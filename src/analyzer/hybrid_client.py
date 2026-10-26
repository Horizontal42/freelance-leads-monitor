"""Hybrid cascaded LLM client combining Mistral and Antigravity."""

import logging
from typing import Optional
from src.analyzer.antigravity_client import AntigravityClient
from src.analyzer.base import BaseLLMClient
from src.analyzer.mistral_client import MistralClient
from src.config import settings
from src.models.analysis import AnalysisResult
from src.models.order import OrderPriority, RawOrder

logger = logging.getLogger(__name__)


class HybridLLMClient(BaseLLMClient):
    """Двухстадийный гибридный клиент:

    1. Быстрый скоринг и отсев через Mistral (300-500 мс).
    2. Глубокий анализ, PERT-сроки и генерация отклика через Antigravity (gemini-3.8-flash-medium).
    Если Mistral API недоступен, напрямую передает заказ в Antigravity.
    Если Antigravity дает сбой, переключается на полный анализ через Mistral.
    """

    def __init__(
        self,
        mistral: Optional[MistralClient] = None,
        antigravity: Optional[AntigravityClient] = None,
    ) -> None:
        self.mistral = mistral or MistralClient()
        self.antigravity = antigravity or AntigravityClient()

    async def analyze_order(self, order: RawOrder) -> AnalysisResult:
        # Стадия 1: Быстрый скоринг через Mistral (если задан ключ)
        if self.mistral.api_key:
            try:
                qc = await self.mistral.quick_classify(order)
                is_relevant = qc.get("is_relevant", True)
                quick_score = int(qc.get("quick_score", 7))
                reason = qc.get("reason", "")

                # Если заказ явно нерелевантен или скор ниже 5, не тратим квоту Antigravity
                if not is_relevant or quick_score < 5:
                    logger.info(
                        "Mistral отсеял заказ [%s #%s]: score=%d, reason='%s'",
                        order.source.value,
                        order.external_id,
                        quick_score,
                        reason,
                    )
                    return AnalysisResult(
                        take_order=False,
                        score=quick_score,
                        priority=OrderPriority.NORMAL,
                        executive_summary=f"Отсеяно на 1-м этапе (Mistral): {reason}",
                        complexity=2,
                        pure_dev_hours=0.0,
                        risks_and_pitfalls=[],
                        proposal_text="",
                    )
            except Exception as e:
                logger.warning("Сбой этапа 1 (Mistral quick_classify): %s. Переход к Antigravity.", e)

        # Стадия 2: Глубокий анализ и генерация отклика через Antigravity
        try:
            return await self.antigravity.analyze_order(order)
        except Exception as e:
            logger.error("Сбой анализа Antigravity: %s. Пробуем резервный Mistral...", e)
            if self.mistral.api_key:
                return await self.mistral.analyze_order(order)
            raise
