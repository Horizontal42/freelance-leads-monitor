"""Order detail enricher: extracts complete task text and attached files before LLM analysis."""

import html
import logging
import os
import re
from typing import List, Optional
import httpx
from src.models.order import RawOrder, SourcePlatform

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {
    ".txt", ".md", ".json", ".csv", ".py", ".sql", ".log",
    ".yml", ".yaml", ".xml", ".html", ".sh", ".env", ".cfg", ".ini",
}
MAX_FILE_BYTES = 50 * 1024  # 50 KB max per file content


class OrderEnricher:
    """Обогатитель заказов: выгружает полное ТЗ со страницы проекта и содержимое прикрепленных файлов."""

    def __init__(self, timeout: float = 12.0) -> None:
        self.timeout = timeout
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
        }

    async def enrich(self, order: RawOrder) -> RawOrder:
        """Выгрузить полное ТЗ и файлы для заказа, передавая готовый текст для LLM."""
        try:
            if order.source == SourcePlatform.KWORK:
                await self._enrich_kwork(order)
            elif order.source == SourcePlatform.FL_RU:
                await self._enrich_fl_ru(order)
            elif order.source == SourcePlatform.FREELANCE_RU:
                await self._enrich_freelance_ru(order)
            elif order.source == SourcePlatform.PCHEL_NET:
                await self._enrich_pchel_net(order)
            elif order.source == SourcePlatform.REMOTE_JOB:
                await self._enrich_remote_job(order)
            elif order.source == SourcePlatform.HH_RU:
                await self._enrich_hh_ru(order)
        except Exception as e:
            logger.warning(
                "Не удалось обогатить заказ [%s #%s] деталями: %s. Используется исходное описание.",
                order.source.value,
                order.external_id,
                e,
            )
        return order

    async def _enrich_kwork(self, order: RawOrder) -> None:
        """Kwork: описание уже полное из stateData; обрабатываем прикрепленные файлы."""
        if not order.raw_payload:
            return

        files = order.raw_payload.get("files", [])
        if not files:
            return

        attachments: List[str] = []
        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout) as client:
            for f in files:
                fname = f.get("fname") or "unnamed_file"
                furl = f.get("url") or ""
                fsize = f.get("size") or 0
                size_str = f"{fsize} байт" if fsize else "размер не указан"
                ext = os.path.splitext(fname)[1].lower()

                if ext in TEXT_EXTENSIONS and furl:
                    try:
                        resp = await client.get(furl, follow_redirects=True)
                        if resp.status_code == 200 and not resp.text.strip().startswith("<!DOCTYPE"):
                            content_sample = resp.text[:MAX_FILE_BYTES].strip()
                            attachments.append(
                                f"[Файл: {fname} ({size_str})]\n"
                                f"--- Начало содержимого файла ---\n"
                                f"{content_sample}\n"
                                f"--- Конец содержимого файла ---"
                            )
                            continue
                    except Exception as e:
                        logger.debug("Не удалось скачать файл Kwork %s: %s", fname, e)

                attachments.append(f"[Прикрепленный файл: {fname} ({size_str})]")

        if attachments:
            order.attachments_text = "\n\n".join(attachments)

    async def _enrich_fl_ru(self, order: RawOrder) -> None:
        """FL.ru: выгружаем полное ТЗ со страницы проекта и ссылки на файлы."""
        if not order.url or not order.url.startswith("http"):
            return

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout) as client:
            resp = await client.get(order.url, follow_redirects=True)
            if resp.status_code != 200:
                return

            html_text = resp.text

            # 1. Полное описание
            m_desc = re.search(r"<div[^>]*id=\"projectp\d+\"[^>]*>(.*?)</div>", html_text, re.DOTALL)
            if not m_desc:
                m_desc = re.search(r"class=\"b-layout__txt[^>]*\">(.*?)</div>", html_text, re.DOTALL)

            if m_desc:
                clean = re.sub(r"<[^>]+>", " ", m_desc.group(1))
                full_text = html.unescape(re.sub(r"\s+", " ", clean)).strip()
                if len(full_text) > len(order.description):
                    order.description = full_text

            # 2. Файлы
            file_matches = re.findall(
                r"<a[^>]*href=\"([^\"]*(?:upload|files|download)[^\"]*)\"[^>]*>(.*?)</a>",
                html_text,
                re.IGNORECASE,
            )
            if file_matches:
                items = [f"[Прикрепленный файл: {html.unescape(txt).strip()}]" for _, txt in file_matches if txt.strip()]
                if items:
                    order.attachments_text = "\n".join(items)

    async def _enrich_freelance_ru(self, order: RawOrder) -> None:
        """Freelance.ru: выгружаем полное ТЗ со страницы /task/view/<id>."""
        if not order.url or not order.url.startswith("http"):
            return

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout) as client:
            resp = await client.get(order.url, follow_redirects=True)
            if resp.status_code != 200:
                return

            html_text = resp.text

            # Извлекаем текст после <h1>
            m_desc = re.search(r"<h1[^>]*>.*?</h1>\s*(.*?)(?:<div|<hr|<footer|<section)", html_text, re.DOTALL)
            if m_desc:
                clean = re.sub(r"<[^>]+>", "\n", m_desc.group(1))
                full_text = html.unescape("\n".join(l.strip() for l in clean.splitlines() if l.strip()))
                if len(full_text) > len(order.description):
                    order.description = full_text

            # Файлы
            files = re.findall(r"href=\"([^\"]*/download/[^\"]*)\"[^>]*>(.*?)</a>", html_text)
            if files:
                items = [f"[Прикрепленный файл: {html.unescape(txt).strip()}]" for _, txt in files if txt.strip()]
                if items:
                    order.attachments_text = "\n".join(items)

    async def _enrich_pchel_net(self, order: RawOrder) -> None:
        """Pchel.net: выгружаем полное описание со страницы заказа."""
        if not order.url or not order.url.startswith("http"):
            return

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout) as client:
            resp = await client.get(order.url, follow_redirects=True)
            if resp.status_code != 200:
                return

            m_desc = re.search(r"<div class=\"project-text[^>]*\">(.*?)</div>", resp.text, re.DOTALL)
            if m_desc:
                clean = re.sub(r"<[^>]+>", "\n", m_desc.group(1))
                full_text = html.unescape("\n".join(l.strip() for l in clean.splitlines() if l.strip()))
                if len(full_text) > len(order.description):
                    order.description = full_text

    async def _enrich_remote_job(self, order: RawOrder) -> None:
        """Remote-job: выгружаем полное описание со страницы заказа."""
        if not order.url or not order.url.startswith("http"):
            return

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout) as client:
            resp = await client.get(order.url, follow_redirects=True)
            if resp.status_code != 200:
                return

            m_desc = re.search(r"class=\"col-xs-12[^\"]*text-left\">(.*?)</div>", resp.text, re.DOTALL)
            if m_desc:
                clean = re.sub(r"<[^>]+>", "\n", m_desc.group(1))
                full_text = html.unescape("\n".join(l.strip() for l in clean.splitlines() if l.strip()))
                if len(full_text) > len(order.description):
                    order.description = full_text

    async def _enrich_hh_ru(self, order: RawOrder) -> None:
        """HeadHunter: выгружаем полное описание вакансии и ключевые навыки через API."""
        from src.config import settings

        token = (settings.HH_APP_TOKEN or "").strip()
        headers = {
            "User-Agent": settings.HH_USER_AGENT,
            "HH-User-Agent": settings.HH_USER_AGENT,
            "Accept": "application/json",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        api_url = f"https://api.hh.ru/vacancies/{order.external_id}"
        async with httpx.AsyncClient(headers=headers, timeout=self.timeout) as client:
            resp = await client.get(api_url)
            if resp.status_code != 200:
                return

            data = resp.json()
            desc_html = data.get("description", "")
            if desc_html:
                clean = re.sub(r"<[^>]+>", " ", desc_html)
                clean_desc = " ".join(html.unescape(clean).split())
                if len(clean_desc) > len(order.description):
                    order.description = clean_desc

            skills = [s.get("name") for s in data.get("key_skills", []) if s.get("name")]
            if skills:
                order.tags = list(dict.fromkeys(order.tags + skills))
                if order.attachments_text:
                    order.attachments_text += f"\n🔑 Навыки: {', '.join(skills)}"
                else:
                    order.attachments_text = f"🔑 Навыки: {', '.join(skills)}"
