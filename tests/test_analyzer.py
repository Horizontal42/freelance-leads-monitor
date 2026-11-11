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


def test_extract_clean_proposal_payload_robustness():
    """Тест надежности извлечения отклика из невалидного/сырого JSON с неэкранированными переводами строк."""
    from src.models.analysis import extract_clean_proposal_payload

    # 1. Сырой JSON с реальными переводами строк внутри кавычек
    raw = '''```json
{
  "market_price": 55000,
  "recommended_price": 48000,
  "estimated_days": "3-5 дней",
  "price_justification": "
  Рыночная стоимость: 50-60к.
  Рекомендуем 48к.
  ",
  "proposal_text": "
  Добрый день! Разрабатываю ботов на Python (aiogram 3).
  Реализация займет 3-5 дней.
  "
}
```'''
    res = extract_clean_proposal_payload(raw)
    assert res["market_price"] == 55000.0
    assert res["recommended_price"] == 48000.0
    assert res["estimated_days"] == "3-5 дней"
    assert "Добрый день!" in res["proposal_text"]
    assert "Рыночная стоимость" in res["price_justification"]

    # 2. Обычный плоский текст без JSON
    plain = "Привет! Готов выполнить ваш заказ за 3 дня."
    res_plain = extract_clean_proposal_payload(plain)
    assert res_plain["proposal_text"] == plain
    assert res_plain["recommended_price"] is None


def test_analysis_result_clean_vacancy_formatting():
    """Тест очистки сырых структур списков и словарей Python/JSON в полях анализа вакансий."""
    from src.models.analysis import AnalysisResult, PertEstimate

    raw_reqs = "['Python (обязательно)', 'PyTorch (базовый)'] {'years': '1-3 года', 'role': 'Junior ML'} ['Docker']"
    raw_match = "['Опыт с **YOLOv8** (AgroTech CV)', 'Работа с **FastAPI**']"

    analysis = AnalysisResult(
        take_order=True,
        score=8,
        priority="hot",
        candidate_requirements=raw_reqs,
        match_reason=raw_match,
        pert=PertEstimate(
            optimistic_days=1.0,
            most_likely_days=2.0,
            pessimistic_days=3.0,
            expected_days=2.0,
            sigma=0.3,
        ),
        realistic_days=2.0,
        complexity=3,
        pure_dev_hours=4.0,
        matched_project="Cortex IT",
        executive_summary="Разработка ML",
    )

    # Проверяем, что нет сырых скобок Python-списков
    assert "['" not in analysis.candidate_requirements
    assert "']" not in analysis.candidate_requirements
    assert "{" not in analysis.candidate_requirements
    assert "• Python (обязательно)" in analysis.candidate_requirements
    assert "Опыт: 1-3 года" in analysis.candidate_requirements

    assert "['" not in analysis.match_reason
    assert "• Опыт с **YOLOv8** (AgroTech CV)" in analysis.match_reason


def test_sanitize_proposal_text_markdown_and_emdash_removal():
    """Тест автоматической очистки отклика от жирного шрифта (**), курсива (*), em-dash и заголовков."""
    from src.models.analysis import sanitize_proposal_text

    raw_proposal = (
        "Добрый день! По вашей задаче сделаю интеграцию с **Битрикс24**.\n"
        "### Сроки и детали\n"
        "По срокам: сделаем за **2-3 недели** (или *10-12 дней*).\n"
        "Опыт \u2014 коммерческая разработка B2B \u2013 речевая аналитика.\n\n"
        "Буду рад обсудить задачи ROOMGRAM, кейсы автоматизации и детали решений на звонке или личной встрече.\n\n"
        "Telegram: @Horizontal84\n\n"
        "Спасибо за внимание. Готов обсудить задачи и проекты на звонке."
    )
    cleaned = sanitize_proposal_text(raw_proposal)
    assert "**" not in cleaned
    assert "*" not in cleaned
    assert "###" not in cleaned
    assert "\u2014" not in cleaned
    assert "\u2013" not in cleaned
    assert "Буду рад обсудить" not in cleaned
    assert "Готов обсудить" not in cleaned
    assert "Спасибо за внимание" not in cleaned
    assert "Битрикс24" in cleaned
    assert "2-3 недели" in cleaned
    assert "10-12 дней" in cleaned
    assert "Telegram: @Horizontal84" in cleaned
    assert "Опыт - коммерческая разработка B2B - речевая аналитика." in cleaned


