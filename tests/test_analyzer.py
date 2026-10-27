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
        attachments_text="[Файл: requirements.txt (45 байт)]\ncurl_cffi>=0.7.0",
    )
    prompt = build_analysis_prompt(order)
    assert "Speech Analytics" in prompt
    assert "Avia_Pars" in prompt
    assert "5526844" in prompt
    assert "Python-разработчик" in prompt
    assert "requirements.txt" in prompt
    # Гарантируем, что внешняя ссылка НЕ передается модели (модель не тратит токены на экспорт)
    assert "https://www.fl.ru/projects/5526844" not in prompt
    assert "Все материалы задачи и файлы уже полностью извлечены" in prompt


def test_build_proposal_prompt_includes_attachments():
    from src.analyzer.prompts import build_proposal_prompt

    order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="777",
        title="Парсер цен конкурентов",
        description="Нужно собрать цены",
        url="https://kwork.ru/777",
        price=20000,
        attachments_text="[Файл: categories.json (150 байт)]",
    )
    proposal_prompt = build_proposal_prompt(order, {"matched_project": "Avia_Pars"})
    assert "categories.json" in proposal_prompt
    assert "Avia_Pars" in proposal_prompt
    assert "https://kwork.ru/777" not in proposal_prompt


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


def test_analysis_result_resilient_parsing():
    """Проверяем устойчивость Pydantic-модели к нестандартным ответам LLM (null в matched_project, dict в price_justification)."""
    raw_payload = {
        "take_order": True,
        "score": 8,
        "priority": "hot",
        "executive_summary": ["Суть задачи 1.", "Суть задачи 2."],
        "recommended_price": 25000,
        "price_justification": {"budget_analysis": "Бюджет адекватен", "strategy": "Без торга"},
        "matched_project": None,
        "proposal_text": "",
    }
    result = AnalysisResult.model_validate(raw_payload)
    assert result.matched_project == "Общий бэкграунд (Python Backend)"
    assert "Бюджет адекватен" in result.price_justification
    assert "Суть задачи 1." in result.executive_summary
