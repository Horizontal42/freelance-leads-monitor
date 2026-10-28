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

    async def chat_order(
        self,
        order: RawOrder,
        analysis_data: Optional[Dict[str, Any]] = None,
        proposal_text: Optional[str] = None,
        history: Optional[list] = None,
        user_message: str = "",
        model_preference: Optional[str] = None,
    ) -> tuple[str, str]:
        """Ответить на уточняющий вопрос по заказу. Возвращает (текст_ответа, имя_модели)."""
        raise NotImplementedError("chat_order не реализован")