def test_sanitize_proposal_text_zdravstvuyte_comma():
    """Тест автоматической замены точки на запятую после 'Здравствуйте'."""
    from src.models.analysis import sanitize_proposal_text

    raw_1 = "Здравствуйте. Занимаюсь бэкенд-разработкой на Python: строю API и ботов."
    assert sanitize_proposal_text(raw_1) == "Здравствуйте, занимаюсь бэкенд-разработкой на Python: строю API и ботов."

    raw_2 = "Здравствуйте.\n\nЗанимаюсь прикладными AI-агентами."
    assert sanitize_proposal_text(raw_2) == "Здравствуйте, занимаюсь прикладными AI-агентами."

    raw_2b = "Здравствуйте,\n\nЗанимаюсь прикладными AI-агентами."
    assert sanitize_proposal_text(raw_2b) == "Здравствуйте, занимаюсь прикладными AI-агентами."

    raw_3 = "Здравствуйте. AI-инженер с опытом продакшена."
    assert sanitize_proposal_text(raw_3) == "Здравствуйте, AI-инженер с опытом продакшена."

    raw_4 = "Здравствуйте."
    assert sanitize_proposal_text(raw_4) == "Здравствуйте,"

    raw_5 = "здравствуйте. разрабатываю парсеры на Scrapy."
    assert sanitize_proposal_text(raw_5) == "здравствуйте, разрабатываю парсеры на Scrapy."


def test_sanitize_proposal_text_unescapes_literal_newlines():
    """Тест автоматического разворачивания строковых \\n\\n в реальные переносы строк."""
    from src.models.analysis import sanitize_proposal_text

    raw = "Добрый день.\\n\\nИнженерная реализация ключевых узлов:\\n1. Интеграция с MeHotel"
    res = sanitize_proposal_text(raw)
    assert "\\n" not in res
    assert "\n\n" in res
    assert "Инженерная реализация ключевых узлов:\n1. Интеграция с MeHotel" in res


def test_sanitize_proposal_text_removes_flattery_and_gaps():
    """Тест автоматического удаления клише 'вакансия соответствует', '3. Почему подхожу' и 'готовность освоить'."""
    from src.models.analysis import sanitize_proposal_text

    raw = (
        "Здравствуйте, занимаюсь разработкой бэкенда на Python.\n\n"
        "Ваша вакансия полностью соответствует моему опыту. Расскажу о проекте, который максимально близок вашим задачам:\n\n"
        "1. Речевая аналитика звонков (B2B-система под ключ)\n"
        "   - FastAPI, Celery, WhisperX.\n\n"
        "2. Стек и релевантные навыки\n"
        "   - Python 3.12+, PostgreSQL, Docker.\n\n"
        "3. Почему подхожу для вашей команды\n"
        "   - Прямой опыт интеграций с CRM.\n"
        "   - Готовность быстро освоить amoCRM по аналогии с Bitrix24.\n\n"
        "GitHub с примерами открытого кода: https://github.com/Horizontal42 (коммерческие проекты закрыты NDA)."
    )
    res = sanitize_proposal_text(raw)
    assert "полностью соответствует моему опыту" not in res
    assert "максимально близок вашим задачам" not in res
    assert "Почему подхожу" not in res
    assert "Готовность быстро освоить" not in res
    assert "1. Речевая аналитика звонков" in res
    assert "2. Стек и релевантные навыки" in res
    assert "Telegram: @Horizontal84" in res
    assert "Email: pimenoffandrew@gmail.com" in res


