"""Heuristic filter for non-IT applied vacancies with direction-specific rules and anti-scam protection."""

from dataclasses import dataclass, field
from enum import Enum
import logging
import re
from typing import Dict, List, Optional, Set
from src.models.order import FilterResult, RawOrder

logger = logging.getLogger(__name__)


class NonITDirection(str, Enum):
    CNC = "cnc"
    ELECTRONICS_REPAIR = "electronics_repair"
    POSTAMAT_TECH = "postamat_tech"
    TRADE_IN_TESTING = "trade_in_testing"
    HELPDESK_L1 = "helpdesk_l1"


@dataclass
class DirectionConfig:
    code: NonITDirection
    title_ru: str
    keywords: List[str]
    anti_scam_words: List[str]
    anti_gap_words: List[str]
    min_salary: int = 70000


# Общий список скама и сомнительных схем для всех прикладных направлений
GLOBAL_ANTI_SCAM_WORDS = [
    "сетевой маркетинг",
    "финансовая пирамида",
    "интим",
    "выбивание долгов",
    "коллектор",
    "закладчик",
    "дроп",
    "процент от чека",
    "согласование стоимости на дому",
    "выезд к клиентам на дом",
    "согласование цен на дому",
    "сдача денег в кассу",
    "продажа фильтров",
    "холодные звонки",
    "телемаркетинг",
]

