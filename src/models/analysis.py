"""Domain models for LLM evaluation and proposals."""

from typing import List
from pydantic import BaseModel, Field
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

    recommended_price: float = Field(..., description="Рекомендуемая цена для отклика в рублях")
    price_justification: str = Field(..., description="Обоснование цены: вилка входа, порог торга")
    realistic_days: float = Field(..., description="Реалистичный срок для клиента в днях")

    matched_project: str = Field(
        ...,
        description="На какой проект из досье больше всего похоже (Speech Analytics, Avia_Pars, leads-monitor и др.)",
    )
    complexity: int = Field(..., ge=1, le=10, description="Реальная техническая сложность 1-10")
    pure_dev_hours: float = Field(..., description="Чистое расчетное время работы в часах")
    risks_and_pitfalls: List[str] = Field(
        default_factory=list,
        description="Скрытые риски, лимиты API, WAF, блокировки",
    )

    proposal_text: str = Field(
        ...,
        description="Готовый отклик живым языком: без штампов, строго с дефисами '-', первые 140 симв с зацепкой",
    )
    pert: PertEstimate = Field(..., description="PERT расчет сроков")
