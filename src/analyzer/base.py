"""Base class for LLM clients."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from src.models.analysis import AnalysisResult
from src.models.order import RawOrder


class BaseLLMClient(ABC):
    """Абстрактный базовый класс для работы с LLM (Antigravity CLI / Mistral API)."""

    @abstractmethod
    async def analyze_order(self, order: RawOrder) -> AnalysisResult:
        """Провести глубокий скоринг и PERT-анализ заказа."""
        pass

    @abstractmethod
    async def generate_proposal(
        self,
        order: RawOrder,
        analysis_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Сгенерировать персонализированный отклик по требованию."""
        pass
