"""Collector for HeadHunter (hh.ru) API vacancies matching Andrei Pimenov's profile."""

import asyncio
from datetime import datetime
import html
import logging
import re
from typing import Any, Dict, List, Optional, Set
import httpx
from src.collectors.base import BaseCollector
from src.config import settings
from src.models.order import RawOrder, SourcePlatform

logger = logging.getLogger(__name__)

HTML_TAG_RE = re.compile(r"<[^>]+>")
QUOTES_RE = re.compile(r"[\"'«»“”„‘’`]")
LEGAL_FORMS_RE = re.compile(r"\b(?:ооо|оао|зао|пао|ао|ип|тоо|llc|inc|ltd)\b\.?", re.IGNORECASE)


def strip_html(text: Optional[str]) -> str:
    """Очистить HTML-теги и нормализовать пробелы."""
    if not text:
        return ""
    clean = HTML_TAG_RE.sub("", text)
    return " ".join(html.unescape(clean).split())


def normalize_employer(name: str) -> str:
    """Нормализовать название компании для схлопывания дубликатов."""
    text = QUOTES_RE.sub(" ", (name or "").lower())
    return " ".join(LEGAL_FORMS_RE.sub(" ", text).split())


class HhRuCollector(BaseCollector):
    """Сборщик вакансий HeadHunter (hh.ru) через официальный API.

    Ориентирован на профиль Андрея Пименова:
    - AI-инженер, LLM, RAG, Whisper, Computer Vision, Python/FastAPI автоматизация.
    - Фильтрация слишком высокого грейда (Middle+/Senior/Lead) с сохранением Junior/Trainee.
    - Отсев непрофильных стоп-вакансий (копирайтинг, SMM, ручная разметка, чистые продажи).
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        user_agent: Optional[str] = None,
        repo: Optional[Any] = None,
    ) -> None:
        super().__init__(name="hh_ru")
        self.config = settings.COLLECTORS_HH_RU
        self.base_url = (base_url or self.config.base_url).rstrip("/")
        self.token = settings.HH_APP_TOKEN if token is None else token
        self.user_agent = settings.HH_USER_AGENT if user_agent is None else user_agent
        self.repo = repo
        self._logged_missing_token = False

        # Компиляция регулярных выражений для отсева нерелевантных вакансий
        self.drop_title_rx = re.compile(self.config.drop_title, re.IGNORECASE)
        self.junior_title_rx = re.compile(self.config.junior_title, re.IGNORECASE)
        self.engineering_marker_rx = re.compile(self.config.engineering_marker, re.IGNORECASE)
        self.stop_hard_rx = [re.compile(p, re.IGNORECASE) for p in self.config.stop_title_hard]
        self.stop_soft_rx = [re.compile(p, re.IGNORECASE) for p in self.config.stop_title_soft]
        self.drop_experience: Set[str] = set(self.config.drop_experience)

    def _is_too_senior(self, title: str, experience: str) -> bool:
        """Проверить, не является ли вакансия слишком высокой по грейду."""
        if self.drop_title_rx.search(title) and not self.junior_title_rx.search(title):
            return True
        return experience in self.drop_experience

    def _is_stop_title(self, title: str) -> bool:
        """Проверить заголовок на наличие жестких или мягких стоп-слов."""
        if any(rx.search(title) for rx in self.stop_hard_rx):
            return True
        if self.engineering_marker_rx.search(title):
            return False
        return any(rx.search(title) for rx in self.stop_soft_rx)

    def _format_salary_meta(
        self, salary_data: Optional[Dict[str, Any]]
    ) -> tuple[Optional[float], bool, str]:
        """Преобразовать зарплатные данные hh.ru в числовую оценку (рубли) и строку."""
        if not salary_data:
            return None, True, "Не указана (по договоренности)"

        s_from = salary_data.get("from")
        s_to = salary_data.get("to")
        curr = (salary_data.get("currency") or "RUR").upper()

        if not s_from and not s_to:
            return None, True, "Не указана (по договоренности)"

        val = float(s_to or s_from)
        if curr in ["USD"]:
            val_rub = val * 95.0
        elif curr in ["EUR"]:
            val_rub = val * 105.0
        else:
            val_rub = val

        curr_symbol = "₽" if curr in ["RUR", "RUB"] else curr
        if s_from and s_to:
            sal_str = f"{s_from:,} - {s_to:,} {curr_symbol}".replace(",", " ")
        elif s_from:
            sal_str = f"от {s_from:,} {curr_symbol}".replace(",", " ")
        else:
            sal_str = f"до {s_to:,} {curr_symbol}".replace(",", " ")

        return val_rub, False, sal_str

    async def fetch_new_orders(
        self, is_cold_start: Optional[bool] = None
    ) -> List[RawOrder]:
        """Собрать свежие вакансии с hh.ru под профиль разработчика."""
        if not self.config.enabled:
            return []

        token = (self.token or "").strip()
        if not token:
            if not self._logged_missing_token:
                logger.info(
                    "HhRuCollector: HH_APP_TOKEN не задан в .env. Для сбора вакансий с hh.ru "
                    "укажите токен и User-Agent с dev.hh.ru."
                )
                self._logged_missing_token = True
            return []

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": self.user_agent,
            "HH-User-Agent": self.user_agent,
            "Accept": "application/json",
        }

        max_pages = (
            min(self.config.max_pages + 1, 3)
            if is_cold_start
            else self.config.max_pages
        )

        # Динамические фильтры города и формата работы из базы настроек
        area_param = self.config.area
        schedule_param = None
        format_setting = "all"
        if self.repo:
            try:
                city_setting = await self.repo.get_setting("vacancy_city", "all")
                if city_setting == "moscow":
                    area_param = [1]
                elif city_setting == "spb":
                    area_param = [2]
                elif city_setting == "russia":
                    area_param = [113]

                format_setting = await self.repo.get_setting("vacancy_work_format", "all")
                if format_setting == "remote":
                    schedule_param = "remote"
                    area_param = None  # Удаленка не привязывается к конкретному городу
                elif format_setting == "hybrid":
                    schedule_param = "flexible"
                elif format_setting == "office":
                    schedule_param = "fullDay"

                min_sal = await self.repo.get_setting("vacancy_min_salary", getattr(settings, "VACANCY_MIN_SALARY", 80000))
                if min_sal and int(min_sal) > 0:
                    salary_param = int(min_sal)
                else:
                    salary_param = None

                allow_neg = await self.repo.get_setting("vacancy_allow_negotiable", getattr(settings, "VACANCY_ALLOW_NEGOTIABLE", True))
                only_with_salary_param = not allow_neg

                custom_drop = await self.repo.get_setting("filter_drop_titles", None)
                if custom_drop and isinstance(custom_drop, list):
                    pattern_str = "|".join(t.strip() for t in custom_drop if t.strip())
                    if pattern_str:
                        self.drop_title_rx = re.compile(pattern_str, re.IGNORECASE)
                else:
                    self.drop_title_rx = re.compile(self.config.drop_title, re.IGNORECASE)
            except Exception as e:
                logger.debug("Не удалось получить динамические настройки вакансий hh.ru: %s", e)
                salary_param = None
                only_with_salary_param = False
        else:
            salary_param = getattr(settings, "VACANCY_MIN_SALARY", None)
            only_with_salary_param = not getattr(settings, "VACANCY_ALLOW_NEGOTIABLE", True)

        # Составляем варианты параметров (город vs удаленка):
        # Удаленные вакансии никогда не должны отсекаться фильтром города.
        param_variants: List[Dict[str, Any]] = []
        if format_setting == "remote":
            param_variants.append({"schedule": "remote"})
        elif format_setting in ("hybrid", "office"):
            var: Dict[str, Any] = {}
            if schedule_param:
                var["schedule"] = schedule_param
            if area_param:
                var["area"] = area_param
            param_variants.append(var)
        else:  # "all"
            if area_param:
                # Все удаленные по всей стране + любые вакансии в выбранном городе
                param_variants.append({"schedule": "remote"})
                param_variants.append({"area": area_param})
            else:
                param_variants.append({})

        found_orders: Dict[str, RawOrder] = {}
        seen_pairs: Set[tuple[str, str]] = set()

        query_configs = [
            (q, var)
            for q in self.config.queries
            for var in param_variants
        ]

        async with httpx.AsyncClient(timeout=15.0) as client:
            for query, variant in query_configs:
                for page in range(max_pages):
                    params: Dict[str, Any] = {
                        "text": query,
                        "per_page": self.config.per_page,
                        "page": page,
                        "period": max(1, min(self.config.days, 30)),
                        **variant,
                    }
                    if "schedule" not in params and "work_format" not in params and self.config.work_format:
                        params["work_format"] = self.config.work_format
                    if salary_param:
                        params["salary"] = salary_param
                    if only_with_salary_param:
                        params["only_with_salary"] = "true"

                    try:
                        resp = await client.get(
                            f"{self.base_url}/vacancies",
                            headers=headers,
                            params=params,
                        )
                    except Exception as e:
                        logger.warning(
                            "Ошибка соединения с api.hh.ru по запросу '%s': %s",
                            query,
                            e,
                        )
                        break

                    if resp.status_code == 400:
                        logger.warning("hh.ru вернул 400 по запросу '%s', пропуск", query)
                        break
                    if resp.status_code in (401, 403):
                        logger.warning(
                            "hh.ru отклонил авторизацию (%d). Проверьте HH_APP_TOKEN в .env",
                            resp.status_code,
                        )
                        return list(found_orders.values())
                    if resp.status_code == 429:
                        logger.warning("hh.ru rate limit 429. Приостановка сбора вакансий.")
                        return list(found_orders.values())
                    if resp.status_code != 200:
                        logger.warning("hh.ru ответил статусом %d", resp.status_code)
                        break

                    data = resp.json()
                    items = data.get("items", [])
                    if not items:
                        break

                    for item in items:
                        vac_id = str(item.get("id", ""))
                        if not vac_id or vac_id in found_orders:
                            continue

                        title = item.get("name", "").strip()
                        employer_obj = item.get("employer") or {}
                        employer_name = employer_obj.get("name", "").strip()
                        city = ((item.get("area") or {}).get("name") or "").strip()
                        formats = [
                            f.get("name", "")
                            for f in item.get("work_format") or []
                            if f.get("name")
                        ]
                        schedule_obj = item.get("schedule") or {}
                        schedule_name = (schedule_obj.get("name") or "").strip()
                        if schedule_name and schedule_name not in formats:
                            formats.append(schedule_name)

                        employment_obj = item.get("employment") or {}
                        employment_name = (employment_obj.get("name") or "").strip()
                        roles = [
                            r.get("name", "").strip()
                            for r in item.get("professional_roles") or []
                            if r.get("name")
                        ]
                        experience = ((item.get("experience") or {}).get("name") or "").strip()

                        # 1. Фильтр по уровню и стоп-словам
                        if self._is_too_senior(title, experience):
                            continue
                        if self._is_stop_title(title):
                            continue

                        # 2. Схлопывание дубликатов одного работодателя с одинаковой позицией
                        pair = (normalize_employer(employer_name), title.lower())
                        if pair in seen_pairs:
                            continue
                        seen_pairs.add(pair)

                        # 3. Разбор зарплаты
                        salary_data = item.get("salary") or item.get("salary_range")
                        price_rub, is_negotiable, sal_str = self._format_salary_meta(salary_data)

                        # 4. Сбор сниппета требований и обязанностей
                        snippet_obj = item.get("snippet") or {}
                        snippet_req = strip_html(snippet_obj.get("requirement"))
                        snippet_resp = strip_html(snippet_obj.get("responsibility"))
                        desc_parts = [p for p in (snippet_req, snippet_resp) if p]
                        description = "\n\n".join(desc_parts) if desc_parts else title

                        # 5. Метаданные для анализа и карточки
                        meta_lines = [
                            f"🏢 Компания: {employer_name}" if employer_name else "",
                            f"📍 Локация: {city}" if city else "",
                            f"🏠 Формат работы: {', '.join(formats)}" if formats else "",
                            f"💼 Занятость: {employment_name}" if employment_name else "",
                            f"⏳ Требуемый опыт: {experience}" if experience else "",
                            f"💰 Зарплата: {sal_str}",
                        ]
                        if roles:
                            meta_lines.append(f"🎯 Роль: {', '.join(roles)}")
                        attachments_text = "\n".join(line for line in meta_lines if line)

                        # 6. Теги
                        tags = []
                        if formats:
                            tags.extend(formats)
                        if city:
                            tags.append(city)
                        if experience:
                            tags.append(experience)
                        if employment_name and employment_name not in tags:
                            tags.append(employment_name)
                        for r in roles:
                            if r not in tags:
                                tags.append(r)

                        url = (item.get("alternate_url") or f"https://hh.ru/vacancy/{vac_id}").split("?")[0]

                        raw_order = RawOrder(
                            source=SourcePlatform.HH_RU,
                            external_id=vac_id,
                            title=title,
                            description=description,
                            url=url,
                            price=price_rub,
                            is_negotiable=is_negotiable,
                            is_pro_only=False,
                            tags=tags,
                            attachments_text=attachments_text,
                            raw_payload=item,
                        )
                        found_orders[vac_id] = raw_order

                    if len(items) < self.config.per_page:
                        break

                    await asyncio.sleep(0.4)

        return list(found_orders.values())


class NonITHhRuCollector(BaseCollector):
    """Сборщик прикладных (не-IT) вакансий в Санкт-Петербурге с hh.ru по 5 целевым направлениям."""

    DEFAULT_QUERIES = [
        "ЧПУ",
        "станок ЧПУ",
        'модульный ремонт OR "ремонт телефонов" OR "ремонт ноутбуков"',
        'постамат OR "сервисный техник"',
        '"trade-in" OR "входной контроль" OR "тестирование техники"',
        "helpdesk OR эникей",
    ]

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        user_agent: Optional[str] = None,
        repo: Optional[Any] = None,
        area: int = 2,
        min_salary: int = 70000,
    ) -> None:
        super().__init__(name="non_it_hh")
        self.config = settings.COLLECTORS_HH_RU
        self.base_url = (base_url or self.config.base_url).rstrip("/")
        self.token = settings.HH_APP_TOKEN if token is None else token
        self.user_agent = settings.HH_USER_AGENT if user_agent is None else user_agent
        self.repo = repo
        self.area = area
        self.min_salary = min_salary

    def _format_salary_meta(
        self, salary_data: Optional[Dict[str, Any]]
    ) -> tuple[Optional[float], bool, str]:
        if not salary_data:
            return None, True, "Не указана (по договоренности)"
        s_from = salary_data.get("from")
        s_to = salary_data.get("to")
        curr = (salary_data.get("currency") or "RUR").upper()
        if not s_from and not s_to:
            return None, True, "Не указана (по договоренности)"
        val = float(s_to or s_from)
        val_rub = val * 95.0 if curr == "USD" else (val * 105.0 if curr == "EUR" else val)
        curr_symbol = "₽" if curr in ["RUR", "RUB"] else curr
        if s_from and s_to:
            sal_str = f"{s_from:,} - {s_to:,} {curr_symbol}".replace(",", " ")
        elif s_from:
            sal_str = f"от {s_from:,} {curr_symbol}".replace(",", " ")
        else:
            sal_str = f"до {s_to:,} {curr_symbol}".replace(",", " ")
        return val_rub, False, sal_str

    async def fetch_new_orders(
        self, is_cold_start: Optional[bool] = None
    ) -> List[RawOrder]:
        token = (self.token or "").strip()
        if not token:
            return []

        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": self.user_agent,
            "HH-User-Agent": self.user_agent,
            "Accept": "application/json",
        }

        queries = getattr(self.config, "non_it_queries", None) or self.DEFAULT_QUERIES
        found_orders: Dict[str, RawOrder] = {}
        seen_pairs: Set[tuple[str, str]] = set()

        async with httpx.AsyncClient(timeout=15.0) as client:
            for query in queries:
                params: Dict[str, Any] = {
                    "text": query,
                    "area": self.area,
                    "salary": self.min_salary,
                    "per_page": 20,
                    "page": 0,
                    "period": 30,
                }
                try:
                    resp = await client.get(
                        f"{self.base_url}/vacancies",
                        headers=headers,
                        params=params,
                    )
                except Exception as e:
                    logger.warning("Ошибка запроса non_it hh.ru '%s': %s", query, e)
                    continue

                if resp.status_code != 200:
                    continue

                data = resp.json()
                items = data.get("items", [])
                for item in items:
                    vac_id = str(item.get("id", ""))
                    if not vac_id or vac_id in found_orders:
                        continue

                    title = item.get("name", "").strip()
                    employer_name = (item.get("employer") or {}).get("name", "").strip()
                    pair = (normalize_employer(employer_name), title.lower())
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)

                    salary_data = item.get("salary") or item.get("salary_range")
                    price_rub, is_negotiable, sal_str = self._format_salary_meta(salary_data)

                    snippet_obj = item.get("snippet") or {}
                    desc_req = strip_html(snippet_obj.get("requirement"))
                    desc_resp = strip_html(snippet_obj.get("responsibility"))
                    parts = [p for p in (desc_req, desc_resp) if p]
                    description = "\n\n".join(parts) if parts else title

                    city = ((item.get("area") or {}).get("name") or "").strip()
                    experience = ((item.get("experience") or {}).get("name") or "").strip()
                    schedule_name = ((item.get("schedule") or {}).get("name") or "").strip()

                    meta_lines = [
                        f"🏢 Компания: {employer_name}" if employer_name else "",
                        f"📍 Локация: {city}" if city else "",
                        f"🏠 График: {schedule_name}" if schedule_name else "",
                        f"⏳ Требуемый опыт: {experience}" if experience else "",
                        f"💰 Зарплата: {sal_str}",
                    ]
                    attachments_text = "\n".join(l for l in meta_lines if l)

                    tags = ["non_it", "прикладное", "hh_ru"]
                    if city:
                        tags.append(city)

                    url = (item.get("alternate_url") or f"https://hh.ru/vacancy/{vac_id}").split("?")[0]
                    found_orders[vac_id] = RawOrder(
                        source=SourcePlatform.HH_RU,
                        external_id=vac_id,
                        title=title,
                        description=description,
                        url=url,
                        price=price_rub,
                        is_negotiable=is_negotiable,
                        is_pro_only=False,
                        tags=tags,
                        attachments_text=attachments_text,
                        raw_payload=item,
                    )

                await asyncio.sleep(0.3)

        return list(found_orders.values())