DIRECTIONS_CONFIG: Dict[NonITDirection, DirectionConfig] = {
    NonITDirection.CNC: DirectionConfig(
        code=NonITDirection.CNC,
        title_ru="Оператор станков с ЧПУ",
        keywords=[
            "чпу",
            "стойка",
            "fanuc",
            "фанук",
            "siemens",
            "sinumerik",
            "heidenhain",
            "хайденайн",
            "токарн",
            "фрезерн",
            "токарно-фрезерн",
            "электроэрози",
            "наладчик станк",
            "оператор станк",
            "чпу станк",
            "металлообработк",
            "гибка металла",
            "листогиб",
            r"наладчик\w*.*чпу",
            r"оператор\w*.*чпу",
            r"станк\w*.*чпу",
            r"гидроабразивн",
            r"лазерн\w*\s+резк",
        ],
        anti_scam_words=[
            "выезд",
            "без опыта от 180",
            "доход от 200",
            "грузчик",
            "подсобный рабочий",
            "вахта с проживанием в вагончике",
        ],
        anti_gap_words=[
            "от 5 лет",
            "от 6 лет",
            "разработка постпроцессор",
            "5-ти осев",
            "5 осей",
            "5-осев",
            "cam-программист от 3",
            "главный технолог",
        ],
        min_salary=70000,
    ),
    NonITDirection.ELECTRONICS_REPAIR: DirectionConfig(
        code=NonITDirection.ELECTRONICS_REPAIR,
        title_ru="Мастер модульного ремонта электроники",
        keywords=[
            "модульный ремонт",
            "блочный ремонт",
            "замена матриц",
            "замена диспле",
            "замена экранов",
            "замена акб",
            "замена батаре",
            "чистка ноутбук",
            "замена термопаст",
            "сервисный центр",
            "ремонт телефонов",
            "ремонт планшетов",
            "ремонт ноутбуков",
            "помощник мастера по ремонту",
            "ученик мастера",
            "сервисный инженер по ремонту",
            "сервисный специалист",
            r"ремонт\w*.*(?:ноутбук|телефон|планшет|электроник|компьютер|техник)",
            r"мастер\w*.*по\s+ремонт",
            r"помощник\w*.*мастер",
            r"сервисн\w*.*инженер",
        ],
        anti_scam_words=[
            "выезд к клиент",
            "выездной мастер",
            "на дому",
            "согласование стоимости",
            "процент от сданных",
            "процент от заказ",
            "сдача денег",
            "холодные звонки",
            "агрегатор",
            "курьер документов",
            "развод",
        ],
        anti_gap_words=[
            "пайка bga",
            "пайке bga",
            "bga пайка",
            "bga-пайк",
            "компонентный ремонт материнских плат от 3 лет",
            "осциллограф",
            "реболлинг",
            "пайка микросхем под микроскопом от 3 лет",
        ],
        min_salary=70000,
    ),
    NonITDirection.POSTAMAT_TECH: DirectionConfig(
        code=NonITDirection.POSTAMAT_TECH,
        title_ru="Сервисный техник постаматов и терминалов",
        keywords=[
            "постамат",
            "вендинг",
            "терминал",
            "сервисный техник",
            "обслуживание постаматов",
            "техник постаматов",
            "5post",
            "сдэк",
            "яндекс маркет",
            "pickpoint",
            "замки ячеек",
            "ремонт терминалов",
            "валидатор",
            "купюроприемник",
            "банкомат",
            "сервисный инженер терминал",
            "кофемашин",
            r"сервисн\w*\s+техник",
            r"обслуживан\w*.*(?:терминал|постамат|вендинг)",
            r"техник\w*.*(?:постамат|терминал)",
        ],
        anti_scam_words=[
            "пеший курьер",
            "доставка посылок",
            "курьер на авто",
            "развоз пиццы",
            "сборщик заказов",
            "расклейка",
            "промоутер",
        ],
        anti_gap_words=[
            "4 группа электробезопасности",
            "5 группа электробезопасности",
            "допуск до 1000в свыше 3 лет",
            "высотные работы от 2 лет",
        ],
        min_salary=70000,
    ),
    NonITDirection.TRADE_IN_TESTING: DirectionConfig(
        code=NonITDirection.TRADE_IN_TESTING,
        title_ru="Специалист входного контроля и Trade-In",
        keywords=[
            "входной контроль",
            "тестирование электроники",
            "проверка техники",
            "дефектовка",
            "trade-in",
            "трейд-ин",
            "уценка",
            "контролер качества",
            "тестировщик техники",
            "сортировщик техники",
            "приемка техники",
            "оценка электроники",
            "проверка смартфонов",
            "диагност техники",
            r"входн\w*\s+контрол",
            r"контролер\w*\s+качеств",
            r"тестирован\w*.*техник",
            r"дефектовк\w*",
        ],
        anti_scam_words=[
            "грузчик",
            "разнорабочий",
            "уборка",
            "фасовщик",
            "комплектовщик ночная смена",
            "стикеровщик",
            "работа со сканером на ногах 12 часов",
        ],
        anti_gap_words=[
            "метрология от 5 лет",
            "ведущий аудитор качества",
            "главный контролер от 5 лет",
        ],
        min_salary=70000,
    ),
    NonITDirection.HELPDESK_L1: DirectionConfig(
        code=NonITDirection.HELPDESK_L1,
        title_ru="Младший специалист техподдержки (Helpdesk L1)",
        keywords=[
            "helpdesk",
            "хэлпдеск",
            "1 линия",
            "l1",
            "первая линия",
            "поддержка пользователей",
            "эникей",
            "обжимка",
            "витая пара",
            "патч-корд",
            "рабочие места",
            "windows 10",
            "windows 11",
            "оргтехник",
            "замена картридж",
            "настройка пк",
            "сборка пк",
            "младший системный администратор",
            "техник ит",
            r"help\s*desk",
            r"тех\w*\s*поддержк",
            r"1\s*лини\w*",
            r"специалист\w*.*поддержк",
        ],
        anti_scam_words=[
            "холодные звонки",
            "продажи",
            "телемаркетинг",
            "входящие звонки банка",
            "кредитные продукты",
            "колл-центр по продажам",
            "горячая линия банка",
        ],
        anti_gap_words=[
            "devops",
            "kubernetes",
            "ccna",
            "ccnp",
            "сеньор",
            "ведущий системный архитектор",
            "архитектор сетей от 5 лет",
        ],
        min_salary=70000,
    ),
}


