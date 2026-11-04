"""Service for local database re-evaluation of orders and vacancies."""

import json
import logging
from typing import Any, Dict, List, Optional

from src.analyzer.base import BaseLLMClient
from src.config import settings
from src.filters.pre_filter import HardFilter
from src.models.order import OrderPriority, OrderStatus, RawOrder, SourcePlatform
from src.storage.repository import OrderRepository

logger = logging.getLogger(__name__)


class DatabaseRecalculator:
    """Сервис локального пересчета и переоценки заказов и вакансий в базе SQLite без обращения к внешним API."""

    def __init__(self, repo: OrderRepository) -> None:
        self.repo = repo

    async def run(
        self,
        scope: str = "trash",
        limit: int = 300,
        analyze_llm: bool = True,
        llm_client: Optional[BaseLLMClient] = None,
    ) -> Dict[str, Any]:
        """Запустить локальный пересчет базы по текущим правилам."""
        saved_settings = await self.repo.get_all_settings()
        filter_pro = saved_settings.get("filter_pro_only", settings.FILTER_PRO_ONLY)
        min_budget = saved_settings.get("min_budget", settings.MIN_BUDGET)

        hard_filter = HardFilter(
            keywords=settings.KEYWORDS,
            stop_words=settings.STOP_WORDS,
            min_budget=min_budget,
            filter_pro_only=filter_pro,
        )

        query = "SELECT * FROM orders WHERE 1=1"
        params: List[Any] = []

        if scope == "trash":
            query += " AND priority = 'trash'"
        elif scope == "hh_ru":
            query += " AND source IN ('hh_ru', 'habr_career')"
        elif scope == "freelance":
            query += " AND source NOT IN ('hh_ru', 'habr_career')"

        query += " ORDER BY id DESC"
        if limit and limit > 0:
            query += f" LIMIT {int(limit)}"

        async with self.repo._get_conn() as db:
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                orders = [dict(r) for r in rows]

        total_processed = len(orders)
        recovered_count = 0
        moved_to_trash_count = 0
        unchanged_count = 0

        for row in orders:
            order_id = row["id"]
            current_priority = row.get("priority")
            current_status = row.get("status")

            try:
                src_platform = SourcePlatform(row["source"])
            except Exception:
                src_platform = SourcePlatform.CUSTOM

            tags = []
            if row.get("tags"):
                try:
                    tags = json.loads(row["tags"])
                except Exception:
                    tags = []

            raw_order = RawOrder(
                source=src_platform,
                external_id=row.get("external_id") or str(order_id),
                title=row.get("title") or "",
                description=row.get("description") or "",
                url=row.get("url") or "",
                price=row.get("price"),
                is_negotiable=bool(row.get("is_negotiable")),
                is_pro_only=bool(row.get("is_pro_only")),
                tags=tags,
                attachments_text=row.get("attachments_text"),
            )

            filter_res = hard_filter.evaluate(raw_order)

            if filter_res.passed:
                # Если заказ был в trash, восстанавливаем его
                if current_priority == "trash" or current_status == "rejected":
                    if analyze_llm and llm_client:
                        try:
                            analysis = await llm_client.analyze_order(raw_order)
                            new_status = OrderStatus.ANALYZED
                            await self.repo.update_analysis(
                                order_id=order_id,
                                analysis=analysis,
                                status=new_status,
                            )
                        except Exception as e:
                            logger.warning("Ошибка AI-анализа при пересчете заказа #%d: %s", order_id, e)
                            async with self.repo._get_conn() as db:
                                await db.execute(
                                    "UPDATE orders SET priority = 'normal', status = 'new', filter_reason = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                                    (order_id,),
                                )
                                await db.commit()
                    else:
                        async with self.repo._get_conn() as db:
                            await db.execute(
                                "UPDATE orders SET priority = 'normal', status = 'new', filter_reason = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                                (order_id,),
                            )
                            await db.commit()
                    recovered_count += 1
                else:
                    unchanged_count += 1
            else:
                # Заказ не прошел фильтр
                if current_priority != "trash":
                    async with self.repo._get_conn() as db:
                        await db.execute(
                            "UPDATE orders SET priority = 'trash', status = 'rejected', filter_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                            (filter_res.reason, order_id),
                        )
                        await db.commit()
                    moved_to_trash_count += 1
                else:
                    # Остается в trash, обновляем причину если изменилась
                    if row.get("filter_reason") != filter_res.reason:
                        async with self.repo._get_conn() as db:
                            await db.execute(
                                "UPDATE orders SET filter_reason = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                                (filter_res.reason, order_id),
                            )
                            await db.commit()
                    unchanged_count += 1

        return {
            "ok": True,
            "total_processed": total_processed,
            "recovered": recovered_count,
            "moved_to_trash": moved_to_trash_count,
            "unchanged": unchanged_count,
            "message": (
                f"Локальный пересчет завершен: обработано {total_processed} записей. "
                f"Восстановлено: {recovered_count}, отсеяно в Trash: {moved_to_trash_count}, без изменений: {unchanged_count}."
            ),
        }
