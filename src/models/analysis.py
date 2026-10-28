"""Domain models for LLM evaluation and proposals."""

from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator
from src.models.order import OrderPriority


class PertEstimate(BaseModel):
    """PERT-анализ сроков разработки."""

    optimistic_days: float = Field(..., description="Оптимистичный сценарий (O)")
    most_likely_days: float = Field(..., description="Наиболее вероятный сценарий (M)")
    pessimistic_days: float = Field(..., description="Пессимистичный сценарий (P)")
    expected_days: float = Field(..., description="Ожидаемый срок E = (O + 4M + P) / 6")
    sigma: float = Field(..., description="Стандартное отклонение (P - O) / 6")


class AnalysisResult(BaseModel):
    """Структурированный результат разбора заказа нейросетью.

    Строго соблюдает регламент FREELANCE_PROFILE.md:
    - Оценка брать/не брать, сложность, чистое время
    - Подводные камни и технические риски
    - Зацепка за реальные проекты из PROJECTS_DOSSIER.md
    - Готовый живой отклик: без маркеров ИИ, строго с дефисами "-" (без "—")
    - PERT-анализ и обоснование цены (холодный старт vs торг)
    """

    take_order: bool = Field(..., description="Брать ли заказ (Да/Нет)")
    score: int = Field(..., ge=1, le=10, description="Общая привлекательность лида от 1 до 10")
    priority: OrderPriority = Field(..., description="Уровень приоритета (hot / normal)")
    executive_summary: str = Field(..., description="Краткое резюме: почему брать/не брать")

    # Специфика вакансий (HH.ru) под резюме Андрея Пименова
    company_overview: Optional[str] = Field(
        default="",
        description="Что за компания, ее сфера бизнеса, масштаб и продукт",
    )
    candidate_requirements: Optional[str] = Field(
        default="",
        description="Требования к кандидату, стек технологий, адекватность грейда",
    )
    job_responsibilities: Optional[str] = Field(
        default="",
        description="Чем предстоит заниматься на практике, реальные задачи",
    )
    match_reason: Optional[str] = Field(
        default="",
        description="Почему вакансия подходит Андрею Пименову с учетом его резюме",
    )
    skills_gap: Optional[str] = Field(
        default="",
        description="Чего не хватает в резюме Андрея из требований вакансии (пробелы в стеке)",
    )
    skills_gap_counter: Optional[str] = Field(
        default="",
        description="Как парировать пробел в требованиях вакансии в Cover Letter",
    )

    market_price: Optional[float] = Field(
        default=None,
        description="Объективная рыночная стоимость разработки (чистые часы * ставка 750-1000 ₽/ч + сложность) БЕЗ привязки к бюджету заказчика",
    )
    recommended_price: float = Field(default=0.0, description="Тактическая рекомендуемая цена для предложения клиенту в рублях")
    price_justification: str = Field(default="", description="Обоснование цен: сравнение рыночной стоимости с бюджетом клиента и стратегия торга")
    realistic_days: float = Field(default=0.0, description="Реалистичный срок для клиента в днях")

    matched_project: str = Field(
        default="Общий бэкграунд (Python Backend)",
        description="На какой проект из досье больше всего похоже (Speech Analytics, Avia_Pars, leads-monitor и др.)",
    )
    complexity: int = Field(default=1, ge=1, le=10, description="Реальная техническая сложность 1-10")
    pure_dev_hours: float = Field(default=0.0, description="Чистое расчетное время работы в часах")
    risks_and_pitfalls: List[str] = Field(
        default_factory=list,
        description="Скрытые риски, лимиты API, WAF, блокировки",
    )

    proposal_text: str = Field(
        default="",
        description="Готовый отклик живым языком: без штампов, строго с дефисами '-', первые 140 симв с зацепкой",
    )
    pert: Optional[PertEstimate] = Field(default=None, description="PERT расчет сроков")

    @field_validator("matched_project", mode="before")
    @classmethod
    def sanitize_matched_project(cls, v: Any) -> str:
        if v is None:
            return "Общий бэкграунд (Python Backend)"
        return str(v)

    @field_validator("price_justification", mode="before")
    @classmethod
    def sanitize_price_justification(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, dict):
            return " ".join(f"{k}: {val}" for k, val in v.items() if val)
        return str(v)

    @field_validator("executive_summary", mode="before")
    @classmethod
    def sanitize_executive_summary(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (list, tuple)):
            return " ".join(str(x) for x in v)
        if isinstance(v, dict):
            return " ".join(str(val) for val in v.values() if val)
        return str(v)

    @field_validator("company_overview", mode="before")
    @classmethod
    def sanitize_company_overview(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (list, tuple)):
            return " ".join(str(x) for x in v)
        if isinstance(v, dict):
            return " ".join(str(val) for val in v.values() if val)
        return str(v)

    @field_validator("candidate_requirements", mode="before")
    @classmethod
    def sanitize_candidate_requirements(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (list, tuple)):
            return " ".join(str(x) for x in v)
        if isinstance(v, dict):
            return " ".join(str(val) for val in v.values() if val)
        return str(v)

    @field_validator("job_responsibilities", mode="before")
    @classmethod
    def sanitize_job_responsibilities(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (list, tuple)):
            return " ".join(str(x) for x in v)
        if isinstance(v, dict):
            return " ".join(str(val) for val in v.values() if val)
        return str(v)

    @field_validator("match_reason", mode="before")
    @classmethod
    def sanitize_match_reason(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (list, tuple)):
            return " ".join(str(x) for x in v)
        if isinstance(v, dict):
            return " ".join(str(val) for val in v.values() if val)
        return str(v)

    @field_validator("skills_gap", mode="before")
    @classmethod
    def sanitize_skills_gap(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (list, tuple)):
            return " ".join(str(x) for x in v)
        if isinstance(v, dict):
            return " ".join(str(val) for val in v.values() if val)
        return str(v)

    @field_validator("skills_gap_counter", mode="before")
    @classmethod
    def sanitize_skills_gap_counter(cls, v: Any) -> str:
        if v is None:
            return ""
        if isinstance(v, (list, tuple)):
            return " ".join(str(x) for x in v)
        if isinstance(v, dict):
            return " ".join(str(val) for val in v.values() if val)
        return str(v)


class ProposalResult(str):
    """Результат генерации отклика Antigravity (agy) с финансовой оценкой на основе поиска в интернете.

    Наследуется от str для 100% обратной совместимости со всеми существующими хэндлерами и тестами,
    но несет в себе дополнительные поля recommended_price и price_justification.
    """

    def __new__(
        cls,
        text: str,
        recommended_price: Optional[float] = None,
        price_justification: Optional[str] = None,
        market_price: Optional[float] = None,
    ) -> "ProposalResult":
        obj = super().__new__(cls, text)
        obj.proposal_text = text
        obj.recommended_price = recommended_price
        obj.price_justification = price_justification
        obj.market_price = market_price
        return obj
