"""Repository for persisting orders and deduplication."""

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import aiosqlite
from src.models.analysis import AnalysisResult
from src.models.order import OrderPriority, OrderStatus, RawOrder
from src.storage.db import get_db_connection

logger = logging.getLogger(__name__)


class OrderRepository:
    """Репозиторий для сохранения заказов и проверки дедупликации."""

    def __init__(self, db_path: Optional[Path | str] = None) -> None:
        self.db_path = db_path

    def _get_conn(self):
        return get_db_connection(self.db_path)

    async def is_duplicate(self, source: str, external_id: str) -> bool:
        """Проверить, был ли заказ уже сохранен в базе."""
        async with self._get_conn() as db:
            async with db.execute(
                "SELECT 1 FROM orders WHERE source = ? AND external_id = ? LIMIT 1",
                (source, external_id),
            ) as cursor:
                row = await cursor.fetchone()
                return row is not None

    async def insert_raw_order(
        self,
        order: RawOrder,
        status: OrderStatus = OrderStatus.NEW,
        priority: OrderPriority = OrderPriority.NORMAL,
        filter_reason: Optional[str] = None,
    ) -> int:
        """Сохранить новый заказ в базу. Возвращает сгенерированный id."""
        tags_str = json.dumps(order.tags, ensure_ascii=False)
        async with self._get_conn() as db:
            cursor = await db.execute(
                """
                INSERT INTO orders (
                    source, external_id, title, description, url, price,
                    is_negotiable, is_pro_only, tags, status, priority, filter_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.source.value,
                    order.external_id,
                    order.title,
                    order.description,
                    order.url,
                    order.price,
                    1 if order.is_negotiable else 0,
                    1 if order.is_pro_only else 0,
                    tags_str,
                    status.value,
                    priority.value,
                    filter_reason,
                    order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )
            await db.commit()
            return cursor.lastrowid  # type: ignore

    async def update_analysis(
        self,
        order_id: int,
        analysis: AnalysisResult,
        status: OrderStatus = OrderStatus.ANALYZED,
    ) -> None:
        """Обновить заказ данными анализа нейросети."""
        analysis_json = analysis.model_dump_json()
        async with self._get_conn() as db:
            await db.execute(
                """
                UPDATE orders SET
                    score = ?,
                    recommended_price = ?,
                    realistic_days = ?,
                    matched_project = ?,
                    proposal_text = ?,
                    analysis_json = ?,
                    priority = ?,
                    status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    analysis.score,
                    analysis.recommended_price,
                    analysis.realistic_days,
                    analysis.matched_project,
                    analysis.proposal_text,
                    analysis_json,
                    analysis.priority.value,
                    status.value,
                    order_id,
                ),
            )
            await db.commit()

    async def update_status(self, order_id: int, status: OrderStatus) -> None:
        """Обновить статус заказа (например, отправлен в TG или архивирован)."""
        async with self._get_conn() as db:
            await db.execute(
                "UPDATE orders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status.value, order_id),
            )
            await db.commit()

    async def update_proposal(self, order_id: int, proposal_text: str) -> None:
        """Сохранить сгенерированный по требованию отклик."""
        async with self._get_conn() as db:
            await db.execute(
                "UPDATE orders SET proposal_text = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (proposal_text, order_id),
            )
            await db.commit()

    async def get_by_id(self, order_id: int) -> Optional[Dict[str, Any]]:
        """Получить заказ по id."""
        async with self._get_conn() as db:
            async with db.execute(
                "SELECT * FROM orders WHERE id = ? LIMIT 1", (order_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_recent_orders(
        self,
        limit: int = 50,
        priority: Optional[OrderPriority | str] = None,
        status: Optional[OrderStatus | str] = None,
        source: Optional[str] = None,
        only_free: bool = False,
    ) -> List[Dict[str, Any]]:
        """Получить список свежих заказов с возможностью фильтрации."""
        query = "SELECT * FROM orders WHERE 1=1"
        params: List[Any] = []

        if priority:
            p_val = priority.value if hasattr(priority, "value") else str(priority)
            query += " AND priority = ?"
            params.append(p_val)
        if status:
            s_val = status.value if hasattr(status, "value") else str(status)
            query += " AND status = ?"
            params.append(s_val)
        if source:
            query += " AND source = ?"
            params.append(str(source).lower())
        if only_free:
            query += " AND is_pro_only = 0"

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        async with self._get_conn() as db:
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_stats(self) -> Dict[str, int]:
        """Получить сводную статистику по базе."""
        async with self._get_conn() as db:
            stats: Dict[str, int] = {}
            async with db.execute("SELECT COUNT(*) FROM orders") as cursor:
                stats["total"] = (await cursor.fetchone())[0]
            async with db.execute(
                "SELECT COUNT(*) FROM orders WHERE priority = 'hot'"
            ) as cursor:
                stats["hot"] = (await cursor.fetchone())[0]
            async with db.execute(
                "SELECT COUNT(*) FROM orders WHERE priority = 'normal'"
            ) as cursor:
                stats["normal"] = (await cursor.fetchone())[0]
            async with db.execute(
                "SELECT COUNT(*) FROM orders WHERE priority = 'trash'"
            ) as cursor:
                stats["trash"] = (await cursor.fetchone())[0]
            async with db.execute(
                "SELECT COUNT(*) FROM orders WHERE status = 'sent_to_tg'"
            ) as cursor:
                stats["sent_to_tg"] = (await cursor.fetchone())[0]
            return stats

    async def get_extended_stats(self) -> Dict[str, Any]:
        """Расширенная статистика с разбивкой по биржам и среднему чеку."""
        async with self._get_conn() as db:
            stats = await self.get_stats()
            async with db.execute(
                """
                SELECT source,
                       COUNT(*) as total,
                       SUM(CASE WHEN priority='hot' THEN 1 ELSE 0 END) as hot,
                       SUM(CASE WHEN priority='normal' THEN 1 ELSE 0 END) as normal,
                       SUM(CASE WHEN priority='trash' THEN 1 ELSE 0 END) as trash
                FROM orders GROUP BY source ORDER BY total DESC
                """
            ) as cursor:
                rows = await cursor.fetchall()
                stats["by_source"] = [
                    {
                        "source": r[0],
                        "total": r[1],
                        "hot": r[2] or 0,
                        "normal": r[3] or 0,
                        "trash": r[4] or 0,
                    }
                    for r in rows
                ]

            async with db.execute(
                "SELECT AVG(price) FROM orders WHERE price IS NOT NULL AND price > 0 AND priority='hot'"
            ) as cursor:
                r = await cursor.fetchone()
                stats["avg_hot_price"] = round(r[0], 0) if r and r[0] else 0

            return stats
