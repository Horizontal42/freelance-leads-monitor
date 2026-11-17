"""Collector for Avito vacancies and service orders."""

import json
import logging
import re
from typing import Any, Dict, List, Optional
import feedparser
import httpx
from src.collectors.base import BaseCollector
from src.config import settings
from src.models.order import RawOrder, SourcePlatform

logger = logging.getLogger(__name__)


class AvitoCollector(BaseCollector):
    """Сборщик вакансий и заказов на услуги с площадки Авито (Avito.ru).

    Поддерживает:
    1. Сбор через внешние RSS/Atom фиды (Web-to-RSS, шлюзы алертов, RSS-мосты).
    2. Прямой опрос поисковой выдачи Авито с защитой от сбоев фаервола QRATOR.
    """

    def __init__(
        self,
        base_url: Any = "https://www.avito.ru",
        timeout: float = 15.0,
        repo: Optional[Any] = None,
    ) -> None:
        super().__init__(name="avito")
        if hasattr(base_url, "base_url"):
            self.base_url = str(base_url.base_url).rstrip("/")
        else:
            self.base_url = str(base_url).rstrip("/")
        self.timeout = timeout
        self.repo = repo
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "application/json,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://www.avito.ru/",
        }

    def _extract_id_from_url(self, url: str) -> str:
        """Извлечь уникальный идентификатор объявления из ссылки Авито."""
        m = re.search(r"_(\d+)(?:\?|$)", url)
        if m:
            return m.group(1)
        m2 = re.search(r"/(\d+)(?:\?|$)", url)
        if m2:
            return m2.group(1)
        clean = url.rstrip("/").split("/")[-1].split("?")[0]
        return clean or str(hash(url))

    def _parse_feed(self, feed_text: str, source_url: str) -> List[RawOrder]:
        """Разобрать RSS/Atom фид объявлений Авито."""
        orders: List[RawOrder] = []
        parsed = feedparser.parse(feed_text)

        for entry in parsed.entries:
            link = getattr(entry, "link", "")
            title = getattr(entry, "title", "").strip()
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            ext_id = self._extract_id_from_url(link) or getattr(entry, "id", "")

            if not title or not link:
                continue

            # Попытка извлечь цену/зарплату из заголовка или описания
            price = None
            price_match = re.search(r"(\d[\d\s]{2,})\s*(?:₽|руб|rub)", f"{title} {summary}", re.IGNORECASE)
            if price_match:
                try:
                    price = float(price_match.group(1).replace(" ", "").replace("\xa0", ""))
                except ValueError:
                    price = None

            is_vacancy = (
                "vakansi" in link.lower()
                or "ваканси" in link.lower()
                or "rabota" in link.lower()
                or "работа" in title.lower()
                or "ваканси" in title.lower()
            )
            tags = ["avito", "vacancy" if is_vacancy else "service"]

            orders.append(
                RawOrder(
                    source=SourcePlatform.AVITO,
                    external_id=str(ext_id),
                    title=title,
                    description=summary.strip() or title,
                    url=link,
                    price=price,
                    tags=tags,
                )
            )

        return orders

    def _parse_html_listings(self, html_text: str, base_url: str) -> List[RawOrder]:
        """Извлечь объявления из HTML-страницы Авито (включая JSON-LD и state)."""
        orders: List[RawOrder] = []

        # 1. Поиск schema.org микроразметки (JobPosting / Product / Offer)
        ld_matches = re.findall(r'<script\s+type=["\']application/ld\+json["\']>(.*?)</script>', html_text, re.DOTALL)
        for ld_raw in ld_matches:
            try:
                data = json.loads(ld_raw.strip())
                items = data if isinstance(data, list) else [data]
                for it in items:
                    it_type = it.get("@type", "")
                    if it_type in ("JobPosting", "Product", "Offer"):
                        title = it.get("title") or it.get("name")
                        desc = it.get("description") or ""
                        url = it.get("url") or base_url
                        ext_id = self._extract_id_from_url(url)

                        price = None
                        if "baseSalary" in it and isinstance(it["baseSalary"], dict):
                            val = it["baseSalary"].get("value")
                            if isinstance(val, dict):
                                price = float(val.get("value") or val.get("minValue") or 0)
                            elif isinstance(val, (int, float)):
                                price = float(val)

                        if title and ext_id:
                            orders.append(
                                RawOrder(
                                    source=SourcePlatform.AVITO,
                                    external_id=str(ext_id),
                                    title=title.strip(),
                                    description=desc.strip() or title.strip(),
                                    url=url,
                                    price=price,
                                    tags=["avito", "vacancy" if it_type == "JobPosting" else "service"],
                                )
                            )
            except Exception as e:
                logger.debug("Ошибка разбора JSON-LD Авито: %s", e)

        # 2. Поиск данных в современных SSR-скриптах Авито (loaderData -> catalog/recommendationsInfinite)
        if not orders:
            for s in re.findall(r'<script[^>]*>(.*?)</script>', html_text, re.DOTALL):
                s_clean = s.strip()
                if '"loaderData"' in s_clean and ('"catalog"' in s_clean or '"items"' in s_clean):
                    try:
                        data = json.loads(s_clean)
                        d = data.get("loaderData", {}).get("data", {})
                        items = (
                            d.get("catalog", {}).get("items")
                            or d.get("recommendationsInfinite", {}).get("items")
                            or []
                        )
                        for item in items:
                            ext_id = str(item.get("id") or "")
                            title = (item.get("title") or "").strip()
                            url_path = item.get("urlPath") or ""
                            if not title or not ext_id:
                                continue

                            full_url = (
                                f"https://www.avito.ru{url_path}"
                                if url_path.startswith("/")
                                else url_path
                            )

                            price = None
                            price_det = item.get("priceDetailed") or {}
                            val = price_det.get("value")
                            if val and float(val) > 0:
                                price = float(val)
                            else:
                                p_str = price_det.get("string") or ""
                                p_match = re.search(r"(\d[\d\s]*)\s*(?:₽|руб)", p_str)
                                if p_match:
                                    try:
                                        price = float(
                                            p_match.group(1).replace(" ", "").replace("\xa0", "")
                                        )
                                    except ValueError:
                                        price = None

                            location_name = (item.get("location") or {}).get("name") or ""
                            tags = ["avito"]
                            if location_name:
                                tags.append(location_name)

                            orders.append(
                                RawOrder(
                                    source=SourcePlatform.AVITO,
                                    external_id=ext_id,
                                    title=title,
                                    description=title,
                                    url=full_url.split("?")[0],
                                    price=price,
                                    tags=tags,
                                )
                            )
                        if orders:
                            break
                    except Exception as e:
                        logger.debug("Ошибка парсинга SSR скрипта Авито: %s", e)

        # 3. Поиск карточек объявлений в HTML по data-marker="item"
        if not orders:
            item_blocks = re.findall(r'<div[^>]*data-marker=["\']item["\'][^>]*>(.*?)</div>\s*</div>', html_text, re.DOTALL)
            for block in item_blocks:
                link_m = re.search(r'<a[^>]*href=["\'](/[^"\']+)["\'][^>]*title=["\']([^"\']+)["\']', block)
                if not link_m:
                    link_m = re.search(r'<a[^>]*title=["\']([^"\']+)["\'][^>]*href=["\'](/[^"\']+)["\']', block)
                    if link_m:
                        title, rel_url = link_m.group(1), link_m.group(2)
                    else:
                        continue
                else:
                    rel_url, title = link_m.group(1), link_m.group(2)

                full_url = f"https://www.avito.ru{rel_url}" if rel_url.startswith("/") else rel_url
                ext_id = self._extract_id_from_url(full_url)

                price = None
                p_match = re.search(r'itemprop=["\']price["\'][^>]*content=["\'](\d+)["\']', block)
                if p_match:
                    try:
                        price = float(p_match.group(1))
                    except ValueError:
                        price = None

                orders.append(
                    RawOrder(
                        source=SourcePlatform.AVITO,
                        external_id=str(ext_id),
                        title=title.strip(),
                        description=title.strip(),
                        url=full_url,
                        price=price,
                        tags=["avito"],
                    )
                )

        return orders

    async def fetch_new_orders(self, is_cold_start: Optional[bool] = None) -> List[RawOrder]:
        """Собрать свежие объявления с Авито (через RSS-ленты или поисковую выдачу)."""
        config = getattr(settings, "COLLECTORS_AVITO", None)
        if config and not getattr(config, "enabled", True):
            logger.info("Авито отключен в конфигурации.")
            return []

        all_orders: List[RawOrder] = []
        seen_ids = set()

        feed_urls: List[str] = getattr(config, "feed_urls", []) if config else []
        search_queries: List[str] = getattr(config, "search_queries", []) if config else [
            "sankt-peterburg/vakansii",
            "sankt-peterburg/predlozheniya_uslug",
        ]

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True) as client:
            # 1. Сбор через внешние RSS/Atom фиды (если настроены)
            for feed_url in feed_urls:
                try:
                    resp = await client.get(feed_url)
                    if resp.status_code == 200:
                        feed_orders = self._parse_feed(resp.text, feed_url)
                        for o in feed_orders:
                            if o.external_id not in seen_ids:
                                seen_ids.add(o.external_id)
                                all_orders.append(o)
                    else:
                        logger.warning("Авито RSS фид %s вернул статус %d", feed_url, resp.status_code)
                except Exception as e:
                    logger.warning("Ошибка опроса Авито RSS фида %s: %s", feed_url, e)

            # 2. Опрос поисковых страниц Авито
            for query in search_queries:
                url = query if query.startswith("http") else f"{self.base_url}/{query.lstrip('/')}"
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        # Проверяем на фаервол в ответе
                        if "Доступ ограничен" in resp.text or "firewall" in resp.text:
                            logger.debug("Авито: страница %s содержит блокировку фаервола QRATOR.", url)
                            continue

                        parsed = self._parse_html_listings(resp.text, url)
                        for o in parsed:
                            if o.external_id not in seen_ids:
                                seen_ids.add(o.external_id)
                                all_orders.append(o)
                    elif resp.status_code in (429, 439):
                        logger.debug(
                            "Авито: доступ ограничен фаерволом QRATOR (HTTP %d). Для прямого сбора настройте RSS-фид или прокси.",
                            resp.status_code,
                        )
                    else:
                        logger.warning("Авито вернул статус %d для %s", resp.status_code, url)
                except Exception as e:
                    logger.debug("Ошибка опроса Авито %s: %s", url, e)

        if all_orders:
            logger.info("AvitoCollector собрал %d объявлений/вакансий", len(all_orders))
        return all_orders
