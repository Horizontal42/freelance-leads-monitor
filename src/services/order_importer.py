"""Service for importing and analyzing arbitrary orders and vacancies by URL."""

import html
import json
import logging
import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import httpx

from src.analyzer.base import BaseLLMClient
from src.collectors.enricher import OrderEnricher
from src.config import settings
from src.models.order import OrderPriority, OrderStatus, RawOrder, SourcePlatform
from src.storage.repository import OrderRepository

logger = logging.getLogger(__name__)


def strip_html_tags(text: Optional[str]) -> str:
    """Удалить HTML-теги и нормализовать пробелы."""
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html.unescape(clean).split())


class OrderImporterService:
    """Сервис поиска или добавления и анализа заказов/вакансий по произвольной ссылке."""

    def __init__(self, timeout: float = 12.0) -> None:
        self.timeout = timeout
        self.enricher = OrderEnricher(timeout=timeout)
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
        }

    def detect_platform_and_id(self, url: str) -> Tuple[SourcePlatform, str]:
        """Определить биржу/платформу и извлечь идентификатор из URL."""
        clean_url = url.strip()
        parsed = urlparse(clean_url)
        domain = parsed.netloc.lower()
        path = parsed.path

        # 1. HeadHunter (hh.ru, spb.hh.ru, etc.)
        if "hh.ru" in domain or "headhunter.ru" in domain:
            m = re.search(r"/vacancy/(\d+)", path)
            ext_id = m.group(1) if m else str(hash(clean_url))
            return SourcePlatform.HH_RU, ext_id

        # 2. Хабр Карьера (career.habr.com)
        if "career.habr.com" in domain:
            m = re.search(r"/vacancies/(\d+)", path)
            ext_id = m.group(1) if m else str(hash(clean_url))
            return SourcePlatform.HABR_CAREER, ext_id

        # 3. Kwork (kwork.ru)
        if "kwork.ru" in domain:
            m = re.search(r"/projects/(\d+)", path)
            ext_id = m.group(1) if m else str(hash(clean_url))
            return SourcePlatform.KWORK, ext_id

        # 4. FL.ru (fl.ru)
        if "fl.ru" in domain:
            m = re.search(r"/projects/(\d+)", path)
            ext_id = m.group(1) if m else str(hash(clean_url))
            return SourcePlatform.FL_RU, ext_id

        # 5. Freelance.ru (freelance.ru)
        if "freelance.ru" in domain:
            m = re.search(r"/(?:tasks|projects)/(\d+)", path) or re.search(r"(\d+)(?:\.html)?$", path)
            ext_id = m.group(1) if m else str(hash(clean_url))
            return SourcePlatform.FREELANCE_RU, ext_id

        # 6. Pchel.net (pchel.net)
        if "pchel.net" in domain:
            m = re.search(r"/jobs/(\d+)", path) or re.search(r"(\d+)(?:\.html)?$", path)
            ext_id = m.group(1) if m else str(hash(clean_url))
            return SourcePlatform.PCHEL_NET, ext_id

        # Fallback: пользовательская или неизвестная ссылка
        slug = path.strip("/").split("/")[-1]
        ext_id = slug if slug else str(hash(clean_url))
        return SourcePlatform.CUSTOM, ext_id

    async def fetch_raw_order(self, url: str) -> RawOrder:
        """Загрузить и распарсить страницу по ссылке в RawOrder."""
        platform, ext_id = self.detect_platform_and_id(url)
        clean_url = url.strip()

        if platform == SourcePlatform.HH_RU:
            return await self._fetch_hh_ru(clean_url, ext_id)
        elif platform == SourcePlatform.KWORK:
            return await self._fetch_kwork(clean_url, ext_id)
        elif platform == SourcePlatform.HABR_CAREER:
            return await self._fetch_habr_career(clean_url, ext_id)
        elif platform == SourcePlatform.FL_RU:
            return await self._fetch_fl_ru(clean_url, ext_id)
        elif platform == SourcePlatform.FREELANCE_RU:
            return await self._fetch_freelance_ru(clean_url, ext_id)
        elif platform == SourcePlatform.PCHEL_NET:
            return await self._fetch_pchel_net(clean_url, ext_id)
        else:
            return await self._fetch_generic(clean_url, ext_id)

    async def _fetch_hh_ru(self, url: str, ext_id: str) -> RawOrder:
        """Спарсить вакансию с HeadHunter (через JSON-LD и HTML)."""
        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise RuntimeError(f"Ошибка загрузки вакансии hh.ru (HTTP {resp.status_code})")
            html_text = resp.text

        title = "Вакансия"
        description = ""
        company = ""
        price = None
        is_negotiable = True

        # 1. Извлечение из JSON-LD Schema (JobPosting)
        for j in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html_text, re.DOTALL):
            try:
                data = json.loads(j)
                if data.get("@type") == "JobPosting":
                    title = data.get("title", title)
                    description = strip_html_tags(data.get("description", ""))
                    company = data.get("hiringOrganization", {}).get("name", "")
                    base_sal = data.get("baseSalary")
                    if isinstance(base_sal, dict):
                        val = base_sal.get("value", {})
                        if isinstance(val, dict):
                            num_val = val.get("value") or val.get("maxValue") or val.get("minValue")
                            if num_val:
                                price = float(num_val)
                                is_negotiable = False
            except Exception:
                pass

        # 2. Поиск зарплаты в HTML
        m_sal = re.search(r'data-qa="vacancy-salary-compensation-type-net"[^>]*>(.*?)</span>', html_text) or \
                re.search(r'data-qa="vacancy-salary"[^>]*>(.*?)</span>', html_text)
        sal_text = strip_html_tags(m_sal.group(1)) if m_sal else ""

        if sal_text and price is None:
            # Извлекаем числа из строки зарплаты
            nums = [int(n.replace(" ", "").replace("\xa0", "")) for n in re.findall(r"\d[\d\s\xa0]+", sal_text)]
            if nums:
                price = float(max(nums))
                is_negotiable = False

        # 3. Извлечение ключевых навыков
        skills = [strip_html_tags(m) for m in re.findall(r'data-qa="bloko-tag__text"[^>]*>(.*?)</span>', html_text)]

        # 4. Формирование мета-информации
        meta_parts = []
        if company:
            meta_parts.append(f"🏢 Компания: {company}")
        if sal_text:
            meta_parts.append(f"💰 Зарплата: {sal_text}")
        if skills:
            meta_parts.append(f"🔑 Навыки: {', '.join(skills)}")

        attachments_text = "\n".join(meta_parts) if meta_parts else None

        return RawOrder(
            source=SourcePlatform.HH_RU,
            external_id=ext_id,
            title=title,
            description=description,
            url=url,
            price=price,
            is_negotiable=is_negotiable,
            tags=skills,
            attachments_text=attachments_text,
        )

    async def _fetch_kwork(self, url: str, ext_id: str) -> RawOrder:
        """Спарсить заказ с Kwork."""
        target_url = f"https://kwork.ru/projects/{ext_id}/view"
        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(target_url)
            if resp.status_code != 200:
                raise RuntimeError(f"Ошибка загрузки проекта Kwork (HTTP {resp.status_code})")
            html_text = resp.text

        title = "Заказ на Kwork"
        description = ""
        price = None
        is_negotiable = True

        # Поиск window.stateData или embedded JSON
        m = re.search(r'"description":"(.*?)","files"', html_text)
        if m:
            try:
                description = json.loads(f'"{m.group(1)}"')
            except Exception:
                description = m.group(1)

        m_name = re.search(r'"name":"(.*?)","max_days"', html_text)
        if m_name:
            try:
                title = json.loads(f'"{m_name.group(1)}"')
            except Exception:
                title = m_name.group(1)

        m_price = re.search(r'"priceLimit":"([\d\.]+)"', html_text)
        if m_price:
            try:
                price = float(m_price.group(1))
                is_negotiable = False
            except Exception:
                pass

        return RawOrder(
            source=SourcePlatform.KWORK,
            external_id=ext_id,
            title=title or f"Kwork #{ext_id}",
            description=description,
            url=target_url,
            price=price,
            is_negotiable=is_negotiable,
        )

    async def _fetch_habr_career(self, url: str, ext_id: str) -> RawOrder:
        """Спарсить вакансию с Хабр Карьеры."""
        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise RuntimeError(f"Ошибка загрузки вакансии Хабр Карьера (HTTP {resp.status_code})")
            html_text = resp.text

        m_title = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.DOTALL)
        title = strip_html_tags(m_title.group(1)) if m_title else f"Вакансия #{ext_id}"

        m_desc = re.search(
            r'<div class="[^"]*(?:vacancy-description|style-ugc)[^"]*"[^>]*>(.*?)</div>',
            html_text,
            re.DOTALL,
        )
        description = strip_html_tags(m_desc.group(1)) if m_desc else ""

        # Зарплата
        m_sal = re.search(r'<div class="[^"]*basic-salary[^"]*"[^>]*>(.*?)</div>', html_text, re.DOTALL)
        sal_text = strip_html_tags(m_sal.group(1)) if m_sal else ""
        price = None
        is_negotiable = True
        if sal_text:
            nums = [int(n.replace(" ", "")) for n in re.findall(r"\d[\d\s]+", sal_text)]
            if nums:
                price = float(max(nums))
                is_negotiable = False

        # Компания
        m_comp = re.search(r'<div class="[^"]*vacancy-company[^"]*"[^>]*>(.*?)</div>', html_text, re.DOTALL)
        company = strip_html_tags(m_comp.group(1)) if m_comp else ""

        meta_parts = []
        if company:
            meta_parts.append(f"🏢 Компания: {company}")
        if sal_text:
            meta_parts.append(f"💰 Зарплата: {sal_text}")

        return RawOrder(
            source=SourcePlatform.HABR_CAREER,
            external_id=ext_id,
            title=title,
            description=description,
            url=url,
            price=price,
            is_negotiable=is_negotiable,
            attachments_text="\n".join(meta_parts) if meta_parts else None,
        )

    async def _fetch_fl_ru(self, url: str, ext_id: str) -> RawOrder:
        """Спарсить проект с FL.ru."""
        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise RuntimeError(f"Ошибка загрузки проекта FL.ru (HTTP {resp.status_code})")
            html_text = resp.text

        m_title = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.DOTALL)
        title = strip_html_tags(m_title.group(1)) if m_title else f"Проект #{ext_id}"

        m_desc = re.search(r'<div class="[^"]*b-layout__txt[^"]*"[^>]*>(.*?)</div>', html_text, re.DOTALL)
        description = strip_html_tags(m_desc.group(1)) if m_desc else ""

        price = None
        is_negotiable = True
        m_price = re.search(r'class="[^"]*price[^"]*"[^>]*>(.*?)</div>', html_text, re.DOTALL)
        if m_price:
            p_text = strip_html_tags(m_price.group(1))
            nums = [int(n.replace(" ", "")) for n in re.findall(r"\d[\d\s]+", p_text)]
            if nums:
                price = float(max(nums))
                is_negotiable = False

        is_pro = "только для pro" in html_text.lower() or "платный проект" in html_text.lower()

        return RawOrder(
            source=SourcePlatform.FL_RU,
            external_id=ext_id,
            title=title,
            description=description,
            url=url,
            price=price,
            is_negotiable=is_negotiable,
            is_pro_only=is_pro,
        )

    async def _fetch_freelance_ru(self, url: str, ext_id: str) -> RawOrder:
        """Спарсить проект с Freelance.ru."""
        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise RuntimeError(f"Ошибка загрузки проекта Freelance.ru (HTTP {resp.status_code})")
            html_text = resp.text

        m_title = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.DOTALL)
        title = strip_html_tags(m_title.group(1)) if m_title else f"Заказ #{ext_id}"

        m_desc = re.search(r'<div class="[^"]*description[^"]*"[^>]*>(.*?)</div>', html_text, re.DOTALL)
        description = strip_html_tags(m_desc.group(1)) if m_desc else ""

        price = None
        is_negotiable = True
        m_price = re.search(r'class="[^"]*cost[^"]*"[^>]*>(.*?)</div>', html_text, re.DOTALL)
        if m_price:
            p_text = strip_html_tags(m_price.group(1))
            nums = [int(n.replace(" ", "")) for n in re.findall(r"\d[\d\s]+", p_text)]
            if nums:
                price = float(max(nums))
                is_negotiable = False

        return RawOrder(
            source=SourcePlatform.FREELANCE_RU,
            external_id=ext_id,
            title=title,
            description=description,
            url=url,
            price=price,
            is_negotiable=is_negotiable,
        )

    async def _fetch_pchel_net(self, url: str, ext_id: str) -> RawOrder:
        """Спарсить проект с Pchel.net."""
        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise RuntimeError(f"Ошибка загрузки проекта Pchel.net (HTTP {resp.status_code})")
            html_text = resp.text

        m_title = re.search(r"<h1[^>]*>(.*?)</h1>", html_text, re.DOTALL)
        title = strip_html_tags(m_title.group(1)) if m_title else f"Заказ #{ext_id}"

        m_desc = re.search(r'<div class="[^"]*project-description[^"]*"[^>]*>(.*?)</div>', html_text, re.DOTALL)
        description = strip_html_tags(m_desc.group(1)) if m_desc else ""

        return RawOrder(
            source=SourcePlatform.PCHEL_NET,
            external_id=ext_id,
            title=title,
            description=description,
            url=url,
        )

    async def _fetch_generic(self, url: str, ext_id: str) -> RawOrder:
        """Спарсить любую общую страницу по ссылке."""
        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True) as client:
            resp = await client.get(url)
            html_text = resp.text

        m_title = re.search(r"<title>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
        title = strip_html_tags(m_title.group(1)) if m_title else "Внешний заказ"

        # Извлекаем текст из body
        m_body = re.search(r"<body[^>]*>(.*?)</body>", html_text, re.IGNORECASE | re.DOTALL)
        body_text = m_body.group(1) if m_body else html_text
        clean_text = strip_html_tags(body_text)

        return RawOrder(
            source=SourcePlatform.CUSTOM,
            external_id=ext_id,
            title=title[:100],
            description=clean_text[:5000],
            url=url,
        )

    async def import_or_lookup(
        self,
        url: str,
        repo: OrderRepository,
        llm_client: BaseLLMClient,
    ) -> Dict[str, Any]:
        """Найти заказ по ссылке в БД или скачать, проанализировать и сохранить."""
        if not url or not url.strip().startswith("http"):
            return {
                "ok": False,
                "error": "Укажите корректную ссылку, начинающуюся с http:// или https://",
            }

        clean_url = url.strip()
        platform, ext_id = self.detect_platform_and_id(clean_url)

        # 1. Поиск в существующей базе
        existing = await repo.find_by_url_or_external_id(platform.value, ext_id, clean_url)
        if existing:
            logger.info("Заказ по ссылке %s уже найден в базе (ID: %s)", clean_url, existing["id"])
            return {
                "ok": True,
                "status": "found",
                "order": existing,
                "message": f"Найдено в базе данных (ID #{existing['id']})",
            }

        # 2. Скачивание и парсинг страницы
        logger.info("Заказ %s отсутствует в базе. Запуск загрузки со страницы...", clean_url)
        try:
            raw_order = await self.fetch_raw_order(clean_url)
        except Exception as e:
            logger.error("Ошибка парсинга страницы %s: %s", clean_url, e)
            return {
                "ok": False,
                "error": f"Не удалось загрузить данные по ссылке: {e}",
            }

        # 3. Дополнительное обогащение ТЗ и файлов (если применимо)
        try:
            raw_order = await self.enricher.enrich(raw_order)
        except Exception as e:
            logger.warning("Ошибка обогащения заказа %s: %s", clean_url, e)

        # 4. Запуск AI-анализа через LLM
        logger.info("Запуск анализа вакансии/заказа в LLM: '%s'...", raw_order.title[:40])
        try:
            analysis = await llm_client.analyze_order(raw_order)
            order_id = await repo.insert_raw_order(
                order=raw_order,
                status=OrderStatus.ANALYZED,
                priority=analysis.priority,
            )
            await repo.update_analysis(
                order_id=order_id,
                analysis=analysis,
                status=OrderStatus.ANALYZED,
            )
        except Exception as e:
            logger.error("Ошибка при AI-анализе заказа: %s", e)
            order_id = await repo.insert_raw_order(
                order=raw_order,
                status=OrderStatus.NEW,
                priority=OrderPriority.NORMAL,
                filter_reason=f"Ручной импорт (ошибка LLM: {e})",
            )

        saved_order = await repo.get_by_id(order_id)
        return {
            "ok": True,
            "status": "created",
            "order": saved_order,
            "message": f"Заказ успешно добавлен в базу и проанализирован (ID #{order_id})",
        }
