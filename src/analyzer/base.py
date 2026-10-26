"""Abstract base class for LLM clients."""

from abc import ABC, abstractmethod
from src.models.analysis import AnalysisResult
from src.models.order import RawOrder


class BaseLLMClient(ABC):
    """Базовый абстрактный класс клиента языковой модели."""

    @abstractmethod
    async def analyze_order(self, order: RawOrder) -> AnalysisResult:
        """Проанализировать заказ и вернуть структурированный AnalysisResult."""
        pass
