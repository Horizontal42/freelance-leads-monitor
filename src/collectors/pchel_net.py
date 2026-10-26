"""Collector for Pchel.net (Freelance.today) programming jobs."""

from datetime import datetime
import html
import logging
import re
from typing import List, Optional
import httpx
from src.collectors.base import BaseCollector
from src.models.order import RawOrder, SourcePlatform

logger = logging.getLogger(__name__)

# Примерный курс доллара для конвертации бюджета с Pchel.net в рубли
DEFAULT_USD_RUB_RATE = 95.0


class PchelNetCollector(BaseCollector):
    """Сборщик IT-заказов с биржи Pchel.net (раздел Программирование)."""

    def __init__(
        self,
        base_url: str = "https://pchel.net",
        usd_rate: float = DEFAULT_USD_RUB_RATE,
    ) -> None:
        super().__init__(name="pchel_net")
        self.base_url = base_url.rstrip("/")
        self.usd_rate = usd_rate
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }

    def _parse_block(self, block_html: str) -> Optional[RawOrder]:
        """Распарсить блок проекта из списка Pchel.net."""
        try:
            # 1. Заголовок и ссылка
            m_title = re.search(
                r'<div class="project-title">.*?<a href="([^"]+)"[^>]*>(.*?)</a>',
                block_html,
                re.DOTALL,
            )
            if not m_title:
                return None

            path = m_title.group(1)
            title = html.unescape(m_title.group(2)).strip()
            url = f"{self.base_url}{path}" if path.startswith("/") else path

            # 2. Извлечение ID из ссылки вида /jobs/programming/...-1625258/
            m_id = re.search(r"-(\d+)/", url)
            external_id = m_id.group(1) if m_id else url.strip("/").split("/")[-1]

            # 3. Описание
            m_desc = re.search(
                r'<div class="project-text">(.*?)</div>',
                block_html,
                re.DOTALL,
            )
            description = ""
            if m_desc:
                raw_desc = m_desc.group(1)
                clean_desc = re.sub(r"<[^>]+>", " ", raw_desc)
                description = html.unescape(clean_desc).strip()

            # 4. Бюджет (часто в долларах $ или рублях)
            m_price = re.search(r'<div class="price">([^<]+)</div>', block_html)
            price_str = m_price.group(1).strip() if m_price else ""

            price: Optional[float] = None
            is_negotiable = False

            if "$" in price_str:
                # Извлекаем доллары и переводим в рубли
                digits = re.search(r"(\d+[\d\s]*)", price_str)
                if digits:
                    usd_val = float(re.sub(r"\s+", "", digits.group(1)))
                    price = round(usd_val * self.usd_rate, 2)
            elif any(c in price_str.lower() for c in ["руб", "р\b", "₽"]):
                digits = re.search(r"(\d+[\d\s]*)", price_str)
                if digits:
                    price = float(re.sub(r"\s+", "", digits.group(1)))
            else:
                is_negotiable = True

            return RawOrder(
                source=SourcePlatform.PCHEL_NET,
                external_id=external_id,
                title=title,
                description=description,
                url=url,
                price=price,
                is_negotiable=is_negotiable,
                tags=["programming"],
                created_at=datetime.now(),
                raw_payload={"price_raw": price_str},
            )

        except Exception as e:
            logger.error("Ошибка парсинга блока Pchel.net: %s", e)
            return None

    async def fetch_new_orders(self) -> List[RawOrder]:
        """Собрать свежие проекты из категории Программирование."""
        orders: List[RawOrder] = []
        target_url = f"{self.base_url}/jobs/programming/"

        async with httpx.AsyncClient(
            headers=self.headers,
            timeout=15.0,
            follow_redirects=True,
        ) as client:
            try:
                resp = await client.get(target_url)
                if resp.status_code != 200:
                    logger.warning("Pchel.net вернул статус %d", resp.status_code)
                    return []

                blocks = re.findall(
                    r'<div class="project-block-cont">(.*?)</div>\s*</div>\s*</div>',
                    resp.text,
                    re.DOTALL,
                )

                for b in blocks:
                    order = self._parse_block(b)
                    if order:
                        orders.append(order)

            except Exception as e:
                logger.error("Ошибка при запросе к Pchel.net (%s): %s", target_url, e)

        logger.info("PchelNetCollector собрал %d заказов", len(orders))
        return orders
