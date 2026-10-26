"""Mistral API client for LLM analysis."""

import json
import logging
import re
from typing import Any, Dict, Optional
import httpx
from src.analyzer.base import BaseLLMClient
from src.analyzer.prompts import build_analysis_prompt, build_proposal_prompt
from src.config import settings
from src.models.analysis import AnalysisResult
from src.models.order import OrderPriority, RawOrder

logger = logging.getLogger(__name__)


class MistralClient(BaseLLMClient):
    """Клиент анализа заказов через официальный Mistral API (ministral/codestral)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        self.api_key = api_key or settings.MISTRAL_API_KEY
        self.model = model or settings.MISTRAL_MODEL
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.MISTRAL_TIMEOUT
        )
        self.api_url = "https://api.mistral.ai/v1/chat/completions"

    def _sanitize_proposal(self, text: str) -> str:
        """Гарантированная замена длинных тире на дефисы."""
        return text.replace("—", "-").replace("–", "-")

    async def analyze_order(self, order: RawOrder) -> AnalysisResult:
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY не задан в конфигурации (.env)")

        prompt = build_analysis_prompt(order)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(self.api_url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Mistral API вернул ошибку {resp.status_code}: {resp.text}"
                )

            result_json = resp.json()
            content = result_json["choices"][0]["message"]["content"]
            data = json.loads(content)

            if "proposal_text" in data and isinstance(data["proposal_text"], str):
                data["proposal_text"] = self._sanitize_proposal(data["proposal_text"])

            score = int(data.get("score", 5))
            if "priority" not in data or data["priority"] not in ["hot", "normal"]:
                data["priority"] = (
                    OrderPriority.HOT.value
                    if score >= settings.HOT_SCORE_THRESHOLD
                    else OrderPriority.NORMAL.value
                )

            return AnalysisResult.model_validate(data)

    async def quick_classify(self, order: RawOrder) -> dict:
        """Быстрый скоринг заказа (до 500мс) для первичного отсева."""
        if not self.api_key:
            return {"is_relevant": True, "quick_score": 7, "reason": "No API key, passed"}

        prompt = (
            f"Оцени заказ для Python Middle разработчика (боты, парсеры, FastAPI, автоматизация, CRM):\n"
            f"Заголовок: {order.title}\n"
            f"Описание: {order.description[:350]}\n"
            f"Бюджет: {order.price or 'Договорной'}\n\n"
            f"Верни строго JSON: {{\"is_relevant\": true/false, \"quick_score\": 1-10, \"reason\": \"кратко\"}}"
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self.api_url, headers=headers, json=payload)
                if resp.status_code == 200:
                    content = resp.json()["choices"][0]["message"]["content"]
                    return json.loads(content)
        except Exception as e:
            logger.warning("Ошибка быстрого скоринга Mistral: %s", e)
        return {"is_relevant": True, "quick_score": 7, "reason": "Fallback to deep analysis"}

    async def generate_proposal(
        self,
        order: RawOrder,
        analysis_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Сгенерировать отклик через Mistral API."""
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY не задан в конфигурации (.env)")

        prompt = build_proposal_prompt(order, analysis_data)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.post(self.api_url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Mistral API вернул ошибку {resp.status_code}: {resp.text}"
                )
            content = resp.json()["choices"][0]["message"]["content"].strip()
            return self._sanitize_proposal(content)
