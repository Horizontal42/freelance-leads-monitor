"""Hybrid cascaded LLM client combining Mistral and Antigravity."""

import logging
from typing import Any, Dict, Optional
from src.analyzer.antigravity_client import AntigravityClient
from src.analyzer.base import BaseLLMClient
from src.analyzer.mistral_client import MistralClient
from src.config import settings
from src.models.analysis import AnalysisResult
from src.models.order import OrderPriority, RawOrder

logger = logging.getLogger(__name__)


class HybridLLMClient(BaseLLMClient):
    """Двухстадийный гибридный клиент:

    1. Быстрый первичный анализ, 3-4 предложения краткой сути, PERT-сроки и оценка
       рыночной цены выполняются через Mistral API.
    2. Финальный продающий отклик/отчет генерируется через Antigravity (agy -p)
       СТРОГО по требованию пользователя (при клике на кнопку в TG или Web UI).
    Если Mistral API недоступен, анализ выполняется резервным Antigravity.
    Если Antigravity дает сбой при генерации отклика, подключается резервный Mistral.
    """

    def __init__(
        self,
        mistral: Optional[MistralClient] = None,
        antigravity: Optional[AntigravityClient] = None,
    ) -> None:
        self.mistral = mistral or MistralClient()
        self.antigravity = antigravity or AntigravityClient()

    async def analyze_order(self, order: RawOrder) -> AnalysisResult:
        """Первичный анализ заказа через Mistral (суть в 3-4 предложениях, PERT, рыночная цена)."""
        if self.mistral.api_key:
            try:
                logger.info(
                    "Первичный анализ заказа [%s #%s] через Mistral...",
                    order.source.value,
                    order.external_id,
                )
                return await self.mistral.analyze_order(order)
            except Exception as e:
                logger.warning(
                    "Сбой анализа через Mistral: %s. Переключение на Antigravity...", e
                )

        # Fallback на Antigravity, если Mistral API недоступен или вернул ошибку
        try:
            return await self.antigravity.analyze_order(order)
        except Exception as e:
            logger.error("Сбой анализа Antigravity: %s", e)
            raise

    async def generate_proposal(
        self,
        order: RawOrder,
        analysis_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Сгенерировать отклик с приоритетом Antigravity (по требованию) и fallback на Mistral."""
        try:
            logger.info(
                "Генерация отклика для заказа [%s #%s] через Antigravity...",
                order.source.value,
                order.external_id,
            )
            return await self.antigravity.generate_proposal(order, analysis_data)
        except Exception as e:
            logger.warning(
                "Сбой генерации отклика Antigravity: %s. Резервный вызов Mistral...", e
            )
            if self.mistral.api_key:
                return await self.mistral.generate_proposal(order, analysis_data)
            raise
