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


@pytest.mark.asyncio
async def test_hybrid_client_flow():
    from unittest.mock import AsyncMock
    from src.analyzer.hybrid_client import HybridLLMClient

    order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="111",
        title="Сделать Telegram-бота на Python",
        description="Нужен парсер и бот на aiogram 3",
        url="https://kwork.ru/111",
        price=15000,
    )

    expected_analysis = AnalysisResult(
        take_order=True,
        score=9,
        priority=OrderPriority.HOT,
        executive_summary="Разработка Telegram-бота на aiogram 3 с парсером данных. Специфика в стабильной работе фонового воркера. Ключевой риск - блокировка источника парсинга без ротации прокси.",
        recommended_price=20000,
        price_justification="Бюджет адекватен, но с учетом парсера стоит запросить 20к",
        realistic_days=3.0,
        matched_project="Avia_Pars",
        complexity=5,
        pure_dev_hours=10.0,
        risks_and_pitfalls=["Капча", "Частые запросы к источнику"],
        proposal_text="",
    )

    mock_mistral = AsyncMock()
    mock_mistral.api_key = "fake_key"
    mock_mistral.analyze_order.return_value = expected_analysis

    mock_antigravity = AsyncMock()
    mock_antigravity.generate_proposal.return_value = "Добрый день. Делал бота Avia_Pars на aiogram 3 с обходом блокировок."

    client = HybridLLMClient(mistral=mock_mistral, antigravity=mock_antigravity)

    # 1. Pipeline analysis is performed by Mistral
    res = await client.analyze_order(order)
    assert res.take_order is True
    assert res.score == 9
    assert res.priority == OrderPriority.HOT
    assert "Avia_Pars" in res.matched_project
    mock_mistral.analyze_order.assert_called_once_with(order)
    # agy was not called during ingestion analysis!
    mock_antigravity.analyze_order.assert_not_called()

    # 2. Proposal generation is performed by Antigravity on user demand
    proposal = await client.generate_proposal(order, {"matched_project": "Avia_Pars"})
    assert "Avia_Pars" in proposal
    mock_antigravity.generate_proposal.assert_called_once()
