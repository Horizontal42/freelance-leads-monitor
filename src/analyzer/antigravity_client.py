"""Antigravity CLI runner for LLM analysis and deep reasoning proposal generation."""

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, Optional
from src.analyzer.base import BaseLLMClient
from src.analyzer.prompts import build_analysis_prompt, build_proposal_prompt, build_chat_prompt
from src.config import settings
from src.models.analysis import AnalysisResult, ProposalResult, extract_clean_proposal_payload, sanitize_proposal_text
from src.models.order import OrderPriority, RawOrder

logger = logging.getLogger(__name__)


class AntigravityClient(BaseLLMClient):
    """Клиент анализа заказов через локальный CLI Antigravity (agy -p). Уровень рассуждений задается пользователем."""

    def __init__(
        self,
        binary_path: Optional[str] = None,
        model: Optional[str] = None,
        effort: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        self.binary_path = binary_path or settings.ANTIGRAVITY_BIN
        self.binary = self.binary_path
        self.model = model or settings.ANTIGRAVITY_MODEL
        self.effort = effort or getattr(settings, "ANTIGRAVITY_EFFORT", "medium")
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
        """Гарантированная очистка отклика: дефисы, удаление звездочек (**) и markdown-мусора."""
        return sanitize_proposal_text(text)

    def _get_subprocess_env(self) -> Dict[str, str]:
        """Гарантирует передачу прокси-переменных в обоих регистрах для вызова agy CLI."""
        env = os.environ.copy()
        for k in ["http_proxy", "https_proxy", "all_proxy", "no_proxy"]:
            val = env.get(k) or env.get(k.upper())
            if val:
                env[k] = val
                env[k.upper()] = val
        return env

    async def analyze_order(self, order: RawOrder) -> AnalysisResult:
        """Запустить CLI agy и распарсить результат."""
        prompt = build_analysis_prompt(order)

        cmd = [
            self.binary_path,
            "-p",
            prompt,
            "--model",
            self.model,
            "--effort",
            self.effort,
            "--output-format",
            "text",
        ]

        logger.info(
            "Запуск анализа Antigravity для заказа %s (%s) [model: %s, effort: %s]",
            order.external_id,
            order.title[:40],
            self.model,
            self.effort,
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._get_subprocess_env(),
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

        # Гарантируем наличие market_price при наличии recommended_price
        if not data.get("market_price") and data.get("recommended_price"):
            try:
                rec_val = float(data["recommended_price"])
                hours = float(data.get("pure_dev_hours") or 0)
                if hours > 0:
                    data["market_price"] = max(rec_val, round(hours * 1200 / 500) * 500)
                else:
                    data["market_price"] = round(rec_val * 1.2 / 500) * 500
            except (ValueError, TypeError):
                pass

        # Проставляем приоритет на основе скора, если не выставлен
        score = int(data.get("score", 5))

        # Наивысший приоритет для AI-First и Agentic проектов
        if order.is_ai_first:
            score = max(score, 9)
            data["score"] = score
            data["priority"] = OrderPriority.HOT.value
            data["take_order"] = True
        elif "priority" not in data or data["priority"] not in ["hot", "normal"]:
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
        effort: Optional[str] = None,
        model: Optional[str] = None,
    ) -> str:
        """Сгенерировать отклик на заказ по требованию."""
        prompt = build_proposal_prompt(order, analysis_data)

        # Модель и уровень рассуждений задаются строго пользователем (из конфига или аргументов)
        selected_model = model or self.model
        selected_effort = effort or self.effort

        cmd = [
            self.binary_path,
            "-p",
            prompt,
            "--model",
            selected_model,
            "--output-format",
            "text",
        ]
        if selected_effort:
            cmd.extend(["--effort", selected_effort])

        logger.info(
            "Запуск генерации отклика Antigravity для заказа %s (%s) [model: %s, effort: %s]",
            order.external_id,
            order.title[:40],
            selected_model,
            selected_effort or "default",
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._get_subprocess_env(),
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
        payload = extract_clean_proposal_payload(output_text)

        rec_price = None
        if payload.get("recommended_price") is not None:
            try:
                rec_price = float(payload["recommended_price"])
            except (ValueError, TypeError):
                pass
        market_price = None
        if payload.get("market_price") is not None:
            try:
                market_price = float(payload["market_price"])
            except (ValueError, TypeError):
                pass
        if market_price is None and rec_price is not None:
            market_price = round(rec_price * 1.2 / 500) * 500

        price_just = payload.get("price_justification")
        if price_just:
            price_just = self._sanitize_proposal(str(price_just).strip())

        estimated_days = payload.get("estimated_days")
        if estimated_days:
            estimated_days = self._sanitize_proposal(str(estimated_days).strip())

        prop_text = self._sanitize_proposal(str(payload.get("proposal_text") or "").strip())

        return ProposalResult(
            prop_text,
            recommended_price=rec_price,
            price_justification=price_just,
            market_price=market_price,
            estimated_days=estimated_days,
        )

    async def chat_order(
        self,
        order: RawOrder,
        analysis_data: Optional[Dict[str, Any]] = None,
        proposal_text: Optional[str] = None,
        history: Optional[list] = None,
        user_message: str = "",
        model_preference: Optional[str] = None,
    ) -> tuple[str, str]:
        """Ответить на вопрос по заказу через Antigravity CLI (agy -p)."""
        prompt = build_chat_prompt(order, analysis_data, proposal_text, history, user_message)

        selected_model = (
            model_preference
            if model_preference and model_preference not in ["auto", "antigravity"]
            else self.model
        )
        selected_effort = self.effort

        cmd = [
            self.binary_path,
            "-p",
            prompt,
            "--model",
            selected_model,
            "--output-format",
            "text",
        ]
        if selected_effort:
            cmd.extend(["--effort", selected_effort])

        logger.info(
            "Запуск вопроса по заказу в Antigravity для заказа %s [model: %s]",
            order.external_id,
            selected_model,
        )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._get_subprocess_env(),
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise TimeoutError(
                f"Antigravity CLI превысил таймаут {self.timeout_seconds} сек при вопросе по заказу"
            )

        if proc.returncode != 0:
            err_msg = stderr_bytes.decode("utf-8", errors="ignore").strip()
            raise RuntimeError(
                f"Antigravity CLI завершился с ошибкой (код {proc.returncode}): {err_msg}"
            )

        output_text = stdout_bytes.decode("utf-8", errors="ignore").strip()
        cleaned_text = re.sub(r"^```[a-zA-Z]*\n", "", output_text)
        cleaned_text = re.sub(r"\n```$", "", cleaned_text).strip()
        return self._sanitize_proposal(cleaned_text), f"Antigravity ({selected_model})"
