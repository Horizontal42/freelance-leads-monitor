"""Collector for Kwork freelance exchange."""

from datetime import datetime
import json
import logging
import re
from typing import Any, Dict, List, Optional
import httpx
from src.collectors.base import BaseCollector
from src.config import settings
from src.models.order import RawOrder, SourcePlatform

logger = logging.getLogger(__name__)


class KworkCollector(BaseCollector):
    """Сборщик заказов с биржи Kwork (парсинг серверного JSON stateData с пагинацией)."""

    def __init__(
        self,
        category_ids: Optional[List[int]] = None,
        max_pages: Optional[int] = None,
        include_all_pages: Optional[int] = None,
    ) -> None:
        super().__init__(name="kwork")
        self.category_ids = category_ids or settings.KWORK_CATEGORY_IDS
        self.max_pages = (
            max_pages
            if max_pages is not None
            else getattr(settings, "KWORK_MAX_PAGES", 5)
        )
        self.include_all_pages = (
            include_all_pages
            if include_all_pages is not None
            else getattr(settings, "KWORK_INCLUDE_ALL_PAGES", 3)
        )
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

    def _extract_state_data(self, html: str) -> Optional[Dict[str, Any]]:
        """Извлечь window.stateData из HTML Kwork."""
        marker = "window.stateData"
        idx = html.find(marker)
        if idx == -1:
            return None

        eq_idx = html.find("=", idx)
        if eq_idx == -1:
            return None

        raw = html[eq_idx + 1 :].strip()
        try:
            decoder = json.JSONDecoder()
            data, _ = decoder.raw_decode(raw)
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.warning("Не удалось декодировать stateData Kwork: %s", e)
        return None

    def _parse_order(self, item: Dict[str, Any]) -> Optional[RawOrder]:
        """Преобразовать сырой объект want из Kwork в RawOrder."""
        try:
            order_id = str(item.get("id"))
            title = (item.get("name") or "").strip()
            description = (item.get("description") or "").strip()
            if not order_id or not title:
                return None

            # Бюджет
            price_val = item.get("possiblePriceLimit") or item.get("priceLimit")
            price: Optional[float] = None
            is_negotiable = False

            if price_val is not None:
                try:
                    price = float(price_val)
                    if price <= 0:
                        price = None
                        is_negotiable = True
                except (ValueError, TypeError):
                    price = None
                    is_negotiable = True
            else:
                is_negotiable = True

            # Дата создания
            date_create_str = item.get("date_create")
            created_at = datetime.now()
            if date_create_str:
                try:
                    created_at = datetime.strptime(date_create_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass

            url = f"{settings.KWORK_BASE_URL}/projects/{order_id}"

            # Теги / Категория
            tags: List[str] = []
            category_id = item.get("category_id")
            if category_id:
                tags.append(f"cat:{category_id}")
            kwork_count = item.get("kwork_count")
            if kwork_count is not None:
                tags.append(f"offers:{kwork_count}")

            return RawOrder(
                source=SourcePlatform.KWORK,
                external_id=order_id,
                title=title,
                description=description,
                url=url,
                price=price,
                is_negotiable=is_negotiable,
                tags=tags,
                created_at=created_at,
                raw_payload=item,
            )
        except Exception as e:
            logger.error("Ошибка парсинга элемента Kwork: %s", e)
            return None

    async def fetch_new_orders(self) -> List[RawOrder]:
        """Запросить страницы категорий Kwork с пагинацией и вернуть список заказов."""
        orders: List[RawOrder] = []
        seen_ids = set()

        # Формируем список целевых URL для сбора
        url_targets: List[tuple[str, int]] = [
            (f"{settings.KWORK_BASE_URL}/projects?c={cat_id}", self.max_pages)
            for cat_id in self.category_ids
        ]
        if self.include_all_pages > 0:
            url_targets.append((f"{settings.KWORK_BASE_URL}/projects", self.include_all_pages))

        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=20.0,
            follow_redirects=True,
        ) as client:
            for base_url, max_depth in url_targets:
                page = 1
                while page <= max_depth:
                    sep = "&" if "?" in base_url else "?"
                    page_url = f"{base_url}{sep}page={page}"
                    try:
                        resp = await client.get(page_url)
                        if resp.status_code != 200:
                            logger.warning(
                                "Kwork вернул статус %d для %s",
                                resp.status_code,
                                page_url,
                            )
                            break

                        state_data = self._extract_state_data(resp.text)
                        if not state_data:
                            logger.warning("stateData не найден на странице %s", page_url)
                            break

                        wld = state_data.get("wantsListData", {})
                        wants = wld.get("wants", []) or state_data.get("wants", [])
                        if not wants:
                            break

                        for want in wants:
                            order = self._parse_order(want)
                            if order and order.external_id not in seen_ids:
                                seen_ids.add(order.external_id)
                                orders.append(order)

                        pag = wld.get("pagination", {})
                        last_page = int(pag.get("last_page", 1))
                        if page >= last_page:
                            break
                        page += 1

                    except Exception as e:
                        logger.error("Ошибка при запросе к Kwork (%s): %s", page_url, e)
                        break

        logger.info("KworkCollector собрал %d заказов", len(orders))
        return orders
