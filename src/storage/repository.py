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
                    is_negotiable, tags, status, priority, filter_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order.source.value,
                    order.external_id,
                    order.title,
                    order.description,
                    order.url,
                    order.price,
                    1 if order.is_negotiable else 0,
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
        priority: Optional[OrderPriority] = None,
        status: Optional[OrderStatus] = None,
    ) -> List[Dict[str, Any]]:
        """Получить список свежих заказов с возможностью фильтрации."""
        query = "SELECT * FROM orders WHERE 1=1"
        params: List[Any] = []

        if priority:
            query += " AND priority = ?"
            params.append(priority.value)
        if status:
            query += " AND status = ?"
            params.append(status.value)

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
