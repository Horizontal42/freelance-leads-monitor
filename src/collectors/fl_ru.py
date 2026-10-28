"""Collector for FL.ru freelance exchange RSS feed."""

from datetime import datetime
import html
import logging
import re
from typing import List, Optional
import feedparser
import httpx
from src.collectors.base import BaseCollector
from src.config import settings
from src.models.order import RawOrder, SourcePlatform

logger = logging.getLogger(__name__)


class FlRuCollector(BaseCollector):
    """Сборщик заказов с биржи FL.ru через официальный RSS-фид."""

    def __init__(self, rss_url: Optional[str] = None) -> None:
        super().__init__(name="fl_ru")
        self.rss_url = rss_url or settings.FL_RSS_URL
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
        }

    def _extract_external_id(self, link: str) -> str:
        """Извлечь ID проекта из ссылки FL.ru."""
        match = re.search(r"/projects/(\d+)/", link)
        if match:
            return match.group(1)
        # Если паттерн не совпал, хэшируем ссылку или берем конец
        return link.split("/")[-1].replace(".html", "")

    def _extract_price(self, text: str) -> tuple[Optional[float], bool]:
        """Извлечь указанный бюджет из текста заказа.

        Возвращает (price, is_negotiable).
        """
        clean_text = html.unescape(text)

        # Паттерн: "Бюджет: 150 000 ₽" или "15 000 руб"
        budget_pattern = re.search(
            r"(?:бюджет|цена|стоимость)?[:\s]*(\d[\d\s]{2,})\s*(?:₽|&#8381;|руб|р\b|rub)",
            clean_text,
            re.IGNORECASE,
        )
        if budget_pattern:
            raw_digits = re.sub(r"\s+", "", budget_pattern.group(1))
            try:
                price = float(raw_digits)
                return price, False
            except ValueError:
                pass

        # Если бюджет не указан явным числом
        return None, True

    async def fetch_new_orders(self, is_cold_start: Optional[bool] = None) -> List[RawOrder]:
        """Получить и распарсить RSS-фид FL.ru."""
        orders: List[RawOrder] = []

        try:
            async with httpx.AsyncClient(
                headers=self.headers,
                timeout=20.0,
                follow_redirects=True,
            ) as client:
                resp = await client.get(self.rss_url)
                if resp.status_code != 200:
                    logger.warning("FL.ru RSS вернул статус %d", resp.status_code)
                    return []

                content = resp.text

            feed = feedparser.parse(content)
            for entry in feed.entries:
                raw_title = entry.get("title", "")
                link = entry.get("link", "")
                raw_summary = entry.get("summary", "")

                if not link or not raw_title:
                    continue

                title = html.unescape(raw_title).strip()
                description = html.unescape(raw_summary).strip()
                external_id = self._extract_external_id(link)

                # Пытаемся вытащить цену из заголовка или описания
                price, is_negotiable = self._extract_price(f"{title} {description}")

                # Дата публикации
                created_at = datetime.now()
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        created_at = datetime(*entry.published_parsed[:6])
                    except Exception:
                        pass

                # Теги/Категории из RSS
                tags: List[str] = []
                if hasattr(entry, "tags"):
                    tags = [t.get("term", "") for t in entry.tags if t.get("term")]

                is_for_everyone = "(для всех)" in title.lower() or "(для всех)" in description.lower()
                is_pro_only = not is_for_everyone

                orders.append(
                    RawOrder(
                        source=SourcePlatform.FL_RU,
                        external_id=external_id,
                        title=title,
                        description=description,
                        url=link,
                        price=price,
                        is_negotiable=is_negotiable,
                        is_pro_only=is_pro_only,
                        tags=tags,
                        created_at=created_at,
                        raw_payload={"guid": entry.get("id", link)},
                    )
                )

        except Exception as e:
            logger.error("Ошибка при сборе заказов с FL.ru RSS: %r", e)

        logger.info("FlRuCollector собрал %d заказов", len(orders))
        return orders