class NonITHardFilter:
    """Специализированный эвристический фильтр для прикладных вакансий (не-IT)."""

    def __init__(
        self,
        min_salary: int = 70000,
        directions: Optional[List[NonITDirection]] = None,
    ) -> None:
        self.min_salary = min_salary
        self.directions = directions or list(NonITDirection)

    def _match_terms(self, text: str, terms: List[str]) -> Set[str]:
        matched = set()
        text_lower = text.lower()
        for term in terms:
            if term.startswith("^") or term.startswith(r"\b") or ".*" in term or r"\s" in term or r"\w" in term or "|" in term:
                if re.search(term, text_lower):
                    matched.add(term)
            elif len(term) <= 3:
                pattern = rf"(?:\b|[^a-zA-Zа-яА-Я0-9]){re.escape(term)}(?:\b|[^a-zA-Zа-яА-Я0-9])"
                if re.search(pattern, text_lower):
                    matched.add(term)
            else:
                if term in text_lower:
                    matched.add(term)
        return matched

    def evaluate(self, order: RawOrder) -> FilterResult:
        full_text = order.full_text

        # 1. Проверка зарплаты (не ниже 70 000 руб, если указана)
        if order.price is not None and order.price > 0 and order.price < self.min_salary:
            return FilterResult(
                passed=False,
                reason=f"Зарплата {int(order.price)} ₽ ниже минимального порога ({self.min_salary} ₽)",
            )

        # 2. Глобальный анти-скам
        matched_global_scam = self._match_terms(full_text, GLOBAL_ANTI_SCAM_WORDS)
        if matched_global_scam:
            return FilterResult(
                passed=False,
                reason=f"Обнаружены признаки сомнительной схемы / скама: {', '.join(sorted(matched_global_scam))}",
                matched_stopwords=list(matched_global_scam),
            )

        # 3. Поиск совпадений по направлениям
        best_direction: Optional[DirectionConfig] = None
        best_keywords: Set[str] = set()

        for d_code in self.directions:
            cfg = DIRECTIONS_CONFIG.get(d_code)
            if not cfg:
                continue
            matched_kw = self._match_terms(full_text, cfg.keywords)
            if len(matched_kw) > len(best_keywords):
                best_direction = cfg
                best_keywords = matched_kw

        if not best_direction or not best_keywords:
            return FilterResult(
                passed=False,
                reason="Не подходит ни под одно из 5 прикладных направлений (ЧПУ, Ремонт, Постаматы, Trade-In, Helpdesk)",
            )

        # 4. Проверка анти-скама конкретного направления
        matched_dir_scam = self._match_terms(full_text, best_direction.anti_scam_words)
        if matched_dir_scam:
            return FilterResult(
                passed=False,
                reason=f"Отсев по критериям {best_direction.title_ru} (скам/непрофиль: {', '.join(sorted(matched_dir_scam))})",
                matched_stopwords=list(matched_dir_scam),
            )

        # 5. Проверка квалификационного барьера (anti-gap)
        matched_gap = self._match_terms(full_text, best_direction.anti_gap_words)
        if matched_gap:
            # Исключение: фразы отрицания "без пайки bga", "без bga"
            if "без пайки" in full_text.lower() or "без bga" in full_text.lower():
                bga_terms = {"пайка bga", "пайке bga", "bga пайка", "bga-пайк"}
                matched_gap = matched_gap - bga_terms

        if matched_gap:
            return FilterResult(
                passed=False,
                reason=f"Завышенные требования для входа ({best_direction.title_ru}: {', '.join(sorted(matched_gap))})",
                matched_stopwords=list(matched_gap),
            )

        # Добавляем теги направления в заказ
        tags = set(order.tags or [])
        tags.add("non_it")
        tags.add(f"direction:{best_direction.code.value}")
        order.tags = sorted(tags)

        return FilterResult(
            passed=True,
            reason=f"Направление: {best_direction.title_ru} (ключевики: {', '.join(sorted(best_keywords))})",
            matched_keywords=list(best_keywords),
        )