def test_extract_clean_proposal_payload_with_unescaped_quotes():
    """Тест извлечения proposal_text и price_justification при наличии неэкранированных кавычек."""
    from src.models.analysis import extract_clean_proposal_payload

    raw_json = """{
      "market_price": 50000,
      "recommended_price": 25000,
      "proposal_text": "Добрый день. По вашей задаче с AI-консультантом на n8n:

  1. Структуризация промптов:
     - Разбить текущие промпты на модули по сценариям (например, "квалификация", "сравнение устройств").
  2. Внедрение слоя памяти на Redis.
  3. Оптимизация токенов.",
      "price_justification": "Рыночная стоимость (поиск на Kwork / FL.ru, например, "чат-боты e-commerce") ~45 000 руб.",
      "estimated_days": "3-4 дня"
    }"""

    res = extract_clean_proposal_payload(raw_json)
    assert res["recommended_price"] == 25000.0
    assert res["market_price"] == 50000.0
    assert res["estimated_days"] == "3-4 дня"
    assert "квалификация" in res["proposal_text"]
    assert "сравнение устройств" in res["proposal_text"]
    assert "2. Внедрение слоя памяти на Redis." in res["proposal_text"]
    assert "3. Оптимизация токенов." in res["proposal_text"]
    assert "чат-боты e-commerce" in res["price_justification"]


def test_sanitize_proposal_text_remove_meta_headers():
    """Тест автоматического удаления шаблонных мета-заголовков вида 'Почему подхожу...' и лести компании."""
    from src.models.analysis import sanitize_proposal_text

    raw = (
        "Здравствуйте, Алина.\n\n"
        "Занимаюсь разработкой бэкенд-систем на Python.\n\n"
        "Почему подхожу на роль Backend Engineer в Вашем инвесторе:\n\n"
        "1. Стек и архитектура:\n"
        "   - FastAPI и PostgreSQL.\n\n"
        "Почему Ваш инвестор:\n"
        "- Ценю прозрачность и культуру компании.\n"
        "- Интересны финтех-проекты.\n\n"
        "Telegram: @Horizontal84"
    )

    cleaned = sanitize_proposal_text(raw)
    assert "Почему подхожу" not in cleaned
    assert "Почему Ваш инвестор" not in cleaned
    assert "Ценю прозрачность" not in cleaned
    assert "1. Стек и архитектура:" in cleaned
    assert "FastAPI и PostgreSQL." in cleaned
    assert "Telegram: @Horizontal84" in cleaned


def test_trim_text_to_char_limit_and_kwork_sanitization():
    from src.models.analysis import sanitize_proposal_text, trim_text_to_char_limit

    # 1. Текст короче лимита не изменяется
    short_text = "Добрый день. Разработаю бота на aiogram за 3 дня."
    assert trim_text_to_char_limit(short_text, max_chars=2000) == short_text

    # 2. Длинный текст (2500+ символов) аккуратно обрезается до <= 2000
    paragraphs = [
        f"Параграф {i}: Настройка микросервисной архитектуры на базе FastAPI, PostgreSQL и Celery с брокером сообщений Redis. " * 3
        for i in range(1, 10)
    ]
    long_text = "\n\n".join(paragraphs)
    assert len(long_text) > 2400

    trimmed = trim_text_to_char_limit(long_text, max_chars=2000)
    assert len(trimmed) <= 2000
    assert len(trimmed) >= 1500
    # Проверяем, что обрезка произошла аккуратно по границе (точка или перенос)
    assert trimmed.endswith(".") or trimmed.endswith("\n")

    # 3. Проверяем sanitize_proposal_text с max_len
    sanitized = sanitize_proposal_text(long_text, max_len=2000)
    assert len(sanitized) <= 2000


