"""Pipeline dispatcher for end-to-end processing of freelance orders."""

import asyncio
import logging
from typing import List, Optional
from src.analyzer.base import BaseLLMClient
from src.config import settings
from src.filters.pre_filter import HardFilter
from src.models.order import OrderPriority, OrderStatus, RawOrder
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
        max_concurrency: int = 2,
    ) -> None:
        self.repo = repo
        self.hard_filter = hard_filter
        self.llm_client = llm_client
        self.tg_notifier = tg_notifier
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

        passed_orders: List[RawOrder] = []

        # 1. Первичная фильтрация и отсев дубликатов
        for order in orders:
            if await self.repo.is_duplicate(order.source.value, order.external_id):
                stats["duplicates"] += 1
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
                logger.info(
                    "Заказ [%s #%s] прошел фильтр. Отправка в LLM: '%s'...",
                    order.source.value,
                    order.external_id,
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

                is_hot = (
                    analysis.priority == OrderPriority.HOT
                    or analysis.score >= settings.HOT_SCORE_THRESHOLD
                )

                if is_hot:
                    stats["hot_leads_sent"] += 1
                    logger.info(
                        "🔥 Горячий лид найден (#%d, скор: %d)!",
                        order_id,
                        analysis.score,
                    )
                    if self.tg_notifier is not None:
                        sent = await self.tg_notifier.send_lead(
                            order=order,
                            analysis=analysis,
                            order_db_id=order_id,
                        )
                        if sent:
                            await self.repo.update_status(order_id, OrderStatus.SENT_TO_TG)
                    else:
                        logger.debug("tg_notifier не задан, пропуск отправки в Telegram")
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
