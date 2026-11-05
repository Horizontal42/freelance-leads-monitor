"""Pipeline dispatcher for end-to-end processing of freelance orders."""

import asyncio
import logging
from typing import List, Optional
from src.analyzer.base import BaseLLMClient
from src.collectors.enricher import OrderEnricher
from src.config import settings
from src.filters.pre_filter import HardFilter
from src.models.order import OrderPriority, OrderStatus, RawOrder, SourcePlatform
from src.notifiers.telegram_notifier import TelegramNotifier
from src.storage.repository import OrderRepository

logger = logging.getLogger(__name__)


class LeadsPipeline:
    """Оркестратор обработки заказов: дедупликация -> фильтр -> нейросеть -> роутинг."""

    def __init__(
        self,
        repo: OrderRepository,
        hard_filter: HardFilter,
        llm_client: BaseLLMClient,
        tg_notifier: Optional[TelegramNotifier] = None,
        vacancies_notifier: Optional[TelegramNotifier] = None,
        enricher: Optional[OrderEnricher] = None,
        max_concurrency: int = 2,
    ) -> None:
        self.repo = repo
        self.hard_filter = hard_filter
        self.llm_client = llm_client
        self.tg_notifier = tg_notifier
        self.vacancies_notifier = vacancies_notifier or tg_notifier
        self.enricher = enricher or OrderEnricher()
        self.semaphore = asyncio.Semaphore(max_concurrency)

    async def process_orders(self, orders: List[RawOrder]) -> dict:
        """Обработать пачку свежих заказов."""
        stats = {
            "received": len(orders),
            "duplicates": 0,
            "filtered_trash": 0,
            "analyzed_normal": 0,
            "hot_leads_sent": 0,
            "errors": 0,
        }

        # Считываем динамические настройки из БД (или используем дефолты из конфига)
        dyn_settings = await self.repo.get_all_settings()
        filter_pro = dyn_settings.get("filter_pro_only", settings.FILTER_PRO_ONLY)
        min_budget = dyn_settings.get("min_budget", settings.MIN_BUDGET)
        vacancy_min_salary = dyn_settings.get("vacancy_min_salary", getattr(settings, "VACANCY_MIN_SALARY", 80000))
        vacancy_allow_negotiable = dyn_settings.get(
            "vacancy_allow_negotiable",
            getattr(settings, "VACANCY_ALLOW_NEGOTIABLE", True),
        )
        hot_threshold = dyn_settings.get("hot_score_threshold", settings.HOT_SCORE_THRESHOLD)
        vacancy_hot_threshold = dyn_settings.get(
            "vacancy_hot_score_threshold",
            getattr(settings, "VACANCY_HOT_SCORE_THRESHOLD", 8),
        )

        # Синхронизируем динамические списки ключевых и стоп-слов из настроек БД
        if "filter_keywords" in dyn_settings and isinstance(dyn_settings["filter_keywords"], list):
            self.hard_filter.keywords = [w.lower().strip() for w in dyn_settings["filter_keywords"] if w.strip()]
        if "filter_stop_words" in dyn_settings and isinstance(dyn_settings["filter_stop_words"], list):
            self.hard_filter.stop_words = [w.lower().strip() for w in dyn_settings["filter_stop_words"] if w.strip()]

        self.hard_filter.min_budget = min_budget
        self.hard_filter.allow_quick_orders = dyn_settings.get(
            "allow_quick_orders", getattr(settings, "ALLOW_QUICK_ORDERS", True)
        )
        self.hard_filter.quick_min_budget = dyn_settings.get(
            "quick_min_budget", getattr(settings, "QUICK_MIN_BUDGET", 2000)
        )

        passed_orders: List[RawOrder] = []

        # 1. Первичная фильтрация и отсев дубликатов
        for order in orders:
            if await self.repo.is_duplicate(order.source.value, order.external_id):
                stats["duplicates"] += 1
                continue

            # Проверка выключен ли источник
            platform_key = f"platform_{order.source.value}"
            if dyn_settings.get(platform_key) is False:
                stats["filtered_trash"] += 1
                await self.repo.insert_raw_order(
                    order=order,
                    status=OrderStatus.REJECTED,
                    priority=OrderPriority.TRASH,
                    filter_reason=f"Источник {order.source.value} отключен в настройках",
                )
                continue

            # Проверка фильтра PRO
            if filter_pro and order.is_pro_only:
                stats["filtered_trash"] += 1
                await self.repo.insert_raw_order(
                    order=order,
                    status=OrderStatus.REJECTED,
                    priority=OrderPriority.TRASH,
                    filter_reason="Заказ только для PRO (отключен в настройках)",
                )
                continue

            # Проверка минимального бюджета (для фриланса) или минимальной зарплаты (для вакансий)
            is_vacancy = order.source in (SourcePlatform.HH_RU, SourcePlatform.HABR_CAREER)
            if is_vacancy:
                if order.is_negotiable or not order.price:
                    if not vacancy_allow_negotiable:
                        stats["filtered_trash"] += 1
                        await self.repo.insert_raw_order(
                            order=order,
                            status=OrderStatus.REJECTED,
                            priority=OrderPriority.TRASH,
                            filter_reason="Зарплата не указана (вакансии без указания вилки отключены)",
                        )
                        continue
                elif vacancy_min_salary and order.price < vacancy_min_salary:
                    stats["filtered_trash"] += 1
                    await self.repo.insert_raw_order(
                        order=order,
                        status=OrderStatus.REJECTED,
                        priority=OrderPriority.TRASH,
                        filter_reason=f"Зарплата {int(order.price)} ₽ ниже минимальной ({vacancy_min_salary} ₽)",
                    )
                    continue
            else:
                if min_budget and order.price and order.price < min_budget and not order.is_negotiable:
                    stats["filtered_trash"] += 1
                    await self.repo.insert_raw_order(
                        order=order,
                        status=OrderStatus.REJECTED,
                        priority=OrderPriority.TRASH,
                        filter_reason=f"Бюджет {int(order.price)} ₽ ниже минимального ({min_budget} ₽)",
                    )
                    continue

            filter_res = self.hard_filter.evaluate(order)
            if not filter_res.passed:
                stats["filtered_trash"] += 1
                await self.repo.insert_raw_order(
                    order=order,
                    status=OrderStatus.REJECTED,
                    priority=OrderPriority.TRASH,
                    filter_reason=filter_res.reason,
                )
                logger.debug(
                    "Заказ [%s #%s] отсеян фильтром: %s",
                    order.source.value,
                    order.external_id,
                    filter_res.reason,
                )
                continue

            passed_orders.append(order)

        # 2. Конкурентный анализ прошедших заказов через LLM с семафором
        async def _analyze_and_route(order: RawOrder) -> None:
            async with self.semaphore:
                # Полная выгрузка ТЗ и файлов перед отправкой в LLM (экономия токенов модели)
                order = await self.enricher.enrich(order)

                logger.info(
                    "Заказ [%s #%s] обогащен (текст: %d симв, файлы: %s). Отправка в LLM: '%s'...",
                    order.source.value,
                    order.external_id,
                    len(order.description),
                    "да" if order.attachments_text else "нет",
                    order.title[:45],
                )
                try:
                    analysis = await self.llm_client.analyze_order(order)
                except Exception as e:
                    stats["errors"] += 1
                    logger.error(
                        "Ошибка при анализе заказа [%s #%s] в LLM: %s",
                        order.source.value,
                        order.external_id,
                        e,
                    )
                    await self.repo.insert_raw_order(
                        order=order,
                        status=OrderStatus.NEW,
                        priority=OrderPriority.NORMAL,
                        filter_reason=f"Ошибка LLM: {e}",
                    )
                    return

                order_id = await self.repo.insert_raw_order(
                    order=order,
                    status=OrderStatus.ANALYZED,
                    priority=analysis.priority,
                )
                await self.repo.update_analysis(
                    order_id=order_id,
                    analysis=analysis,
                    status=OrderStatus.ANALYZED,
                )

                is_vacancy = order.source in (SourcePlatform.HH_RU, SourcePlatform.HABR_CAREER)
                effective_hot_threshold = vacancy_hot_threshold if is_vacancy else hot_threshold

                if is_vacancy:
                    is_hot = analysis.score >= effective_hot_threshold
                else:
                    is_hot = (
                        analysis.priority == OrderPriority.HOT
                        or analysis.score >= effective_hot_threshold
                    )

                if is_hot:
                    stats["hot_leads_sent"] += 1
                    logger.info(
                        "🔥 Горячий лид найден (#%d, скор: %d)!",
                        order_id,
                        analysis.score,
                    )
                    active_notifier = self.vacancies_notifier if is_vacancy else self.tg_notifier
                    if active_notifier is not None:
                        sent = await active_notifier.send_lead(
                            order=order,
                            analysis=analysis,
                            order_db_id=order_id,
                        )
                        if sent:
                            await self.repo.update_status(order_id, OrderStatus.SENT_TO_TG)
                    else:
                        logger.debug("Нотификатор не задан, пропуск отправки в Telegram")
                else:
                    stats["analyzed_normal"] += 1
                    logger.info(
                        "⚡ Обычный заказ (#%d, скор: %d) сохранен в базу (без пуша в Telegram).",
                        order_id,
                        analysis.score,
                    )

        if passed_orders:
            await asyncio.gather(*(_analyze_and_route(o) for o in passed_orders))

        return stats
