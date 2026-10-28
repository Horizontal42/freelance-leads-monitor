"""Mistral API client for LLM analysis with rate limiting, exponential backoff, and fallback."""

import asyncio
import json
import logging
from typing import Any, Dict, Optional
import httpx
from tenacity import (
    AsyncRetrying,
    before_sleep_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)
from src.analyzer.base import BaseLLMClient
from src.analyzer.prompts import build_analysis_prompt, build_proposal_prompt, build_chat_prompt
from src.config import settings
from src.models.analysis import AnalysisResult, ProposalResult
from src.models.order import OrderPriority, RawOrder

logger = logging.getLogger(__name__)


class MistralRateLimitError(RuntimeError):
    """Исключение при 429 Rate Limit / Backend out of capacity от Mistral API."""
    pass


class AsyncRateLimiter:
    """Интервальный rate limiter для соблюдения ограничений RPM (запросов в минуту)."""

    def __init__(self, rpm: int = 30) -> None:
        self.interval = 60.0 / max(rpm, 1)
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            elapsed = now - self._last_call
            if elapsed < self.interval:
                await asyncio.sleep(self.interval - elapsed)
            self._last_call = loop.time()


def is_retryable_mistral_error(exc: BaseException) -> bool:
    """Проверка, является ли ошибка временной для повторной попытки (429, 5xx, timeout)."""
    if isinstance(exc, (MistralRateLimitError, httpx.TimeoutException, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in [429, 500, 502, 503, 504]
    return False


class MistralClient(BaseLLMClient):
    """Клиент анализа заказов через Mistral API с Rate Limiter, tenacity retry и fallback."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_concurrency: Optional[int] = None,
        rpm_limit: Optional[int] = None,
        retry_attempts: Optional[int] = None,
        retry_min_wait: Optional[float] = None,
        retry_max_wait: Optional[float] = None,
        fallback_client: Optional[BaseLLMClient] = None,
    ) -> None:
        self.api_key = api_key or settings.MISTRAL_API_KEY
        self.model = model or settings.MISTRAL_MODEL
        self.fallback_client = fallback_client

        # Лимиты и таймауты определяются с учетом профиля выбранной модели (8b vs 14b)
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.MISTRAL_TIMEOUT
        )
        self.max_concurrency = (
            max_concurrency
            if max_concurrency is not None
            else settings.MISTRAL_MAX_CONCURRENCY
        )
        self.rpm_limit = (
            rpm_limit if rpm_limit is not None else settings.MISTRAL_RPM_LIMIT
        )
        self.retry_attempts = (
            retry_attempts
            if retry_attempts is not None
            else getattr(settings, "MISTRAL_RETRY_ATTEMPTS", 3)
        )
        self.retry_min_wait = (
            retry_min_wait
            if retry_min_wait is not None
            else getattr(settings, "MISTRAL_RETRY_MIN_WAIT", 2.0)
        )
        self.retry_max_wait = (
            retry_max_wait
            if retry_max_wait is not None
            else getattr(settings, "MISTRAL_RETRY_MAX_WAIT", 10.0)
        )

        self.api_url = "https://api.mistral.ai/v1/chat/completions"
        self.semaphore = asyncio.Semaphore(self.max_concurrency)
        self.rate_limiter = AsyncRateLimiter(rpm=self.rpm_limit)

    def _sanitize_proposal(self, text: str) -> str:
        """Гарантированная замена длинных тире на дефисы."""
        return text.replace("—", "-").replace("–", "-")

    async def _post_chat_completion(
        self,
        client: httpx.AsyncClient,
        headers: Dict[str, str],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Отправка HTTP запроса к Mistral API с динамическим tenacity retry на 429 и 5xx."""
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(self.retry_attempts),
            wait=wait_exponential(
                multiplier=2, min=self.retry_min_wait, max=self.retry_max_wait
            ),
            retry=retry_if_exception(is_retryable_mistral_error),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        ):
            with attempt:
                resp = await client.post(self.api_url, headers=headers, json=payload)
                if resp.status_code == 429:
                    err_body = resp.text
                    logger.warning(
                        "Mistral API 429 rate limit / capacity: %s. Запуск retry...",
                        err_body[:200],
                    )
                    raise MistralRateLimitError(f"Mistral API 429: {err_body}")

                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        message=f"Mistral server error {resp.status_code}: {resp.text}",
                        request=resp.request,
                        response=resp,
                    )

                if resp.status_code != 200:
                    raise RuntimeError(
                        f"Mistral API вернул ошибку {resp.status_code}: {resp.text}"
                    )

                return resp.json()

    async def _execute_with_rate_limit(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Выполнить запрос с учетом ограничений семафора и RPM."""
        async with self.semaphore:
            await self.rate_limiter.acquire()
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                return await self._post_chat_completion(client, headers, payload)

    async def analyze_order(self, order: RawOrder) -> AnalysisResult:
        """Проанализировать заказ через Mistral API с мягким fallback на Antigravity при отказе."""
        if not self.api_key:
            if self.fallback_client:
                logger.warning("MISTRAL_API_KEY не задан. Мягкий fallback на AntigravityClient...")
                return await self.fallback_client.analyze_order(order)
            raise ValueError("MISTRAL_API_KEY не задан в конфигурации (.env)")

        prompt = build_analysis_prompt(order)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        try:
            result_json = await self._execute_with_rate_limit(payload)
            content = result_json["choices"][0]["message"]["content"]
            data = json.loads(content)

            for key in [
                "proposal_text", "executive_summary", "company_overview",
                "candidate_requirements", "job_responsibilities", "match_reason",
                "skills_gap", "skills_gap_counter", "price_justification"
            ]:
                if key in data and isinstance(data[key], str):
                    data[key] = self._sanitize_proposal(data[key])

            if not data.get("matched_project"):
                data["matched_project"] = "Общий бэкграунд (Python Backend)"

            if isinstance(data.get("price_justification"), dict):
                data["price_justification"] = " ".join(
                    f"{k}: {v}" for k, v in data["price_justification"].items() if v
                )

            score = int(data.get("score", 5))
            if "priority" not in data or data["priority"] not in ["hot", "normal"]:
                data["priority"] = (
                    OrderPriority.HOT.value
                    if score >= settings.HOT_SCORE_THRESHOLD
                    else OrderPriority.NORMAL.value
                )

            return AnalysisResult.model_validate(data)

        except Exception as e:
            logger.warning(
                "Сбой анализа Mistral для заказа [%s #%s] после ретраев: %s",
                order.source.value,
                order.external_id,
                e,
            )
            if self.fallback_client:
                logger.info(
                    "Выполняется мягкий fallback на AntigravityClient для заказа [%s #%s]...",
                    order.source.value,
                    order.external_id,
                )
                return await self.fallback_client.analyze_order(order)
            raise

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
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        try:
            result_json = await self._execute_with_rate_limit(payload)
            content = result_json["choices"][0]["message"]["content"]
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
            if self.fallback_client:
                return await self.fallback_client.generate_proposal(order, analysis_data)
            raise ValueError("MISTRAL_API_KEY не задан в конфигурации (.env)")

        prompt = build_proposal_prompt(order, analysis_data)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }

        try:
            result_json = await self._execute_with_rate_limit(payload)
            content = result_json["choices"][0]["message"]["content"].strip()
            # Попытка извлечь JSON если есть
            try:
                json_str = self._clean_json_output(content)
                parsed = json.loads(json_str)
                if isinstance(parsed, dict) and "proposal_text" in parsed:
                    rec_price = None
                    if parsed.get("recommended_price"):
                        try:
                            rec_price = float(parsed["recommended_price"])
                        except (ValueError, TypeError):
                            pass
                    price_just = parsed.get("price_justification")
                    return ProposalResult(
                        self._sanitize_proposal(str(parsed["proposal_text"]).strip()),
                        recommended_price=rec_price,
                        price_justification=str(price_just) if price_just else None,
                    )
            except Exception:
                pass

            return ProposalResult(self._sanitize_proposal(content))
        except Exception as e:
            logger.warning("Сбой генерации отклика Mistral: %s", e)
            if self.fallback_client:
                return await self.fallback_client.generate_proposal(order, analysis_data)
            raise

    async def chat_order(
        self,
        order: RawOrder,
        analysis_data: Optional[Dict[str, Any]] = None,
        proposal_text: Optional[str] = None,
        history: Optional[list] = None,
        user_message: str = "",
        model_preference: Optional[str] = None,
    ) -> tuple[str, str]:
        """Ответить на вопрос по заказу через Mistral API."""
        if not self.api_key:
            if self.fallback_client:
                return await self.fallback_client.chat_order(
                    order, analysis_data, proposal_text, history, user_message, model_preference
                )
            raise ValueError("MISTRAL_API_KEY не задан в конфигурации (.env)")

        prompt = build_chat_prompt(order, analysis_data, proposal_text, history, user_message)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
        }

        try:
            result_json = await self._execute_with_rate_limit(payload)
            content = result_json["choices"][0]["message"]["content"].strip()
            return self._sanitize_proposal(content), f"Mistral ({self.model})"
        except Exception as e:
            logger.warning("Сбой ответа Mistral в чате по заказу: %s", e)
            if self.fallback_client:
                return await self.fallback_client.chat_order(
                    order, analysis_data, proposal_text, history, user_message, model_preference
                )
            raise
