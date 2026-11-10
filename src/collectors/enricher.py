"""Order detail enricher: extracts complete task text and attached files before LLM analysis."""

import html
import logging
import os
import re
import urllib.parse
from typing import List, Optional
import httpx
from src.models.order import RawOrder, SourcePlatform
from src.collectors.file_extractor import (
    is_supported_attachment,
    extract_text_from_file_bytes,
)

logger = logging.getLogger(__name__)

TEXT_EXTENSIONS = {
    ".txt", ".md", ".json", ".csv", ".py", ".sql", ".log",
    ".yml", ".yaml", ".xml", ".html", ".sh", ".env", ".cfg", ".ini",
}
MAX_FILE_BYTES = 50 * 1024  # 50 KB max per file content


def clean_html_to_text(raw_html: str) -> str:
    """Очищает HTML в читаемый plain text с сохранением структуры абзацев, заголовков и списков."""
    if not raw_html:
        return ""
    # 1. Структурные теги заменяем на переносы строк
    text = re.sub(r"<(?:br|hr)\s*/?>", "\n", raw_html, flags=re.IGNORECASE)
    text = re.sub(
        r"</?(?:p|div|section|article|header|footer|h[1-6]|tr|blockquote)[^>]*>",
        "\n\n",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"<li[^>]*>", "\n• ", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    # 2. Удаляем все оставшиеся теги
    text = re.sub(r"<[^>]+>", " ", text)
    # 3. Декодируем HTML entities
    text = html.unescape(text)
    # 4. Нормализуем пробелы построчно
    lines = []
    for line in text.split("\n"):
        cleaned = " ".join(line.split())
        lines.append(cleaned)
    result = "\n".join(lines)
    # 5. Схлопываем 3+ пустых строк в две
    return re.sub(r"\n{3,}", "\n\n", result).strip()


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
        fl_cookie = os.getenv("FL_RU_COOKIE") or os.getenv("FL_COOKIE")
        if fl_cookie:
            self.headers["Cookie"] = fl_cookie

    async def _fetch_and_extract_file(
        self, client: httpx.AsyncClient, file_url: str, fname: str, size_str: str = ""
    ) -> str:
        """Download and extract content from attachment, returning formatted block."""
        target_fname = fname
        if not os.path.splitext(target_fname)[1]:
            parsed_path = urllib.parse.urlparse(file_url).path
            base_ext = os.path.splitext(parsed_path)[1]
            if base_ext:
                target_fname = f"{fname}{base_ext}"

        if not is_supported_attachment(target_fname) and not is_supported_attachment(file_url):
            return f"[Прикрепленный файл: {fname} ({size_str})]" if size_str else f"[Прикрепленный файл: {fname}]"

        try:
            resp = await client.get(file_url, follow_redirects=True)
            if resp.status_code == 200 and not resp.text.strip().startswith("<!DOCTYPE"):
                extracted = extract_text_from_file_bytes(resp.content, target_fname)
                if extracted:
                    extracted = extracted.replace("\x00", "").strip()
                    header = f"[Файл: {fname} ({size_str})]" if size_str else f"[Файл: {fname}]"
                    return (
                        f"{header}\n"
                        f"--- Начало содержимого файла ---\n"
                        f"{extracted}\n"
                        f"--- Конец содержимого файла ---"
                    )
        except Exception as e:
            logger.debug("Не удалось скачать или разобрать файл %s: %s", fname, e)

        return f"[Прикрепленный файл: {fname} ({size_str})]" if size_str else f"[Прикрепленный файл: {fname}]"

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
            elif order.source == SourcePlatform.HABR_CAREER:
                await self._enrich_habr_career(order)
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
                size_str = f"{fsize} байт" if fsize else ""
                block = await self._fetch_and_extract_file(client, furl, fname, size_str)
                attachments.append(block)

        if attachments:
            files_block = "\n\n".join(attachments)
            if order.attachments_text:
                order.attachments_text = f"{order.attachments_text}\n\n{files_block}"
            else:
                order.attachments_text = files_block

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
                full_text = clean_html_to_text(m_desc.group(1))
                if len(full_text) > len(order.description):
                    order.description = full_text

            # 2. Файлы
            file_matches = re.findall(
                r"<a[^>]*href=[\"']([^\"']*(?:upload|files|download|\.(?:docx?|pdf|xlsx?|txt|rtf|zip))[^\"']*)[\"'][^>]*>(.*?)</a>",
                html_text,
                re.IGNORECASE,
            )
            attachments: List[str] = []
            ignored_href_tokens = ("/about/", "/rules", "cookie_accept", "regulations", "appendix_2", "terms", "agreement", "privacy")
            ignored_names = ("ссылка на заказ", "посмотреть другие заказы", "вход", "откликнуться", "правила", "соглашение", "конфиденциальность")
            for href, txt in file_matches:
                if any(tok in href.lower() for tok in ignored_href_tokens):
                    continue
                fname = html.unescape(txt).strip() or os.path.basename(href.split("?")[0])
                if not fname or fname.lower() in ignored_names:
                    continue
                full_furl = urllib.parse.urljoin("https://www.fl.ru", href)
                block = await self._fetch_and_extract_file(client, full_furl, fname)
                attachments.append(block)

            if attachments:
                files_block = "\n\n".join(attachments)
                if order.attachments_text:
                    order.attachments_text = f"{order.attachments_text}\n\n{files_block}"
                else:
                    order.attachments_text = files_block

            # 3. Уточнение статуса PRO / платного объявления
            if (
                "topprjpay" in html_text
                or "payed-emp" in html_text
                or "pro-big" in html_text
                or "b-icon__pro_f" in html_text
                or "urgently-1.png" in html_text
                or "b-post_bg_ffffd4" in html_text
                or "платное объявление" in html_text.lower()
                or "платный проект" in html_text.lower()
                or "только для pro" in html_text.lower()
            ):
                order.is_pro_only = True

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
            files = re.findall(
                r"<a[^>]*href=[\"']([^\"']*(?:/download/|\.(?:docx?|pdf|xlsx?|txt|rtf|zip))[^\"']*)[\"'][^>]*>(.*?)</a>",
                html_text,
                re.IGNORECASE,
            )
            attachments: List[str] = []
            ignored_href_tokens = ("/about/", "/rules", "cookie_accept", "regulations", "terms", "agreement", "privacy")
            ignored_names = ("ссылка на заказ", "посмотреть другие заказы", "вход", "откликнуться", "правила", "соглашение", "конфиденциальность")
            for href, txt in files:
                if any(tok in href.lower() for tok in ignored_href_tokens):
                    continue
                fname = html.unescape(txt).strip() or os.path.basename(href.split("?")[0])
                if not fname or fname.lower() in ignored_names:
                    continue
                full_furl = urllib.parse.urljoin("https://freelance.ru", href)
                block = await self._fetch_and_extract_file(client, full_furl, fname)
                attachments.append(block)

            if attachments:
                files_block = "\n\n".join(attachments)
                if order.attachments_text:
                    order.attachments_text = f"{order.attachments_text}\n\n{files_block}"
                else:
                    order.attachments_text = files_block

            # Уточнение бюджета со страницы задания (если не определен в ленте)
            if order.price is None:
                m_price = re.search(r'class="tv-meta-item__val[^"]*--budget[^"]*">(.*?)</div>', html_text, re.DOTALL)
                if m_price:
                    raw_b = html.unescape(m_price.group(1)).replace("\xa0", " ")
                    if not ("индивидуально" in raw_b.lower() or "договор" in raw_b.lower() or "cost-not-set" in raw_b.lower()):
                        p_d = re.search(r"(\d[\d\s]*)\s*(?:₽|&#8381;|руб|р\b)", raw_b, re.IGNORECASE)
                        if p_d:
                            try:
                                order.price = float(re.sub(r"\s+", "", p_d.group(1)))
                                order.is_negotiable = False
                            except ValueError:
                                pass

            # Проверка статуса PRO / Премиум
            if (
                "task-card--premium" in html_text
                or "task-badge--premium" in html_text
                or "task-badge--business" in html_text
                or "только для премиум" in html_text.lower()
                or "владельцев премиум" in html_text.lower()
                or "только для pro" in html_text.lower()
                or "аккаунт pro" in html_text.lower()
            ):
                order.is_pro_only = True
            elif "task-badge--all" in html_text or "видно всем" in html_text.lower():
                order.is_pro_only = False

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

            # Файлы
            files = re.findall(
                r"<a[^>]*href=[\"']([^\"']*(?:/download/|/attachments/|\.(?:docx?|pdf|xlsx?|txt|rtf|zip))[^\"']*)[\"'][^>]*>(.*?)</a>",
                resp.text,
                re.IGNORECASE,
            )
            attachments: List[str] = []
            ignored_href_tokens = ("/about/", "/rules", "cookie_accept", "regulations", "terms", "agreement", "privacy")
            ignored_names = ("ссылка на заказ", "посмотреть другие заказы", "вход", "откликнуться", "правила", "соглашение", "конфиденциальность")
            for href, txt in files:
                if any(tok in href.lower() for tok in ignored_href_tokens):
                    continue
                fname = html.unescape(txt).strip() or os.path.basename(href.split("?")[0])
                if not fname or fname.lower() in ignored_names:
                    continue
                full_furl = urllib.parse.urljoin("https://pchel.net", href)
                block = await self._fetch_and_extract_file(client, full_furl, fname)
                attachments.append(block)

            if attachments:
                files_block = "\n\n".join(attachments)
                if order.attachments_text:
                    order.attachments_text = f"{order.attachments_text}\n\n{files_block}"
                else:
                    order.attachments_text = files_block

    async def _enrich_habr_career(self, order: RawOrder) -> None:
        """Хабр Карьера: выгружаем полный текст описания вакансии."""
        if not order.url or not order.url.startswith("http"):
            return

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout) as client:
            resp = await client.get(order.url, follow_redirects=True)
            if resp.status_code != 200:
                return

            html_text = resp.text
            m_desc = re.search(
                r"<div[^>]*class=\"[^\"]*vacancy-description__text[^\"]*\"[^>]*>(.*?)</div>\s*</div>",
                html_text,
                re.DOTALL,
            )
            if m_desc:
                full_text = clean_html_to_text(m_desc.group(1))
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
                clean_desc = clean_html_to_text(desc_html)
                if len(clean_desc) > len(order.description):
                    order.description = clean_desc

            skills = [s.get("name") for s in data.get("key_skills", []) if s.get("name")]
            sched_name = (data.get("schedule") or {}).get("name", "")
            emp_name = (data.get("employment") or {}).get("name", "")

            enrich_parts = []
            if skills:
                order.tags = list(dict.fromkeys(order.tags + skills))
                enrich_parts.append(f"🔑 Навыки: {', '.join(skills)}")
            if sched_name and sched_name not in (order.attachments_text or ""):
                enrich_parts.append(f"🏠 График: {sched_name}")
            if emp_name and emp_name not in (order.attachments_text or ""):
                enrich_parts.append(f"💼 Занятость: {emp_name}")

            if enrich_parts:
                add_block = "\n".join(enrich_parts)
                if order.attachments_text:
                    order.attachments_text += f"\n{add_block}"
                else:
                    order.attachments_text = add_block
