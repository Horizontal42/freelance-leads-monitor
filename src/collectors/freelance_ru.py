"""Collector for Freelance.ru exchange."""

from datetime import datetime
import html
import logging
import re
from typing import List, Optional
import httpx
from src.collectors.base import BaseCollector
from src.models.order import RawOrder, SourcePlatform

logger = logging.getLogger(__name__)


class FreelanceRuCollector(BaseCollector):
    """Сборщик заказов с биржи Freelance.ru (вторая крупнейшая биржа РФ)."""

    def __init__(
        self,
        base_url: str = "https://freelance.ru",
        categories: Optional[List[int]] = None,
        normal_pages: Optional[int] = None,
        backfill_pages: Optional[int] = None,
    ) -> None:
        super().__init__(name="freelance_ru")
        self.base_url = base_url.rstrip("/")
        from src.config import settings
        self.categories = (
            categories
            if categories is not None
            else getattr(settings, "FREELANCE_RU_CATEGORIES", [4, 724])
        )
        self.normal_pages = (
            normal_pages
            if normal_pages is not None
            else getattr(settings, "FREELANCE_RU_NORMAL_PAGES", 2)
        )
        self.backfill_pages = (
            backfill_pages
            if backfill_pages is not None
            else getattr(settings, "FREELANCE_RU_BACKFILL_PAGES", 4)
        )
        self._is_first_run: bool = True
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def _parse_article(self, article_html: str) -> Optional[RawOrder]:
        """Распарсить карточку заказа <article class="task-card">."""
        try:
            # 1. Ссылка и заголовок
            m_link = re.search(
                r'<a class="task-card__title-link" href="(/task/view/(\d+))"[^>]*>(.*?)</a>',
                article_html,
                re.DOTALL,
            )
            if not m_link:
                return None

            path = m_link.group(1)
            external_id = m_link.group(2)
            title = html.unescape(m_link.group(3)).strip()
            url = f"{self.base_url}{path}"

            # 2. Описание
            m_desc = re.search(
                r'<p class="task-card__desc">(.*?)</p>',
                article_html,
                re.DOTALL,
            )
            description = ""
            if m_desc:
                raw_desc = m_desc.group(1)
                clean_desc = re.sub(r"<[^>]+>", " ", raw_desc)
                description = html.unescape(clean_desc).strip()

            # 3. Бюджет
            m_budget = re.search(
                r'<div class="task-card__budget[^"]*">(.*?)</div>',
                article_html,
                re.DOTALL,
            )
            budget_raw = m_budget.group(1) if m_budget else ""
            budget_lower = budget_raw.lower()

            is_negotiable = (
                "cost-not-set" in budget_raw
                or "индивидуально" in budget_lower
                or "договор" in budget_lower
                or not budget_raw.strip()
            )

            price: Optional[float] = None
            if not is_negotiable:
                # Ищем число перед символом рубля или &#8381;
                clean_budget = html.unescape(budget_raw)
                p_digits = re.search(
                    r"(\d[\d\s]*)\s*(?:₽|&#8381;|руб|р\b)",
                    clean_budget,
                    re.IGNORECASE,
                )
                if p_digits:
                    try:
                        price = float(re.sub(r"\s+", "", p_digits.group(1)))
                    except ValueError:
                        price = None
                        is_negotiable = True
                else:
                    is_negotiable = True

            # 4. Теги / Категории (chips)
            chips = re.findall(
                r'<span class="task-chip[^"]*">(.*?)</span>',
                article_html,
            )
            tags = [html.unescape(c).strip() for c in chips if c.strip()]

            # 5. Дата публикации
            m_date = re.search(
                r'<span class="task-card__foot-item" title="(\d\d\.\d\d\.\d\d\d\d \d\d:\d\d)">',
                article_html,
            )
            created_at = datetime.now()
            if m_date:
                try:
                    created_at = datetime.strptime(m_date.group(1), "%d.%m.%Y %H:%M")
                except ValueError:
                    pass

            is_pro_only = (
                "task-card__pro" in article_html
                or "аккаунт pro" in article_html.lower()
                or "только для pro" in article_html.lower()
            )

            return RawOrder(
                source=SourcePlatform.FREELANCE_RU,
                external_id=external_id,
                title=title,
                description=description,
                url=url,
                price=price,
                is_negotiable=is_negotiable,
                is_pro_only=is_pro_only,
                tags=tags,
                created_at=created_at,
                raw_payload={"path": path},
            )

        except Exception as e:
            logger.error("Ошибка парсинга карточки Freelance.ru: %s", e)
            return None

    async def fetch_new_orders(self, is_cold_start: Optional[bool] = None) -> List[RawOrder]:
        """Получить свежие заказы из категорий IT/Нейросетей и общей ленты Freelance.ru."""
        cold = self._is_first_run if is_cold_start is None else is_cold_start
        self._is_first_run = False
        depth = self.backfill_pages if cold else self.normal_pages

        orders: List[RawOrder] = []
        seen_ids = set()

        # Формируем целевые выборки страниц
        target_requests: List[str] = []

        # 1. Категории IT (4 - Веб-разработка и IT, 724 - ИИ и Нейросети)
        for cat_id in self.categories:
            for p in range(1, depth + 1):
                sep = "&" if p > 1 else ""
                target_requests.append(
                    f"{self.base_url}/task?c[]={cat_id}{f'&page={p}' if p > 1 else ''}"
                )

        # 2. Общая лента заданий
        feed_depth = max(1, depth - 1)
        for p in range(1, feed_depth + 1):
            target_requests.append(
                f"{self.base_url}/task{f'?page={p}' if p > 1 else ''}"
            )

        # 3. Поисковый запрос python
        target_requests.append(f"{self.base_url}/task?q=python")

        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=15.0,
            follow_redirects=True,
        ) as client:
            for url in target_requests:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        logger.warning(
                            "Freelance.ru вернул статус %d для %s",
                            resp.status_code,
                            url,
                        )
                        continue

                    articles = re.findall(
                        r'<article class="task-card[^"]*">(.*?)</article>',
                        resp.text,
                        re.DOTALL,
                    )

                    if not articles:
                        continue

                    for art in articles:
                        order = self._parse_article(art)
                        if order and order.external_id not in seen_ids:
                            seen_ids.add(order.external_id)
                            orders.append(order)

                except Exception as e:
                    logger.error("Ошибка при запросе к Freelance.ru (%s): %s", url, e)

        logger.info(
            "FreelanceRuCollector собрал %d заказов (%s, глубина: %d стр)",
            len(orders),
            "бэкфилл" if cold else "обычный",
            depth,
        )
        return orders
