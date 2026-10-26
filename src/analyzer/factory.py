"""Factory for creating LLM client instances."""

import logging
from src.analyzer.antigravity_client import AntigravityClient
from src.analyzer.base import BaseLLMClient
from src.analyzer.mistral_client import MistralClient
from src.config import settings

logger = logging.getLogger(__name__)


def get_llm_client() -> BaseLLMClient:
    """Получить настроенный экземпляр LLM клиента."""
    provider = settings.LLM_PROVIDER.lower().strip()
    if provider == "mistral":
        logger.info("Инициализирован LLM провайдер: Mistral (%s)", settings.MISTRAL_MODEL)
        return MistralClient()

    # По умолчанию используем Antigravity
    logger.info(
        "Инициализирован LLM провайдер: Antigravity (%s)",
        settings.ANTIGRAVITY_MODEL,
    )
    return AntigravityClient()
