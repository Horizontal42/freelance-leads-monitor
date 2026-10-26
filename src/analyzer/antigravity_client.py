"""Antigravity CLI runner for LLM analysis."""

import asyncio
import json
import logging
import re
from typing import Any, Dict, Optional
from src.analyzer.base import BaseLLMClient
from src.analyzer.prompts import build_analysis_prompt, build_proposal_prompt
from src.config import settings
from src.models.analysis import AnalysisResult
from src.models.order import OrderPriority, RawOrder

logger = logging.getLogger(__name__)


class AntigravityClient(BaseLLMClient):
    """Клиент анализа заказов через локальный CLI Antigravity (agy -p)."""

    def __init__(
        self,
        binary_path: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        self.binary_path = binary_path or settings.ANTIGRAVITY_BIN
        self.model = model or settings.ANTIGRAVITY_MODEL
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.ANTIGRAVITY_TIMEOUT
        )

    def _clean_json_output(self, raw_text: str) -> str:
        """Извлечь чистый JSON-блок из текстового вывода модели."""
        # Удаляем markdown-блоки кода ```json ... ```
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)

        # Ищем внешние фигурные скобки
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            return cleaned[start_idx : end_idx + 1]
        return cleaned

    def _sanitize_proposal(self, text: str) -> str:
        """Гарантированная замена длинных тире на дефисы."""
        return text.replace("—", "-").replace("–", "-")

    async def analyze_order(self, order: RawOrder) -> AnalysisResult:
        """Запустить CLI agy и распарсить результат."""
        prompt = build_analysis_prompt(order)

        cmd = [
            self.binary_path,
            "-p",
            prompt,
            "--model",
            self.model,
            "--output-format",
            "text",
        ]

        logger.info(
            "Запуск анализа Antigravity для заказа %s (%s)",
            order.external_id,
            order.title[:40],
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError(
                f"Antigravity CLI превысил таймаут {self.timeout_seconds} сек"
            )

        if proc.returncode != 0:
            err_msg = stderr_bytes.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(
                f"Antigravity CLI завершился с ошибкой (код {proc.returncode}): {err_msg}"
            )

        output_text = stdout_bytes.decode("utf-8", errors="ignore").strip()
        json_str = self._clean_json_output(output_text)

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error("Не удалось распарсить JSON от Antigravity: %s", output_text[:300])
            raise ValueError(f"Ошибка декодирования JSON: {e}")

        # Пост-обработка текста отклика (строго дефисы)
        if "proposal_text" in data and isinstance(data["proposal_text"], str):
            data["proposal_text"] = self._sanitize_proposal(data["proposal_text"])

        # Проставляем приоритет на основе скора, если не выставлен
        score = int(data.get("score", 5))
        if "priority" not in data or data["priority"] not in ["hot", "normal"]:
            data["priority"] = (
                OrderPriority.HOT.value
                if score >= settings.HOT_SCORE_THRESHOLD
                else OrderPriority.NORMAL.value
            )

        return AnalysisResult.model_validate(data)

    async def generate_proposal(
        self,
        order: RawOrder,
        analysis_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Сгенерировать отклик на заказ по требованию."""
        prompt = build_proposal_prompt(order, analysis_data)
        cmd = [
            self.binary,
            "-p",
            prompt,
            "--model",
            self.model,
            "--output-format",
            "text",
        ]

        logger.info(
            "Запуск генерации отклика Antigravity для заказа %s (%s)",
            order.external_id,
            order.title[:40],
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError(
                f"Antigravity CLI превысил таймаут {self.timeout_seconds} сек при генерации отклика"
            )

        if proc.returncode != 0:
            err_msg = stderr_bytes.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(
                f"Antigravity CLI завершился с ошибкой (код {proc.returncode}): {err_msg}"
            )

        output_text = stdout_bytes.decode("utf-8", errors="ignore").strip()
        # Очищаем от markdown блоков если есть
        output_text = re.sub(r"^```[a-zA-Z]*\n", "", output_text)
        output_text = re.sub(r"\n```$", "", output_text).strip()
        return self._sanitize_proposal(output_text)
