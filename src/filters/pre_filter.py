"""Heuristic Hard-Filter for screening out junk leads without LLM costs."""

import logging
import re
from typing import List, Optional, Set
from src.config import settings
from src.models.order import FilterResult, RawOrder, SourcePlatform

logger = logging.getLogger(__name__)


class HardFilter:
    """Эвристический фильтр первого уровня (без вызова LLM).

    Правила:
    1. Бюджет: строго от MIN_BUDGET (10 000 руб.), либо если бюджет не указан (по договоренности).
    2. Черный список стоп-слов: отсев дипломов, курсовых, 1С, верстки, копирайтинга.
    3. Белый список ключевых слов: поиск признаков нашего стека (Python, боты, парсинг, CRM и др.).
    """

    def __init__(
        self,
        min_budget: Optional[int] = None,
        stop_words: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        filter_pro_only: Optional[bool] = None,
        allow_quick_orders: Optional[bool] = None,
        quick_min_budget: Optional[int] = None,
    ) -> None:
        self.min_budget = min_budget or settings.MIN_BUDGET
        self.stop_words = [w.lower().strip() for w in (stop_words or settings.STOP_WORDS)]
        self.keywords = [w.lower().strip() for w in (keywords or settings.KEYWORDS)]
        self.filter_pro_only = (
            filter_pro_only if filter_pro_only is not None else settings.FILTER_PRO_ONLY
        )
        self.allow_quick_orders = (
            allow_quick_orders
            if allow_quick_orders is not None
            else getattr(settings, "ALLOW_QUICK_ORDERS", True)
        )
        self.quick_min_budget = (
            quick_min_budget
            if quick_min_budget is not None
            else getattr(settings, "QUICK_MIN_BUDGET", 2000)
        )

        # Регулярные выражения для фильтрации IT-вакансий (HH.ru, Хабр Карьера, Авито)
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
        self.excessive_exp_rx = re.compile(
            r"\b(?:от\s*(?:[5-9]|\d{2})\s*лет|(?:[5-9]|\d{2})\+\s*лет|опыт\s*(?:работы\s*)?(?:от\s*)?(?:[5-9]|\d{2})\s*лет|более\s*(?:4|[5-9]|\d{2})\s*лет)\b",
            re.IGNORECASE,
        )
        self.stop_it_titles_rx = re.compile(
            r"\b(?:smm|копирайт|разметчик\w* данных|ai[- ]?тренер|ai trainer|продаж\w*|\bsales\b|маркетолог|маркетинг|наставник|куратор|преподав\w*|репетитор)\b",
            re.IGNORECASE,
        )
        self.engineering_marker_rx = re.compile(
            r"\b(?:инженер|engineer|разработчик|developer|программист|ml|llm|rag|python)\b",
            re.IGNORECASE,
        )

    def _match_terms(self, text: str, terms: List[str]) -> Set[str]:
        """Найти совпадения терминов в тексте с учетом границ коротких слов."""
        matched = set()
        text_lower = text.lower()

        for term in terms:
            # Для коротких терминов (до 3 символов, e.g. "1c", "1с", "ии", "crm", "api")
            # используем строгие границы слов, чтобы избежать ложных срабатываний
            if len(term) <= 3:
                pattern = rf"(?:\b|[^a-zA-Zа-яА-Я0-9]){re.escape(term)}(?:\b|[^a-zA-Zа-яА-Я0-9])"
                if re.search(pattern, text_lower):
                    matched.add(term)
            else:
                if term in text_lower:
                    matched.add(term)

        return matched

    def evaluate(self, order: RawOrder) -> FilterResult:
        """Проверить заказ по правилам фильтрации."""
        full_text = order.full_text

        # Специализированная фильтрация IT-вакансий (hh.ru, habr_career, avito-вакансии)
        is_it_vacancy = (
            order.source in (SourcePlatform.HH_RU, SourcePlatform.HABR_CAREER)
            or (order.source == SourcePlatform.AVITO and "vacancy" in (order.tags or []))
        ) and not order.is_non_it

        if is_it_vacancy:
            # 1. Отсев по грейду (Senior/Lead)
            if self.drop_title_rx.search(order.title) and not self.junior_title_rx.search(order.title):
                return FilterResult(
                    passed=False,
                    reason=f"Вакансия для уровня Senior/Lead в названии: '{order.title}' (профиль: Junior+/Middle)",
                )
            if any(self.drop_tags_rx.search(t.strip()) for t in (order.tags or [])):
                return FilterResult(
                    passed=False,
                    reason="Вакансия содержит теги уровня Senior/Lead",
                )

            # 2. Отсев по требуемому опыту работы (от 5+ лет)
            if self.excessive_exp_rx.search(full_text):
                return FilterResult(
                    passed=False,
                    reason="Требуемый опыт работы (от 5+ лет) превышает профиль (Junior+/Middle)",
                )

            # 3. Отсев по нецелевому языку/стеку в названии (C#, Java, PHP, Go и др. без Python/AI)
            if self.drop_languages_rx.search(order.title) and not self.target_stack_rx.search(order.title):
                return FilterResult(
                    passed=False,
                    reason=f"Непрофильный основной стек в названии вакансии: '{order.title}'",
                )

            # 4. Отсев непрофильных направлений в IT (SMM, продажи, копирайтинг, разметка)
            if self.stop_it_titles_rx.search(order.title) and not self.engineering_marker_rx.search(order.title):
                return FilterResult(
                    passed=False,
                    reason=f"Непрофильное направление IT-вакансии: '{order.title}'",
                )

        # 1. Проверка стоп-слов
        matched_stopwords = self._match_terms(full_text, self.stop_words)
        if matched_stopwords:
            # Разграничение: инженерный дизайн (System Design, API Design) vs визуальный дизайн (UI/UX, графика)
            design_stopwords = {"дизайн", "дизайнер", "дизайн сайта", "веб-дизайн"}
            if matched_stopwords.intersection(design_stopwords):
                engineering_design_rx = re.compile(
                    r"\b(?:system\s*design|дизайн\s*систем|api\s*design|дизайн\s*api|database\s*design|дизайн\s*баз|design\s*pattern|паттерн[а-я]*\s*дизайн|prompt\s*design|дизайн\s*архитектур|архитектурн[а-я]*\s*дизайн)\b",
                    re.IGNORECASE,
                )
                visual_design_rx = re.compile(
                    r"\b(?:ui/ux|ux/ui|figma|фигм[а-я]*|баннер[а-я]*|логотип[а-я]*|полиграфи[а-я]*|интерьер[а-я]*|векторн[а-я]*\s*материал|карточ[а-я]*\s*(?:wb|ozon|вб|озон)|айдентик[а-я]*|фирменн[а-я]*\s*стил)\b",
                    re.IGNORECASE,
                )
                if engineering_design_rx.search(full_text) and not visual_design_rx.search(full_text):
                    # Инженерный системный дизайн сохраняем, снимаем триггер стоп-слова дизайна
                    matched_stopwords = matched_stopwords - design_stopwords

        if matched_stopwords:
            if order.is_ai_first:
                # Для приоритетных AI-First / Agentic лидов блокируем только академический спам и накрутки
                hard_junk = {"диплом", "дипломная", "дипломный", "дипломн", "студент", "курсовая", "курсовой проект", "реферат", "лабораторная работа", "накрутка", "накрутк", "рукапча", "2captcha", "antigate"}
                critical_matches = matched_stopwords.intersection(hard_junk)
                if critical_matches:
                    return FilterResult(
                        passed=False,
                        reason=f"Обнаружены критические стоп-слова: {', '.join(sorted(critical_matches))}",
                        matched_stopwords=list(critical_matches),
                    )
            else:
                return FilterResult(
                    passed=False,
                    reason=f"Обнаружены стоп-слова: {', '.join(sorted(matched_stopwords))}",
                    matched_stopwords=list(matched_stopwords),
                )

        # 2. Проверка платных откликов / PRO
        if self.filter_pro_only and order.is_pro_only:
            return FilterResult(
                passed=False,
                reason="Требуется платный отклик / аккаунт PRO",
            )

        # 2. Проверка бюджета
        is_quick_order = False
        if (
            order.price is not None
            and order.price < self.min_budget
            and not order.is_negotiable
        ):
            # Проверяем возможность пропустить как быстрый микро-заказ (Quick Win)
            if self.allow_quick_orders and order.price >= self.quick_min_budget:
                quick_patterns = r"\b(?:скрипт|парсер|парсинг|бот|aiogram|эндпоинт|endpoint|n8n|вебхук|webhook|конвертац|обработк|api|fastapi|pandas)\b"
                heavy_patterns = r"\b(?:под\s*ключ|маркетплейс|интернет[- ]магазин|портал|crm.*нуля|платформ|saas|соцсет|сервис.*под\s*ключ)\b"
                if re.search(quick_patterns, full_text, re.IGNORECASE) and not re.search(heavy_patterns, full_text, re.IGNORECASE):
                    is_quick_order = True
                else:
                    return FilterResult(
                        passed=False,
                        reason=f"Бюджет {int(order.price)} ₽ ниже минимального порога {self.min_budget} ₽ (не является быстрым точечным заказом)",
                    )
            else:
                return FilterResult(
                    passed=False,
                    reason=f"Бюджет {int(order.price)} ₽ ниже минимального порога {self.min_budget} ₽",
                )

        # 3. Проверка белого списка ключевых слов
        matched_keywords = self._match_terms(full_text, self.keywords)
        if not matched_keywords:
            return FilterResult(
                passed=False,
                reason="Нет совпадений с белым списком ключевых слов",
            )

        # Все проверки пройдены
        reason_msg = (
            f"Прошел фильтр как быстрый заказ ⚡ Quick Win (бюджет {int(order.price)} ₽)"
            if is_quick_order
            else f"Прошел фильтр (найдены ключевики: {', '.join(sorted(matched_keywords))})"
        )
        return FilterResult(
            passed=True,
            reason=reason_msg,
            matched_keywords=list(matched_keywords),
        )
