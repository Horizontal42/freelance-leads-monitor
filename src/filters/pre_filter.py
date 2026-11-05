"""Heuristic Hard-Filter for screening out junk leads without LLM costs."""

import logging
import re
from typing import List, Optional, Set
from src.config import settings
from src.models.order import FilterResult, RawOrder

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
    ) -> None:
        self.min_budget = min_budget or settings.MIN_BUDGET
        self.stop_words = [w.lower().strip() for w in (stop_words or settings.STOP_WORDS)]
        self.keywords = [w.lower().strip() for w in (keywords or settings.KEYWORDS)]
        self.filter_pro_only = (
            filter_pro_only if filter_pro_only is not None else settings.FILTER_PRO_ONLY
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

        # 1. Проверка стоп-слов
        matched_stopwords = self._match_terms(full_text, self.stop_words)
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
        if (
            order.price is not None
            and order.price < self.min_budget
            and not order.is_negotiable
        ):
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
        return FilterResult(
            passed=True,
            reason=f"Прошел фильтр (найдены ключевики: {', '.join(sorted(matched_keywords))})",
            matched_keywords=list(matched_keywords),
        )
