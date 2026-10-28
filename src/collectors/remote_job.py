"""Collector for Remote-job.ru freelance projects."""

from datetime import datetime
import html
import logging
import re
from typing import List, Optional
import httpx
from src.collectors.base import BaseCollector
from src.models.order import RawOrder, SourcePlatform

logger = logging.getLogger(__name__)


class RemoteJobCollector(BaseCollector):
    """Сборщик проектов с площадки Remote-job.ru (раздел заданий)."""

    def __init__(
        self,
        base_url: str = "https://remote-job.ru",
        normal_pages: Optional[int] = None,
        backfill_pages: Optional[int] = None,
    ) -> None:
        super().__init__(name="remote_job")
        self.base_url = base_url.rstrip("/")
        self.feed_url = f"{self.base_url}/search?search%5BsearchType%5D=project"
        from src.config import settings
        self.normal_pages = (
            normal_pages
            if normal_pages is not None
            else getattr(settings, "REMOTE_JOB_NORMAL_PAGES", 1)
        )
        self.backfill_pages = (
            backfill_pages
            if backfill_pages is not None
            else getattr(settings, "REMOTE_JOB_BACKFILL_PAGES", 3)
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

    def _parse_card(self, card_html: str) -> Optional[RawOrder]:
        """Распарсить карточку заказа <div class="vacancy_item">...</div>."""
        try:
            # 1. Ссылка, ID и заголовок
            m_link = re.search(
                r'href=[\"\'](/project_work/project_show/(\d+)/[^\"]*)[\"\']\s*>\s*([^<]+)</a>',
                card_html,
                re.DOTALL,
            )
            if not m_link:
                return None

            path, external_id, raw_title = m_link.groups()
            title = (
                html.unescape(raw_title)
                .replace("(Дистанционная работа)", "")
                .strip()
            )
            url = f"{self.base_url}{path}" if path.startswith("/") else path

            # 2. Описание
            m_desc = re.search(
                r'<div class="col-xs-12[^\"]*text-left\">(.*?)</div>',
                card_html,
                re.DOTALL,
            )
            description = ""
            if m_desc:
                raw_desc = m_desc.group(1)
                clean_desc = re.sub(r"<[^>]+>", " ", raw_desc)
                description = html.unescape(re.sub(r"\s+", " ", clean_desc)).strip()

            # 3. Бюджет
            m_budget = re.search(r"<h3>(.*?)</h3>", card_html, re.DOTALL)
            budget_raw = (
                re.sub(r"\s+", " ", m_budget.group(1)).strip() if m_budget else ""
            )

            is_negotiable = (
                "не указан" in budget_raw.lower()
                or "договор" in budget_raw.lower()
                or not budget_raw
            )

            price: Optional[float] = None
            if not is_negotiable:
                digits = re.search(r"(\d[\d\s]*)\s*(?:руб|р\b|₽)", budget_raw, re.IGNORECASE)
                if digits:
                    try:
                        price = float(re.sub(r"\s+", "", digits.group(1)))
                    except ValueError:
                        price = None
                        is_negotiable = True
                else:
                    is_negotiable = True

            return RawOrder(
                source=SourcePlatform.REMOTE_JOB,
                external_id=external_id,
                title=title,
                description=description,
                url=url,
                price=price,
                is_negotiable=is_negotiable,
                tags=["project", "remote"],
                created_at=datetime.now(),
            )
        except Exception as e:
            logger.warning(
                "Ошибка парсинга карточки Remote-job: %s", e, exc_info=True
            )
            return None

    async def fetch_new_orders(self, is_cold_start: Optional[bool] = None) -> List[RawOrder]:
        """Получить свежие заказы с remote-job.ru с поддержкой бэкфилла."""
        cold = self._is_first_run if is_cold_start is None else is_cold_start
        self._is_first_run = False
        depth = self.backfill_pages if cold else self.normal_pages

        orders: List[RawOrder] = []
        seen_ids = set()

        try:
            async with httpx.AsyncClient(
                headers=self.headers, timeout=12.0, follow_redirects=True
            ) as client:
                for page in range(1, depth + 1):
                    page_url = (
                        self.feed_url
                        if page == 1
                        else f"{self.feed_url}&page={page}"
                    )
                    resp = await client.get(page_url)
                    if resp.status_code != 200:
                        logger.warning(
                            "Remote-job вернул HTTP %s для %s",
                            resp.status_code,
                            page_url,
                        )
                        break

                    cards = re.findall(
                        r'<div class="vacancy_item">(.*?)</div>\s*<hr>',
                        resp.text,
                        re.DOTALL,
                    )

                    if not cards:
                        break

                    for card in cards:
                        order = self._parse_card(card)
                        if order and order.external_id not in seen_ids:
                            seen_ids.add(order.external_id)
                            orders.append(order)

            logger.info(
                "Remote-job: собрано %d заказов (%s, глубина: %d стр)",
                len(orders),
                "бэкфилл" if cold else "обычный",
                depth,
            )
        except httpx.RequestError as e:
            logger.warning("Сетевая ошибка при запросе к Remote-job: %s", e)
        except Exception as e:
            logger.error(
                "Непредвиденная ошибка в RemoteJobCollector: %s", e, exc_info=True
            )

        return orders
