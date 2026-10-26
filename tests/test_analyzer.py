"""Tests for LLM prompts and client output sanitization."""

import pytest
from src.analyzer.antigravity_client import AntigravityClient
from src.analyzer.prompts import build_analysis_prompt
from src.models.analysis import AnalysisResult
from src.models.order import OrderPriority, RawOrder, SourcePlatform


def test_build_analysis_prompt():
    order = RawOrder(
        source=SourcePlatform.FL_RU,
        external_id="5526844",
        title="Python-разработчик (Анти-фрод, обход Cloudflare)",
        description="Стек: curl_cffi, patchright, proxies",
        url="https://www.fl.ru/projects/5526844",
        price=25000,
    )
    prompt = build_analysis_prompt(order)
    assert "Speech Analytics" in prompt
    assert "Avia_Pars" in prompt
    assert "5526844" in prompt
    assert "Python-разработчик" in prompt


def test_antigravity_clean_json_and_sanitize():
    client = AntigravityClient()

    # Markdown fence test
    raw = """
    ```json
    {
      "take_order": true,
      "score": 9,
      "priority": "hot",
      "executive_summary": "Отличный мэтч с Avia_Pars",
      "recommended_price": 30000,
      "price_justification": "Вилка входа от 25к",
      "realistic_days": 3.0,
      "matched_project": "Avia_Pars",
      "complexity": 6,
      "pure_dev_hours": 10.0,
      "risks_and_pitfalls": ["WAF блокировки"],
      "proposal_text": "Добрый день. Делал бота — обход Cloudflare через curl_cffi — решим.",
      "pert": {
        "optimistic_days": 2.0,
        "most_likely_days": 3.0,
        "pessimistic_days": 5.0,
        "expected_days": 3.17,
        "sigma": 0.5
      }
    }
    ```
    """
    cleaned = client._clean_json_output(raw)
    assert cleaned.startswith("{") and cleaned.endswith("}")

    sanitized = client._sanitize_proposal("Делал бота — обход Cloudflare — решим.")
    assert "—" not in sanitized
    assert sanitized == "Делал бота - обход Cloudflare - решим."
