"""Factory for creating LLM client instances."""

import logging
from src.analyzer.antigravity_client import AntigravityClient
from src.analyzer.base import BaseLLMClient
from src.analyzer.hybrid_client import HybridLLMClient
from src.analyzer.mistral_client import MistralClient
from src.config import settings

logger = logging.getLogger(__name__)


def get_llm_client() -> BaseLLMClient:
    """Получить настроенный экземпляр LLM клиента."""
    provider = settings.LLM_PROVIDER.lower().strip()
    if provider == "mistral":
        logger.info("Инициализирован LLM провайдер: Mistral (%s)", settings.MISTRAL_MODEL)
        return MistralClient()

    if provider == "hybrid":
        logger.info(
            "Инициализирован гибридный LLM каскад: Mistral (%s) -> Antigravity (%s)",
            settings.MISTRAL_MODEL,
            settings.ANTIGRAVITY_MODEL,
        )
        return HybridLLMClient()

    # По умолчанию используем Antigravity
    logger.info(
        "Инициализирован LLM провайдер: Antigravity (%s)",
        settings.ANTIGRAVITY_MODEL,
    )
    return AntigravityClient()
