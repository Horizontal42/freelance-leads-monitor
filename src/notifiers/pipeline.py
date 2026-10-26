"""Pipeline dispatcher for end-to-end processing of freelance orders."""

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
    ) -> None:
        self.repo = repo
        self.hard_filter = hard_filter
        self.llm_client = llm_client
        self.tg_notifier = tg_notifier or TelegramNotifier()

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

        for order in orders:
            # 1. Проверка дедупликации
            if await self.repo.is_duplicate(order.source.value, order.external_id):
                stats["duplicates"] += 1
                continue

            # 2. Эвристический Hard-Filter
            filter_res = self.hard_filter.evaluate(order)
            if not filter_res.passed:
                stats["filtered_trash"] += 1
                # Сохраняем в базу с флагом REJECTED, чтобы не анализировать повторно
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

            # 3. Анализ нейросетью (Antigravity / Mistral)
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
                # Сохраняем как непроанализированный заказ
                await self.repo.insert_raw_order(
                    order=order,
                    status=OrderStatus.NEW,
                    priority=OrderPriority.NORMAL,
                    filter_reason=f"Ошибка LLM: {e}",
                )
                continue

            # 4. Сохранение результатов анализа
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

            # 5. Роутинг по уровням (Tiering)
            is_hot = (
                analysis.priority == OrderPriority.HOT
                or analysis.score >= settings.HOT_SCORE_THRESHOLD
            )

            if is_hot:
                stats["hot_leads_sent"] += 1
                logger.info(
                    "🔥 Горячий лид найден (#%d, скор: %d)! Отправка в Telegram...",
                    order_id,
                    analysis.score,
                )
                sent = await self.tg_notifier.send_lead(
                    order=order,
                    analysis=analysis,
                    order_db_id=order_id,
                )
                if sent:
                    await self.repo.update_status(order_id, OrderStatus.SENT_TO_TG)
            else:
                stats["analyzed_normal"] += 1
                logger.info(
                    "⚡ Обычный заказ (#%d, скор: %d) сохранен в базу (без пуша в Telegram).",
                    order_id,
                    analysis.score,
                )

        return stats
