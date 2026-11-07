"""Repository for persisting orders and deduplication."""

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import aiosqlite
from src.models.analysis import AnalysisResult, extract_clean_proposal_payload
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
        try:
            async with self._get_conn() as db:
                cursor = await db.execute(
                    """
                    INSERT INTO orders (
                        source, external_id, title, description, url, price,
                        is_negotiable, is_pro_only, tags, status, priority, filter_reason, attachments_text, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        order.attachments_text,
                        order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
                await db.commit()
                return cursor.lastrowid  # type: ignore
        except aiosqlite.IntegrityError:
            # Если запись уже была добавлена параллельным процессом, находим ее ID
            async with self._get_conn() as db:
                async with db.execute(
                    "SELECT id FROM orders WHERE source = ? AND external_id = ? ORDER BY id DESC LIMIT 1",
                    (order.source.value, order.external_id),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return row[0]
            raise

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
                    market_price = ?,
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
                    analysis.market_price,
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

    async def toggle_responded(self, order_id: int, is_responded: Optional[bool] = None) -> bool:
        """Переключить или установить статус отклика по заказу с фиксацией времени отклика."""
        async with self._get_conn() as db:
            if is_responded is None:
                async with db.execute("SELECT is_responded FROM orders WHERE id = ?", (order_id,)) as cursor:
                    row = await cursor.fetchone()
                    current = bool(row[0]) if row and row[0] is not None else False
                new_state = not current
            else:
                new_state = is_responded

            if new_state:
                await db.execute(
                    "UPDATE orders SET is_responded = 1, responded_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (order_id,),
                )
            else:
                await db.execute(
                    "UPDATE orders SET is_responded = 0, responded_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (order_id,),
                )
            await db.commit()
            return new_state

    async def toggle_skipped(self, order_id: int, is_skipped: Optional[bool] = None) -> bool:
        """Переключить или установить статус пропуска (скипа) заказа или вакансии."""
        async with self._get_conn() as db:
            if is_skipped is None:
                async with db.execute("SELECT is_skipped FROM orders WHERE id = ?", (order_id,)) as cursor:
                    row = await cursor.fetchone()
                    current = bool(row[0]) if row and row[0] is not None else False
                new_state = not current
            else:
                new_state = is_skipped

            if new_state:
                await db.execute(
                    "UPDATE orders SET is_skipped = 1, skipped_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (order_id,),
                )
            else:
                await db.execute(
                    "UPDATE orders SET is_skipped = 0, skipped_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (order_id,),
                )
            await db.commit()
            return new_state

    async def update_status(self, order_id: int, status: OrderStatus) -> None:
        """Обновить статус заказа (например, отправлен в TG или архивирован)."""
        async with self._get_conn() as db:
            await db.execute(
                "UPDATE orders SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status.value, order_id),
            )
            await db.commit()

    def _clean_order_row(self, row: Optional[Any]) -> Optional[Dict[str, Any]]:
        """Очистить поля заказа от сырого JSON (например, если в proposal_text попал JSON)."""
        if not row:
            return None
        d = dict(row)
        prop = d.get("proposal_text")
        if prop and ("proposal_text" in str(prop)) and ("{" in str(prop) or "```" in str(prop)):
            payload = extract_clean_proposal_payload(str(prop))
            clean_text = payload.get("proposal_text")
            if clean_text:
                d["proposal_text"] = clean_text
            if d.get("recommended_price") is None and payload.get("recommended_price"):
                d["recommended_price"] = payload.get("recommended_price")
            if d.get("market_price") is None and payload.get("market_price"):
                d["market_price"] = payload.get("market_price")
        return d

    async def update_proposal(
        self,
        order_id: int,
        proposal_text: str,
        recommended_price: Optional[float] = None,
        price_justification: Optional[str] = None,
        market_price: Optional[float] = None,
        estimated_days: Optional[str] = None,
    ) -> None:
        """Сохранить сгенерированный по требованию отклик и обновленную рыночную оценку от agy."""
        # Гарантируем, что в базу сохраняется чистый текст отклика, а не сырой JSON
        payload = extract_clean_proposal_payload(proposal_text)
        clean_proposal_text = payload.get("proposal_text") or proposal_text
        if recommended_price is None and payload.get("recommended_price"):
            recommended_price = payload.get("recommended_price")
        if market_price is None and payload.get("market_price"):
            market_price = payload.get("market_price")
        if price_justification is None and payload.get("price_justification"):
            price_justification = payload.get("price_justification")
        if estimated_days is None and payload.get("estimated_days"):
            estimated_days = payload.get("estimated_days")

        # Парсим число дней для realistic_days если есть
        parsed_days: Optional[float] = None
        if estimated_days:
            import re
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(estimated_days))
            if m:
                try:
                    parsed_days = float(m.group(1))
                except ValueError:
                    pass

        async with self._get_conn() as db:
            # Считываем существующий analysis_json если он есть, чтобы обновить в нем цену, срок и обоснование
            async with db.execute(
                "SELECT analysis_json FROM orders WHERE id = ?", (order_id,)
            ) as cursor:
                row = await cursor.fetchone()

            updated_analysis_json = None
            if row and row[0]:
                try:
                    data = json.loads(row[0])
                    if recommended_price is not None:
                        data["recommended_price"] = recommended_price
                    if market_price is not None:
                        data["market_price"] = market_price
                    if price_justification is not None:
                        data["price_justification"] = price_justification
                    if estimated_days is not None:
                        data["estimated_days"] = estimated_days
                    data["proposal_text"] = clean_proposal_text
                    updated_analysis_json = json.dumps(data, ensure_ascii=False)
                except Exception:
                    pass

            if updated_analysis_json:
                await db.execute(
                    """
                    UPDATE orders SET
                        proposal_text = ?,
                        recommended_price = COALESCE(?, recommended_price),
                        market_price = COALESCE(?, market_price),
                        realistic_days = COALESCE(?, realistic_days),
                        analysis_json = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (clean_proposal_text, recommended_price, market_price, parsed_days, updated_analysis_json, order_id),
                )
            else:
                await db.execute(
                    """
                    UPDATE orders SET
                        proposal_text = ?,
                        recommended_price = COALESCE(?, recommended_price),
                        market_price = COALESCE(?, market_price),
                        realistic_days = COALESCE(?, realistic_days),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (clean_proposal_text, recommended_price, market_price, parsed_days, order_id),
                )
            await db.commit()

    async def get_by_id(self, order_id: int) -> Optional[Dict[str, Any]]:
        """Получить заказ по id."""
        async with self._get_conn() as db:
            async with db.execute(
                """
                SELECT orders.*,
                       (SELECT COUNT(*) FROM order_messages WHERE order_messages.order_id = orders.id) as messages_count
                FROM orders WHERE id = ? LIMIT 1
                """,
                (order_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return self._clean_order_row(dict(row)) if row else None

    async def find_by_url_or_external_id(
        self,
        source: Optional[str] = None,
        external_id: Optional[str] = None,
        url: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Найти заказ по источнику и external_id, либо по URL."""
        async with self._get_conn() as db:
            # 1. Поиск по source и external_id
            if source and external_id:
                async with db.execute(
                    """
                    SELECT orders.*,
                           (SELECT COUNT(*) FROM order_messages WHERE order_messages.order_id = orders.id) as messages_count
                    FROM orders WHERE source = ? AND external_id = ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (source, external_id),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return self._clean_order_row(dict(row))

            # 2. Поиск по точному URL или без query-параметров
            if url:
                clean_url = url.strip()
                async with db.execute(
                    """
                    SELECT orders.*,
                           (SELECT COUNT(*) FROM order_messages WHERE order_messages.order_id = orders.id) as messages_count
                    FROM orders WHERE url = ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (clean_url,),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return self._clean_order_row(dict(row))

                url_base = clean_url.split("?")[0].rstrip("/")
                if len(url_base) > 10:
                    async with db.execute(
                        """
                        SELECT orders.*,
                               (SELECT COUNT(*) FROM order_messages WHERE order_messages.order_id = orders.id) as messages_count
                        FROM orders WHERE url LIKE ?
                        ORDER BY id DESC LIMIT 1
                        """,
                        (f"{url_base}%",),
                    ) as cursor:
                        row = await cursor.fetchone()
                        if row:
                            return self._clean_order_row(dict(row))

            # 3. Поиск по external_id в поле url
            if external_id and len(external_id) >= 4:
                async with db.execute(
                    """
                    SELECT orders.*,
                           (SELECT COUNT(*) FROM order_messages WHERE order_messages.order_id = orders.id) as messages_count
                    FROM orders WHERE external_id = ? OR url LIKE ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (external_id, f"%{external_id}%"),
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        return self._clean_order_row(dict(row))

            return None

    async def get_recent_orders(
        self,
        limit: int = 50,
        priority: Optional[OrderPriority | str] = None,
        status: Optional[OrderStatus | str] = None,
        source: Optional[str] = None,
        only_free: bool = False,
        section: Optional[str] = None,
        hide_responded: bool = False,
        only_responded: bool = False,
        hide_skipped: bool = True,
        only_skipped: bool = False,
    ) -> List[Dict[str, Any]]:
        """Получить список свежих заказов с возможностью фильтрации по секциям, откликам и скипам."""
        query = """
            SELECT orders.*,
                   (SELECT COUNT(*) FROM order_messages WHERE order_messages.order_id = orders.id) as messages_count
            FROM orders WHERE 1=1
        """
        params: List[Any] = []

        if section in ["vacancies", "hh_ru", "hh"]:
            query += " AND source IN ('hh_ru', 'habr_career')"
        elif section == "freelance":
            query += " AND source NOT IN ('hh_ru', 'habr_career')"

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

        if only_responded:
            query += " AND is_responded = 1"
        elif hide_responded:
            query += " AND (is_responded IS NULL OR is_responded = 0)"

        if only_skipped:
            query += " AND is_skipped = 1"
        elif hide_skipped and not only_responded:
            query += " AND (is_skipped IS NULL OR is_skipped = 0)"

        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        async with self._get_conn() as db:
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                return [self._clean_order_row(dict(r)) for r in rows]

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
        """Расширенная статистика с разбивкой по биржам, секциям (фриланс / hh.ru) и среднему чеку."""
        async with self._get_conn() as db:
            stats = await self.get_stats()

            # Фриланс статистика (биржи фриланса без hh_ru)
            async with db.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN priority='hot' THEN 1 ELSE 0 END) as hot,
                    SUM(CASE WHEN priority='normal' THEN 1 ELSE 0 END) as normal,
                    SUM(CASE WHEN priority='trash' THEN 1 ELSE 0 END) as trash,
                    SUM(CASE WHEN status='sent_to_tg' THEN 1 ELSE 0 END) as sent_to_tg,
                    AVG(CASE WHEN price IS NOT NULL AND price > 0 AND priority='hot' THEN price ELSE NULL END) as avg_price,
                    SUM(CASE WHEN is_responded=1 THEN 1 ELSE 0 END) as responded,
                    SUM(CASE WHEN is_skipped=1 THEN 1 ELSE 0 END) as skipped
                FROM orders WHERE source NOT IN ('hh_ru', 'habr_career')
                """
            ) as cursor:
                r_fr = await cursor.fetchone()
                stats["freelance"] = {
                    "total": r_fr[0] or 0,
                    "hot": r_fr[1] or 0,
                    "normal": r_fr[2] or 0,
                    "trash": r_fr[3] or 0,
                    "sent_to_tg": r_fr[4] or 0,
                    "avg_hot_price": round(r_fr[5], 0) if r_fr and r_fr[5] else 0,
                    "responded": r_fr[6] or 0,
                    "skipped": r_fr[7] or 0,
                }

            # Вакансии (HH.ru + Хабр Карьера)
            async with db.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN priority='hot' THEN 1 ELSE 0 END) as hot,
                    SUM(CASE WHEN priority='normal' THEN 1 ELSE 0 END) as normal,
                    SUM(CASE WHEN priority='trash' THEN 1 ELSE 0 END) as trash,
                    SUM(CASE WHEN status='sent_to_tg' THEN 1 ELSE 0 END) as sent_to_tg,
                    AVG(CASE WHEN price IS NOT NULL AND price > 0 AND priority='hot' THEN price ELSE NULL END) as avg_price,
                    SUM(CASE WHEN is_responded=1 THEN 1 ELSE 0 END) as responded,
                    SUM(CASE WHEN is_skipped=1 THEN 1 ELSE 0 END) as skipped
                FROM orders WHERE source IN ('hh_ru', 'habr_career')
                """
            ) as cursor:
                r_hh = await cursor.fetchone()
                vac_stats = {
                    "total": r_hh[0] or 0,
                    "hot": r_hh[1] or 0,
                    "normal": r_hh[2] or 0,
                    "trash": r_hh[3] or 0,
                    "sent_to_tg": r_hh[4] or 0,
                    "avg_hot_price": round(r_hh[5], 0) if r_hh and r_hh[5] else 0,
                    "responded": r_hh[6] or 0,
                    "skipped": r_hh[7] or 0,
                }
                stats["hh_ru"] = vac_stats
                stats["vacancies"] = vac_stats

            async with db.execute(
                """
                SELECT source,
                       COUNT(*) as total,
                       SUM(CASE WHEN priority='hot' THEN 1 ELSE 0 END) as hot,
                       SUM(CASE WHEN priority='normal' THEN 1 ELSE 0 END) as normal,
                       SUM(CASE WHEN priority='trash' THEN 1 ELSE 0 END) as trash,
                       SUM(CASE WHEN is_responded=1 THEN 1 ELSE 0 END) as responded,
                       SUM(CASE WHEN is_skipped=1 THEN 1 ELSE 0 END) as skipped
                FROM orders
                WHERE source NOT IN ('hh_ru', 'habr_career')
                GROUP BY source ORDER BY total DESC
                """
            ) as cursor:
                rows = await cursor.fetchall()
                stats["by_source_freelance"] = [
                    {
                        "source": r[0],
                        "total": r[1],
                        "hot": r[2] or 0,
                        "normal": r[3] or 0,
                        "trash": r[4] or 0,
                        "responded": r[5] or 0,
                        "skipped": r[6] or 0,
                    }
                    for r in rows
                ]

            async with db.execute(
                """
                SELECT source,
                       COUNT(*) as total,
                       SUM(CASE WHEN priority='hot' THEN 1 ELSE 0 END) as hot,
                       SUM(CASE WHEN priority='normal' THEN 1 ELSE 0 END) as normal,
                       SUM(CASE WHEN priority='trash' THEN 1 ELSE 0 END) as trash,
                       SUM(CASE WHEN is_responded=1 THEN 1 ELSE 0 END) as responded,
                       SUM(CASE WHEN is_skipped=1 THEN 1 ELSE 0 END) as skipped
                FROM orders
                WHERE source IN ('hh_ru', 'habr_career')
                GROUP BY source ORDER BY total DESC
                """
            ) as cursor:
                rows = await cursor.fetchall()
                stats["by_source_vacancies"] = [
                    {
                        "source": r[0],
                        "total": r[1],
                        "hot": r[2] or 0,
                        "normal": r[3] or 0,
                        "trash": r[4] or 0,
                        "responded": r[5] or 0,
                        "skipped": r[6] or 0,
                    }
                    for r in rows
                ]

            stats["by_source"] = stats["by_source_freelance"] + stats["by_source_vacancies"]

            async with db.execute(
                "SELECT AVG(price) FROM orders WHERE price IS NOT NULL AND price > 0 AND priority='hot'"
            ) as cursor:
                r = await cursor.fetchone()
                stats["avg_hot_price"] = round(r[0], 0) if r and r[0] else 0

            return stats

    async def get_section_analytics(self, section: str = "freelance") -> Dict[str, Any]:
        """Расширенная аналитика воронки, динамики откликов, скорости реакции и топ-навыков."""
        is_vacancies = section in ["hh_ru", "vacancies", "hh"]
        source_cond = "source IN ('hh_ru', 'habr_career')" if is_vacancies else "source NOT IN ('hh_ru', 'habr_career')"

        async with self._get_conn() as db:
            # 1. Отклики по временным периодам
            async with db.execute(
                f"""
                SELECT
                    SUM(CASE WHEN is_responded = 1 AND (datetime(responded_at, 'localtime') >= datetime('now', 'start of day', 'localtime') OR date(responded_at) = date('now')) THEN 1 ELSE 0 END) as resp_today,
                    SUM(CASE WHEN is_responded = 1 AND datetime(responded_at) >= datetime('now', '-7 days') THEN 1 ELSE 0 END) as resp_7d,
                    SUM(CASE WHEN is_responded = 1 AND datetime(responded_at) >= datetime('now', '-30 days') THEN 1 ELSE 0 END) as resp_30d,
                    SUM(CASE WHEN is_responded = 1 THEN 1 ELSE 0 END) as resp_total,
                    SUM(CASE WHEN priority = 'hot' THEN 1 ELSE 0 END) as hot_total,
                    SUM(CASE WHEN priority = 'hot' AND is_responded = 1 THEN 1 ELSE 0 END) as hot_responded,
                    SUM(CASE WHEN is_skipped = 1 THEN 1 ELSE 0 END) as skipped_total,
                    SUM(CASE WHEN is_responded = 1 AND price IS NOT NULL THEN price ELSE 0 END) as total_pipeline_rub,
                    AVG(CASE WHEN is_responded = 1 AND price IS NOT NULL AND price > 0 THEN price ELSE NULL END) as avg_resp_rub
                FROM orders
                WHERE {source_cond}
                """
            ) as cursor:
                row = await cursor.fetchone()
                resp_today = row[0] or 0
                resp_7d = row[1] or 0
                resp_30d = row[2] or 0
                resp_total = row[3] or 0
                hot_total = row[4] or 0
                hot_responded = row[5] or 0
                skipped_total = row[6] or 0
                total_pipeline_rub = row[7] or 0
                avg_resp_rub = round(row[8], 0) if row and row[8] else 0

            # 2. Скорость реакции (Response Velocity)
            async with db.execute(
                f"""
                SELECT AVG((julianday(responded_at) - julianday(created_at)) * 86400.0)
                FROM orders
                WHERE {source_cond} AND is_responded = 1 AND responded_at IS NOT NULL AND created_at IS NOT NULL
                  AND julianday(responded_at) >= julianday(created_at)
                """
            ) as cursor:
                avg_sec_row = await cursor.fetchone()
                avg_seconds = avg_sec_row[0] if avg_sec_row and avg_sec_row[0] is not None else None

            response_velocity_text = "Нет данных"
            if avg_seconds is not None:
                if avg_seconds < 60:
                    response_velocity_text = f"{int(avg_seconds)} сек"
                elif avg_seconds < 3600:
                    response_velocity_text = f"{int(avg_seconds / 60)} мин"
                elif avg_seconds < 86400:
                    hours = int(avg_seconds / 3600)
                    mins = int((avg_seconds % 3600) / 60)
                    response_velocity_text = f"{hours} ч {mins} мин" if mins else f"{hours} ч"
                else:
                    days = round(avg_seconds / 86400.0, 1)
                    response_velocity_text = f"{days} дн"

            # 3. Конверсия Hot в отклики
            hot_conversion = round((hot_responded / hot_total * 100), 1) if hot_total > 0 else 0.0

            # 4. Топ технологий и навыков: целевые (в Hot-лидах) и общерыночные (все заказы)
            async with db.execute(
                f"""
                SELECT tags, title, description, attachments_text
                FROM orders
                WHERE {source_cond} AND priority = 'hot'
                ORDER BY id DESC LIMIT 300
                """
            ) as cursor:
                hot_rows = await cursor.fetchall()

            async with db.execute(
                f"""
                SELECT tags, title, description, attachments_text
                FROM orders
                WHERE {source_cond}
                ORDER BY id DESC LIMIT 500
                """
            ) as cursor:
                market_rows = await cursor.fetchall()

            import re
            tech_patterns = [
                ("Python", r"\bpython\b"),
                ("FastAPI / Django", r"\b(?:fastapi|django|flask)\b"),
                ("Telegram Bot", r"\b(?:telegram|aiogram|telebot|тг[- ]?бот)\b"),
                ("LLM / GPT / Agents", r"\b(?:llm|gpt|openai|claude|gemini|mistral|llama|langchain|llamaindex|crewai|агент)\b"),
                ("RAG / Vector DB", r"\b(?:rag|qdrant|chroma|pinecone|векторн)\b"),
                ("Whisper / STT / TTS", r"\b(?:whisper|stt|tts|speech|транскриб)\b"),
                ("Computer Vision", r"\b(?:yolo|opencv|cv|компьютерн[а-я]* зрени)\b"),
                ("Парсинг / Scraping", r"\b(?:парс|scraping|crawler|playwright|selenium|beautifulsoup)\b"),
                ("n8n / Automation", r"\b(?:n8n|zapier|make\.com)\b"),
                ("Docker / K8s", r"\b(?:docker|kubernetes|k8s)\b"),
                ("PostgreSQL / SQL", r"\b(?:postgres|postgresql|mysql|sqlite|sql)\b"),
                ("Redis / Celery", r"\b(?:redis|celery|rabbitmq|kafka)\b"),
                ("REST API / gRPC", r"\b(?:rest\s*api|fastapi|grpc|graphql|интеграци[а-я]* по api)\b"),
                ("Linux / CI/CD / DevOps", r"\b(?:linux|ubuntu|systemd|vps|vds|ci[-/]cd|devops)\b"),
                ("CRM / Bitrix24 / Amo", r"\b(?:bitrix|битрикс|amocrm|планфикс|planfix)\b"),
                ("TypeScript / Frontend", r"\b(?:typescript|react|vue|next\.?js|javascript|frontend)\b"),
                ("PyTorch / ML / AI", r"\b(?:pytorch|tensorflow|scikit|fine[- ]?tuning|lora|huggingface)\b"),
                ("Go / Golang", r"\b(?:golang|go)\b"),
                ("Data Engineering", r"\b(?:clickhouse|etl|dbt|airflow|data\s*engineer)\b"),
            ]

            def _calculate_skills(rows):
                if not rows:
                    return []
                tech_counts = {name: 0 for name, _ in tech_patterns}
                for r in rows:
                    combined = f"{r[0] or ''} {r[1] or ''} {r[2] or ''} {r[3] or ''}".lower()
                    for name, pat in tech_patterns:
                        if re.search(pat, combined, re.IGNORECASE):
                            tech_counts[name] += 1
                total_cnt = len(rows)
                return [
                    {
                        "name": name,
                        "count": count,
                        "pct": round(count / total_cnt * 100, 1),
                    }
                    for name, count in sorted(tech_counts.items(), key=lambda x: x[1], reverse=True)
                    if count > 0
                ][:16]

            top_skills = _calculate_skills(hot_rows)
            market_skills = _calculate_skills(market_rows)

            return {
                "section": section,
                "resp_today": resp_today,
                "resp_7d": resp_7d,
                "resp_30d": resp_30d,
                "resp_total": resp_total,
                "hot_total": hot_total,
                "hot_responded": hot_responded,
                "hot_conversion": hot_conversion,
                "skipped_total": skipped_total,
                "total_pipeline_rub": int(total_pipeline_rub),
                "avg_resp_rub": int(avg_resp_rub),
                "response_velocity": response_velocity_text,
                "top_skills": top_skills,
                "market_skills": market_skills,
            }

    async def add_chat_message(
        self,
        order_id: int,
        role: str,
        model: str,
        message: str,
    ) -> int:
        """Сохранить сообщение чата по заказу."""
        async with self._get_conn() as db:
            cursor = await db.execute(
                """
                INSERT INTO order_messages (order_id, role, model, message, created_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (order_id, role, model, message),
            )
            await db.commit()
            return cursor.lastrowid  # type: ignore

    async def get_chat_messages(self, order_id: int) -> List[Dict[str, Any]]:
        """Получить историю переписки по заказу."""
        async with self._get_conn() as db:
            async with db.execute(
                """
                SELECT id, order_id, role, model, message, created_at
                FROM order_messages
                WHERE order_id = ?
                ORDER BY id ASC
                """,
                (order_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_setting(self, key: str, default: Any = None) -> Any:
        """Получить значение настройки из БД (или дефолтное)."""
        async with self._get_conn() as db:
            async with db.execute(
                "SELECT value FROM system_settings WHERE key = ? LIMIT 1", (key,)
            ) as cursor:
                row = await cursor.fetchone()
                if row and row[0] is not None:
                    try:
                        return json.loads(row[0])
                    except Exception:
                        return row[0]
                return default

    async def set_setting(self, key: str, value: Any) -> None:
        """Сохранить или обновить настройку в БД."""
        val_str = json.dumps(value, ensure_ascii=False)
        async with self._get_conn() as db:
            await db.execute(
                """
                INSERT INTO system_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, val_str),
            )
            await db.commit()

    async def get_all_settings(self) -> Dict[str, Any]:
        """Получить все сохраненные настройки."""
        async with self._get_conn() as db:
            async with db.execute("SELECT key, value FROM system_settings") as cursor:
                rows = await cursor.fetchall()
                res = {}
                for r in rows:
                    try:
                        res[r[0]] = json.loads(r[1])
                    except Exception:
                        res[r[0]] = r[1]
                return res

    async def delete_setting(self, key: str) -> None:
        """Удалить настройку из БД."""
        async with self._get_conn() as db:
            await db.execute("DELETE FROM system_settings WHERE key = ?", (key,))
            await db.commit()

    async def save_market_snapshot(self, snapshot: Dict[str, Any]) -> int:
        """Сохранить или обновить снимок аналитики рынка за определенную дату."""
        top_skills_str = json.dumps(snapshot.get("top_skills", {}), ensure_ascii=False)
        sources_str = json.dumps(snapshot.get("sources_breakdown", {}), ensure_ascii=False)
        async with self._get_conn() as db:
            cursor = await db.execute(
                """
                INSERT INTO market_daily_snapshots (
                    date, source_type, scope, total_count, responded_count, skipped_count,
                    hot_count, avg_price, median_price, min_price, max_price,
                    top_skills_json, sources_breakdown_json, ai_summary, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(date, source_type, scope) DO UPDATE SET
                    total_count = excluded.total_count,
                    responded_count = excluded.responded_count,
                    skipped_count = excluded.skipped_count,
                    hot_count = excluded.hot_count,
                    avg_price = excluded.avg_price,
                    median_price = excluded.median_price,
                    min_price = excluded.min_price,
                    max_price = excluded.max_price,
                    top_skills_json = excluded.top_skills_json,
                    sources_breakdown_json = excluded.sources_breakdown_json,
                    ai_summary = COALESCE(excluded.ai_summary, market_daily_snapshots.ai_summary),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    snapshot["date"],
                    snapshot["source_type"],
                    snapshot["scope"],
                    snapshot.get("total_count", 0),
                    snapshot.get("responded_count", 0),
                    snapshot.get("skipped_count", 0),
                    snapshot.get("hot_count", 0),
                    snapshot.get("avg_price"),
                    snapshot.get("median_price"),
                    snapshot.get("min_price"),
                    snapshot.get("max_price"),
                    top_skills_str,
                    sources_str,
                    snapshot.get("ai_summary"),
                ),
            )
            await db.commit()
            return cursor.lastrowid  # type: ignore

    async def get_market_snapshots(
        self,
        source_type: Optional[str] = None,
        scope: Optional[str] = None,
        limit: int = 60,
    ) -> List[Dict[str, Any]]:
        """Получить историю снимков рынка по фильтрам источника и охвата."""
        conds = []
        params: List[Any] = []
        if source_type:
            conds.append("source_type = ?")
            params.append(source_type)
        if scope:
            conds.append("scope = ?")
            params.append(scope)
        where_clause = f"WHERE {' AND '.join(conds)}" if conds else ""
        query = f"""
            SELECT id, date, source_type, scope, total_count, responded_count, skipped_count,
                   hot_count, avg_price, median_price, min_price, max_price,
                   top_skills_json, sources_breakdown_json, ai_summary, created_at, updated_at
            FROM market_daily_snapshots
            {where_clause}
            ORDER BY date DESC
            LIMIT ?
        """
        params.append(limit)
        async with self._get_conn() as db:
            async with db.execute(query, tuple(params)) as cursor:
                rows = await cursor.fetchall()
                results = []
                for r in rows:
                    top_skills = {}
                    if r[12]:
                        try:
                            top_skills = json.loads(r[12])
                        except Exception:
                            pass
                    sources_breakdown = {}
                    if r[13]:
                        try:
                            sources_breakdown = json.loads(r[13])
                        except Exception:
                            pass
                    results.append({
                        "id": r[0],
                        "date": r[1],
                        "source_type": r[2],
                        "scope": r[3],
                        "total_count": r[4],
                        "responded_count": r[5],
                        "skipped_count": r[6],
                        "hot_count": r[7],
                        "avg_price": r[8],
                        "median_price": r[9],
                        "min_price": r[10],
                        "max_price": r[11],
                        "top_skills": top_skills,
                        "sources_breakdown": sources_breakdown,
                        "ai_summary": r[14],
                        "created_at": r[15],
                        "updated_at": r[16],
                    })
                return results

    async def get_latest_market_snapshot(
        self,
        source_type: str,
        scope: str,
    ) -> Optional[Dict[str, Any]]:
        """Получить самый свежий снимок рынка."""
        res = await self.get_market_snapshots(source_type=source_type, scope=scope, limit=1)
        return res[0] if res else None

    async def save_market_ai_summary(
        self,
        date: str,
        source_type: str,
        scope: str,
        ai_summary: str,
    ) -> None:
        """Сохранить сгенерированную AI-сводку в снимок за дату."""
        async with self._get_conn() as db:
            await db.execute(
                """
                UPDATE market_daily_snapshots
                SET ai_summary = ?, updated_at = CURRENT_TIMESTAMP
                WHERE date = ? AND source_type = ? AND scope = ?
                """,
                (ai_summary, date, source_type, scope),
            )
            await db.commit()

    async def get_distinct_order_dates(self) -> List[str]:
        """Получить все даты (YYYY-MM-DD), за которые есть записи в orders."""
        async with self._get_conn() as db:
            async with db.execute(
                """
                SELECT DISTINCT date(created_at) as order_date
                FROM orders
                WHERE created_at IS NOT NULL
                ORDER BY order_date ASC
                """
            ) as cursor:
                rows = await cursor.fetchall()
                return [r[0] for r in rows if r[0]]


