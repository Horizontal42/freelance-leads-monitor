"""Collector for Habr Career (career.habr.com) vacancy RSS feeds."""

from datetime import datetime
import html
import logging
import re
from typing import Any, List, Optional
import feedparser
import httpx
from src.collectors.base import BaseCollector
from src.config import settings
from src.models.order import RawOrder, SourcePlatform

logger = logging.getLogger(__name__)


class HabrCareerCollector(BaseCollector):
    """Сборщик вакансий и проектов с Хабр Карьеры через RSS."""

    def __init__(self, rss_base_url: Optional[str] = None, repo: Optional[Any] = None) -> None:
        super().__init__(name="habr_career")
        self.rss_base_url = rss_base_url or "https://career.habr.com/vacancies/rss"
        self.repo = repo
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
        }

    def _extract_price(self, text: str) -> tuple[Optional[float], bool]:
        """Извлечь указанную вилку зарплаты из заголовка вакансии.

        Возвращает (price, is_negotiable).
        """
        clean_text = html.unescape(text)
        m = re.search(r"(?:от\s+([\d\s]+))?(?:до\s+([\d\s]+))?\s*(?:₽|руб)", clean_text, re.IGNORECASE)
        if m:
            val_from = float(re.sub(r"\s+", "", m.group(1))) if m.group(1) else None
            val_to = float(re.sub(r"\s+", "", m.group(2))) if m.group(2) else None
            if val_from:
                return val_from, False
            if val_to:
                return val_to, False

        return None, True

    def _extract_id(self, link: str, guid: str) -> str:
        """Извлечь числовой идентификатор вакансии."""
        m = re.search(r"/vacancies/(\d+)", link or guid)
        if m:
            return m.group(1)
        clean = (guid or link).rstrip("/").split("/")[-1]
        return clean or str(hash(link))

    async def fetch_new_orders(self, is_cold_start: Optional[bool] = None) -> List[RawOrder]:
        """Получить новые вакансии с Хабр Карьеры по настроенным запросам."""
        config = getattr(settings, "COLLECTORS_HABR_CAREER", None)
        if config and not getattr(config, "enabled", True):
            logger.info("Хабр Карьера отключена в конфигурации.")
            return []

        queries = getattr(config, "queries", ["python", "ai"]) if config else ["python", "ai"]
        rss_base = getattr(config, "rss_url", self.rss_base_url) if config else self.rss_base_url

        seen_ids = set()
        all_vacancies: List[RawOrder] = []

        # Динамические параметры фильтрации
        extra_params = ""
        if self.repo:
            try:
                v_fmt = await self.repo.get_setting("vacancy_work_format", "all")
                if v_fmt == "remote":
                    extra_params += "&s[]=remote"
                v_city = await self.repo.get_setting("vacancy_city", "all")
                if v_city == "moscow":
                    extra_params += "&city_id=678"
                elif v_city == "spb":
                    extra_params += "&city_id=679"
            except Exception as e:
                logger.debug("Не удалось получить настройки вакансий для Хабр Карьеры: %s", e)

        async with httpx.AsyncClient(headers=self.headers, timeout=15.0, follow_redirects=True) as client:
            for query in queries:
                url = f"{rss_base}?q={query}{extra_params}"
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        logger.warning("Хабр Карьера RSS вернул статус %d для q=%s", resp.status_code, query)
                        continue

                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries:
                        link = entry.get("link", "").strip()
                        raw_title = entry.get("title", "").strip()
                        guid = entry.get("id") or entry.get("guid") or ""
                        ext_id = self._extract_id(link, guid)

                        if not ext_id or ext_id in seen_ids:
                            continue
                        seen_ids.add(ext_id)

                        # Извлекаем чистое название из кавычек «...»
                        title_match = re.search(r"«(.*?)»", raw_title)
                        clean_title = title_match.group(1).strip() if title_match else raw_title

                        company = entry.get("author", "").strip()
                        summary = entry.get("summary", "").strip()

                        # Навыки/теги из хэштегов summary: #Python, #FastAPI, etc.
                        tags = re.findall(r"#([A-Za-z0-9_+-]+)", summary)
                        # Очищаем summary от HTML-тегов
                        clean_summary = re.sub(r"<[^>]+>", " ", summary)
                        clean_summary = html.unescape(re.sub(r"\s+", " ", clean_summary)).strip()

                        # Зарплата
                        price, is_negotiable = self._extract_price(raw_title)

                        # Дата публикации
                        created_at = datetime.now()
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            try:
                                created_at = datetime(*entry.published_parsed[:6])
                            except Exception:
                                pass

                        meta_lines = []
                        if company:
                            meta_lines.append(f"🏢 Компания: {company}")
                        if tags:
                            meta_lines.append(f"🔑 Навыки: {', '.join(tags)}")

                        attachments_text = "\n".join(meta_lines) if meta_lines else None

                        raw_order = RawOrder(
                            source=SourcePlatform.HABR_CAREER,
                            external_id=ext_id,
                            title=clean_title,
                            description=clean_summary,
                            url=link,
                            price=price,
                            is_negotiable=is_negotiable,
                            is_pro_only=False,
                            tags=tags,
                            created_at=created_at,
                            attachments_text=attachments_text,
                        )
                        all_vacancies.append(raw_order)

                except Exception as e:
                    logger.warning("Ошибка запроса RSS Хабр Карьеры (%s): %s", url, e)

        logger.info("Хабр Карьера: успешно собрано %d вакансий", len(all_vacancies))
        return all_vacancies