@pytest.mark.asyncio
async def test_kwork_proposal_prompt_and_client_limit(monkeypatch):
    from src.analyzer.antigravity_client import AntigravityClient
    from src.analyzer.prompts import build_proposal_prompt
    from src.models.order import RawOrder, SourcePlatform

    order_kwork = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="kw_test_99",
        title="Разработка Telegram-бота",
        description="Сложный бот с CRM",
        url="https://kwork.ru/projects/99",
        price=30000,
    )

    # 1. Проверяем наличие требования о 2000 символов в промпте Kwork
    prompt = build_proposal_prompt(order_kwork)
    assert "2 000 СИМВОЛОВ" in prompt or "2000" in prompt
    assert "KWORK" in prompt

    # 2. Мокаем вывод Antigravity с текстом длиннее 2000 символов
    client = AntigravityClient()
    overlong_proposal = "Здравствуйте, по вашей задаче на Kwork: представляю архитектурный план. " + ("Подробный пункт реализации архитектуры и интеграций. " * 70)
    assert len(overlong_proposal) > 2300

    import json
    fake_payload = json.dumps({
        "market_price": 35000,
        "recommended_price": 30000,
        "estimated_days": "3 дня",
        "price_justification": "Адекватный бюджет",
        "proposal_text": overlong_proposal,
    }, ensure_ascii=False)

    async def mock_communicate(*args, **kwargs):
        return fake_payload.encode("utf-8"), b""

    class DummyProc:
        returncode = 0
        communicate = mock_communicate
        def kill(self): pass

    async def mock_create_subprocess_exec(*args, **kwargs):
        return DummyProc()

    import asyncio
    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_create_subprocess_exec)

    result = await client.generate_proposal(order_kwork)
    assert len(result) <= 2000
    assert len(result.proposal_text) <= 2000


def test_sanitize_internal_project_codenames():
    """Проверяем автоматическую замену внутренних кодовых имен репозиториев (Avia_Pars и др.) на человеческий текст."""
    from src.models.analysis import sanitize_proposal_text

    raw_text = (
        "Добрый день. По вашей задаче обхода rate-limit предлагаю архитектуру (как в Avia_Pars) "
        "на базе проверенного стека Avia_Pars с адаптацией под API. "
        "Тестирование: 200+ тестов (как в Avia_Pars). "
        "В проекте Speech Analytics делали скоринг. "
        "Также утилита netsleuth и пайплайн leads-monitor."
    )
    clean = sanitize_proposal_text(raw_text)
    assert "Avia_Pars" not in clean
    assert "Speech Analytics" not in clean
    assert "netsleuth" not in clean
    assert "leads-monitor" not in clean
    assert "в аналогичном проекте" in clean
    assert "—" not in clean


def test_sanitize_sycophantic_blocks_and_connectors():
    """Проверяем вырезание шаблонных подводок и списков самосоответствия."""
    from src.models.analysis import sanitize_proposal_text

    raw_text = (
        "Здравствуйте, разрабатываю AI-решения на Python.\n\n"
        "Мой опыт тесно пересекается с задачами УАЗ / «Цифровые решения»:\n\n"
        "1. LLM и ML\n- Опыт с WhisperX.\n\n"
        "Почему подхожу для вашей команды\n"
        "- Опыт работы с LLM в продакшене.\n"
        "- Готовность быстро освоить Kubernetes.\n\n"
        "Контакты:\nTelegram: @Horizontal84"
    )
    clean = sanitize_proposal_text(raw_text)
    assert "Мой опыт тесно пересекается" not in clean
    assert "Почему подхожу" not in clean
    assert "быстро освоить Kubernetes" not in clean
    assert "1. LLM и ML" in clean
    assert "@Horizontal84" in clean


def test_normalize_extracted_price():
    """Проверяем нормализацию цен (пробелы, миллионы, тысячи)."""
    from src.models.analysis import normalize_extracted_price, extract_clean_proposal_payload

    assert normalize_extracted_price("1 000 000") == 1000000.0
    assert normalize_extracted_price("950 000") == 950000.0
    assert normalize_extracted_price(1.0) == 1000000.0
    assert normalize_extracted_price(950.0) == 950000.0
    assert normalize_extracted_price(280000) == 280000.0

    raw_json = '{"proposal_text": "Отклик", "recommended_price": 950, "market_price": 1.0}'
    payload = extract_clean_proposal_payload(raw_json)
    assert payload["recommended_price"] == 950000.0
    assert payload["market_price"] == 1000000.0


def test_format_matched_project():
    """Проверяем форматирование названий кейсов для UI и Telegram."""
    from src.models.analysis import format_matched_project

    assert format_matched_project("['RAG-ассистент', 'Avia_Pars']") == "Корпоративный RAG, Мониторинг цен (боты)"
    assert format_matched_project("Avia_Pars") == "Мониторинг цен (боты)"
    assert format_matched_project("Speech Analytics") == "Речевая аналитика"
    assert format_matched_project(None) is None









