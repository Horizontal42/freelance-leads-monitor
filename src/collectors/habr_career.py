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

        # Фильтры грейда и нецелевого стека для IT-вакансий Хабр Карьеры
        self.drop_title_rx = re.compile(
            r"senior|сеньор|\blead\b|тимлид|team lead|ведущ|старш|главный|principal|head of|руководител|архитектор|architect",
            re.IGNORECASE,
        )
        self.junior_title_rx = re.compile(
            r"junior|джуниор|\bджун\b|стаж[её]р|стажировк|\bintern\b|\binternship\b|\btrainee\b|начинающ|младш",
            re.IGNORECASE,
        )
        self.drop_tags_rx = re.compile(
            r"^(?:senior|lead|principal|architect|архитектор|руководитель|тимлид)$",
            re.IGNORECASE,
        )
        self.drop_languages_rx = re.compile(
            r"(?:(?:\b|_)c#(?=[^a-zA-Z0-9]|$)|c-sharp|csharp|\.net\b|\bdotnet\b|\bjava\b(?!\s*script)|\bphp\b|(?:\b|_)c\+\+(?=[^a-zA-Z0-9]|$)|cpp\b|\bgolang\b|\bgo\s*(?:разработчик|developer|инженер|engineer|бэкенд|backend)\b|\bruby\b|\brails\b|\brust\b|\bkotlin\b|\bandroid\b|\bswift\b|\bios\b|\b1с\b|\b1c\b|\bvmware\b)",
            re.IGNORECASE,
        )
        self.target_stack_rx = re.compile(
            r"\b(?:python|питон|ai\b|ии\b|ml\b|llm|rag|нейросет|data engineer|nlp|cv\b)\b",
            re.IGNORECASE,
        )

    def _is_too_senior(self, title: str, tags: List[str]) -> bool:
        """Проверить заголовок и теги на завышенный сеньорский грейд."""
        if any(self.drop_tags_rx.search(t.strip()) for t in tags):
            return True
        if self.drop_title_rx.search(title) and not self.junior_title_rx.search(title):
            return True
        return False

    def _is_non_target_stack(self, title: str, tags: List[str]) -> bool:
        """Проверить, не ориентирована ли вакансия на чужой язык программирования (C#, Java, PHP и т.д.)."""
        # Если в заголовке прямо указан чужой стек и нет Python/AI
        if self.drop_languages_rx.search(title) and not self.target_stack_rx.search(title):
            return True
        # Если теги содержат чужие языки, а Python/AI отсутствует
        tag_str = " ".join(tags)
        if self.drop_languages_rx.search(tag_str) and not self.target_stack_rx.search(f"{title} {tag_str}"):
            return True
        return False

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

        # Динамические параметры фильтрации (удаленка не привязывается к городу)
        extra_param_sets = [""]
        if self.repo:
            try:
                v_fmt = await self.repo.get_setting("vacancy_work_format", "all")
                v_city = await self.repo.get_setting("vacancy_city", "all")

                city_param = ""
                if v_city == "moscow":
                    city_param = "&city_id=678"
                elif v_city == "spb":
                    city_param = "&city_id=679"

                if v_fmt == "remote":
                    # RSS Хабр Карьеры ломается при передаче &s[]=remote, поэтому запрашиваем базовый фид
                    extra_param_sets = [""]
                elif v_fmt == "office":
                    extra_param_sets = [f"{city_param}"]
                elif v_fmt == "hybrid":
                    extra_param_sets = [f"{city_param}"]
                else:  # "all"
                    if city_param:
                        extra_param_sets = ["", city_param]
                    else:
                        extra_param_sets = [""]
            except Exception as e:
                logger.debug("Не удалось получить настройки вакансий для Хабр Карьеры: %s", e)

        async with httpx.AsyncClient(headers=self.headers, timeout=15.0, follow_redirects=True) as client:
            for query in queries:
                for extra_params in extra_param_sets:
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

                            # Отсев завышенного грейда (Senior/Lead) и чужих стеков (C#, Java, PHP и т.д.)
                            if self._is_too_senior(clean_title, tags):
                                logger.debug("Хабр Карьера: отсев по грейду (Senior/Lead): '%s' (теги: %s)", clean_title, tags)
                                continue
                            if self._is_non_target_stack(clean_title, tags):
                                logger.debug("Хабр Карьера: отсев по нецелевому стеку: '%s' (теги: %s)", clean_title, tags)
                                continue

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
