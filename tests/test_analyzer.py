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


@pytest.mark.asyncio
async def test_mistral_rate_limit_retry_and_soft_fallback(monkeypatch):
    """Тест устойчивости MistralClient к 429: ретраи с экспоненциальным backoff и мягкий fallback на Antigravity."""
    from unittest.mock import AsyncMock
    from src.analyzer.mistral_client import MistralClient
    import httpx

    # Мок fallback-клиента
    mock_fallback = AsyncMock()
    fallback_res = AnalysisResult(
        take_order=True,
        score=8,
        priority=OrderPriority.HOT,
        executive_summary="Fallback анализ от Antigravity",
        recommended_price=25000,
        price_justification="Fallback",
        realistic_days=3.0,
        matched_project="Avia_Pars",
        complexity=5,
        pure_dev_hours=12.0,
        proposal_text="",
    )
    mock_fallback.analyze_order.return_value = fallback_res

    client = MistralClient(
        api_key="fake_key",
        fallback_client=mock_fallback,
    )

    order = RawOrder(
        source=SourcePlatform.FL_RU,
        external_id="123",
        title="Парсер цен",
        description="Стек: python",
        url="https://fl.ru/123",
        price=35000,
    )

    # Имитируем постоянный 429 backend_out_of_capacity
    call_count = 0
    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        req = httpx.Request("POST", "https://api.mistral.ai/v1/chat/completions")
        return httpx.Response(status_code=429, text='{"error": "backend_out_of_capacity"}', request=req)

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    # Запускаем анализ: должен исчерпать 3 ретрая и мягко передать управление в fallback_client
    res = await client.analyze_order(order)
    assert call_count == 3  # ровно 3 попытки ретрая
    assert res.executive_summary == "Fallback анализ от Antigravity"
    mock_fallback.analyze_order.assert_called_once_with(order)


@pytest.mark.asyncio
async def test_antigravity_effort_configuration(monkeypatch):
    """Тест того, что глубина рассуждений (--effort) берется из конфигурации пользователя или передается вручную."""
    import asyncio
    from unittest.mock import AsyncMock
    from src.analyzer.antigravity_client import AntigravityClient

    captured_cmds = []

    async def mock_subprocess_exec(*cmd, **kwargs):
        captured_cmds.append(list(cmd))
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            "Добрый день. Сделаем архитектуру на высшем уровне.".encode("utf-8"),
            b"",
        )
        mock_proc.returncode = 0
        return mock_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess_exec)

    client = AntigravityClient(effort="medium")

    order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="999",
        title="CRM и парсинг",
        description="Архитектура",
        url="https://kwork.ru/999",
        price=50000,
    )

    # 1. По умолчанию берется effort из конфига (без эвристических переопределений)
    proposal = await client.generate_proposal(order)
    assert "архитектуру" in proposal
    assert len(captured_cmds) == 1
    cmd1 = captured_cmds[0]
    assert "--effort" in cmd1
    assert cmd1[cmd1.index("--effort") + 1] == "medium"

    # 2. Если пользователь явно передает effort (например "high") - прокидывается он
    await client.generate_proposal(order, effort="high")
    assert len(captured_cmds) == 2
    cmd2 = captured_cmds[1]
    assert "--effort" in cmd2
    assert cmd2[cmd2.index("--effort") + 1] == "high"


def test_mistral_model_specific_profiles():
    """Тест раздельных профилей лимитов для ministral-8b-latest и ministral-14b-latest."""
    from src.config import YamlAppConfig

    # Профиль 8B
    raw_yaml_8b = {
        "llm": {
            "mistral": {
                "active_model": "ministral-8b-latest",
            }
        }
    }
    cfg_8b = YamlAppConfig.model_validate(raw_yaml_8b)
    from src.config import Settings
    s8 = Settings()
    s8.app_config = cfg_8b
    assert s8.MISTRAL_MODEL == "ministral-8b-latest"
    assert s8.MISTRAL_RPM_LIMIT == 150
    assert s8.MISTRAL_MAX_CONCURRENCY == 4
    assert s8.MISTRAL_TIMEOUT == 40.0

    # Профиль 14B
    raw_yaml_14b = {
        "llm": {
            "mistral": {
                "active_model": "ministral-14b-latest",
            }
        }
    }
    cfg_14b = YamlAppConfig.model_validate(raw_yaml_14b)
    s14 = Settings()
    s14.app_config = cfg_14b
    assert s14.MISTRAL_MODEL == "ministral-14b-latest"
    assert s14.MISTRAL_RPM_LIMIT == 25
    assert s14.MISTRAL_MAX_CONCURRENCY == 2
    assert s14.MISTRAL_TIMEOUT == 60.0


@pytest.mark.asyncio
async def test_antigravity_proposal_with_market_pricing_and_web_search(monkeypatch):
    """Тест генерации отклика Antigravity с рыночной оценкой через веб-поиск и сохранением в ProposalResult."""
    import asyncio
    from unittest.mock import AsyncMock
    from src.analyzer.antigravity_client import AntigravityClient
    from src.models.analysis import ProposalResult

    captured_cmds = []

    async def mock_subprocess_exec(*cmd, **kwargs):
        captured_cmds.append(list(cmd))
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            b'```json\n{"recommended_price": 45000, "price_justification": "\xd0\xa0\xd1\x8b\xd0\xbd\xd0\xbe\xd1\x87\xd0\xbd\xd0\xb0\xd1\x8f \xd1\x81\xd1\x82\xd0\xb0\xd0\xb2\xd0\xba\xd0\xb0 \xd0\xbf\xd0\xbe Kwork/FL: 40-50\xd0\xba", "proposal_text": "\xd0\x94\xd0\xbe\xd0\xb1\xd1\x80\xd1\x8b\xd0\xb9 \xd0\xb4\xd0\xb5\xd0\xbd\xd1\x8c. \xd0\xa1\xd0\xb4\xd0\xb5\xd0\xbb\xd0\xb0\xd0\xb5\xd0\xbc CRM \xd0\xb8\xd0\xbd\xd1\x82\xd0\xb5\xd0\xb3\xd1\x80\xd0\xb0\xd1\x86\xd0\xb8\xd1\x8e."}\n```',
            b"",
        )
        mock_proc.returncode = 0
        return mock_proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess_exec)

    client = AntigravityClient()
    order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="777",
        title="Интеграция Битрикс24 и amoCRM",
        description="Синхронизация сделок",
        url="https://kwork.ru/777",
        price=40000,
    )

    result = await client.generate_proposal(order)
    assert isinstance(result, ProposalResult)
    assert isinstance(result, str)
    assert "CRM интеграцию" in result
    assert result.recommended_price == 45000.0
    assert result.market_price is not None
    assert result.market_price >= result.recommended_price
    assert "Kwork/FL" in result.price_justification

    # Проверяем, что в промпт agy включена инструкция поиска в интернете
    assert len(captured_cmds) == 1
    prompt_arg = captured_cmds[0][2]
    assert "search_web" in prompt_arg or "поиск в интернете" in prompt_arg.lower()
