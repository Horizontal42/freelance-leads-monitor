"""Tests for HeadHunter (hh.ru) collector, vacancy analysis, and web dashboard split views."""

import json
import pytest
import httpx
from src.collectors.hh_ru import HhRuCollector, strip_html, normalize_employer
from src.models.analysis import AnalysisResult
from src.models.order import OrderPriority, OrderStatus, RawOrder, SourcePlatform
from src.storage.db import init_db
from src.storage.repository import OrderRepository
from src.web.app import create_web_app


def test_strip_html_and_normalize_employer():
    assert strip_html("<p>Привет, <b>мир</b>!</p>") == "Привет, мир!"
    assert strip_html(None) == ""
    assert normalize_employer('ООО "Яндекс Крауд"') == "яндекс крауд"
    assert normalize_employer("АО «Тинькофф Банк»") == "тинькофф банк"


@pytest.mark.asyncio
async def test_hh_collector_missing_token_returns_empty():
    collector = HhRuCollector(token="")
    orders = await collector.fetch_new_orders()
    assert orders == []


@pytest.mark.asyncio
async def test_hh_collector_parsing_and_filtering(monkeypatch):
    sample_hh_response = {
        "items": [
            {
                "id": "1001",
                "name": "Junior AI Инженер / LLM разработчик",
                "employer": {"name": "ООО Сбер Образование"},
                "area": {"name": "Москва"},
                "work_format": [{"name": "Удаленная работа"}],
                "experience": {"name": "От 1 года до 3 лет"},
                "salary": {"from": 120000, "to": 160000, "currency": "RUR"},
                "alternate_url": "https://hh.ru/vacancy/1001?from=share",
                "snippet": {
                    "requirement": "Знание <highlighttext>Python</highlighttext>, FastAPI, опыт с LangChain и RAG.",
                    "responsibility": "Разработка AI-ассистентов и интеграция с LLM API.",
                },
            },
            {
                "id": "1002",
                "name": "Senior Lead AI Architect",
                "employer": {"name": "ООО МегаТех"},
                "area": {"name": "Москва"},
                "work_format": [{"name": "Офис"}],
                "experience": {"name": "Более 6 лет"},
                "salary": {"from": 500000, "to": 700000, "currency": "RUR"},
                "alternate_url": "https://hh.ru/vacancy/1002",
                "snippet": {"requirement": "10+ лет опыта", "responsibility": "Архитектура"},
            },
            {
                "id": "1003",
                "name": "SMM специалист по нейросетям",
                "employer": {"name": "ИП Иванов"},
                "area": {"name": "Казань"},
                "work_format": [],
                "experience": {"name": "Нет опыта"},
                "salary": None,
                "alternate_url": "https://hh.ru/vacancy/1003",
                "snippet": {"requirement": "Ведение соцсетей", "responsibility": "Посты"},
            },
        ]
    }

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, headers=None, params=None):
            class MockResponse:
                status_code = 200

                def json(self):
                    # Если пагинация page > 0, возвращаем пустой список
                    if params and params.get("page", 0) > 0:
                        return {"items": []}
                    return sample_hh_response

            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    collector = HhRuCollector(token="test_token_123")
    orders = await collector.fetch_new_orders()

    assert len(orders) == 1
    ord1 = orders[0]
    assert ord1.source == SourcePlatform.HH_RU
    assert ord1.external_id == "1001"
    assert ord1.title == "Junior AI Инженер / LLM разработчик"
    assert ord1.price == 160000.0
    assert not ord1.is_negotiable
    assert "Удаленная работа" in ord1.tags
    assert "Москва" in ord1.tags
    assert "ООО Сбер Образование" in ord1.attachments_text
    assert "Senior Lead AI Architect" not in [o.title for o in orders]
    assert "SMM специалист по нейросетям" not in [o.title for o in orders]


@pytest.mark.asyncio
async def test_web_split_sections_freelance_vs_hh(tmp_path):
    db_path = tmp_path / "test_split.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)

    # 1. Заказ с фриланс-биржи
    freelance_order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="fw-555",
        title="Разработка Telegram-бота на Python",
        description="Срочно нужен бот для приема заявок",
        url="https://kwork.ru/projects/555",
        price=25000,
    )
    fid = await repo.insert_raw_order(
        order=freelance_order,
        status=OrderStatus.ANALYZED,
        priority=OrderPriority.HOT,
    )
    f_analysis = AnalysisResult(
        take_order=True,
        score=9,
        priority=OrderPriority.HOT,
        executive_summary="Разработка Telegram-бота на aiogram 3.",
        recommended_price=28000,
        price_justification="Клиент дает 25к, рыночная цена 28к.",
        complexity=3,
        pure_dev_hours=5.0,
        realistic_days=1.5,
        matched_project="Avia_Pars",
    )
    await repo.update_analysis(fid, f_analysis)

    # 2. Вакансия с HeadHunter
    hh_order = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="hh-777",
        title="Младший AI-инженер (RAG, Speech Analytics)",
        description="Ищем разработчика в команду речевой аналитики и RAG.",
        url="https://hh.ru/vacancy/777",
        price=130000,
        attachments_text="🏢 Компания: Cortex AI Labs\n📍 Локация: Удаленно\n💰 Зарплата: 130 000 ₽",
    )
    hid = await repo.insert_raw_order(
        order=hh_order,
        status=OrderStatus.ANALYZED,
        priority=OrderPriority.HOT,
    )
    h_analysis = AnalysisResult(
        take_order=True,
        score=9,
        priority=OrderPriority.HOT,
        executive_summary="Разработка голосового ИИ и корпоративного RAG.",
        company_overview="Cortex AI Labs разрабатывает платформы речевой аналитики для крупного бизнеса.",
        candidate_requirements="Опыт с FastAPI, Whisper, векторными БД (Qdrant).",
        job_responsibilities="Проектирование и поддержка микросервисов транскрибации и RAG-поиска.",
        match_reason="100% совпадение с реальным опытом Андрея в Cortex IT (WhisperX + Qdrant + FastAPI).",
        skills_gap="Требуется опыт с Kubernetes и vLLM.",
        skills_gap_counter="Опереться на Docker Compose, оптимизацию памяти WhisperX через ctypes и батчинг на GPU.",
        risks_and_pitfalls=["Высокие требования к отказоустойчивости пайплайнов"],
        recommended_price=130000,
        price_justification="Адекватная рыночная вилка для Junior+/Middle",
        complexity=5,
        pure_dev_hours=0,
        realistic_days=0,
        matched_project="Cortex IT (RAG / Speech Analytics)",
    )
    await repo.update_analysis(hid, h_analysis)

    app = create_web_app(repo=repo)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        auth=("Horizontal42", "qaz403111"),
    ) as client:
        # 1. Проверяем раздел Фриланс-биржи
        resp_fl = await client.get("/?section=freelance")
        assert resp_fl.status_code == 200
        html_fl = resp_fl.text
        assert "Разработка Telegram-бота на Python" in html_fl
        assert "Младший AI-инженер" not in html_fl
        assert "Фриланс-биржи" in html_fl
        assert "28 000 ₽" in html_fl
        assert "(предв.)" in html_fl

        # 2. Проверяем раздел Вакансии HH.ru
        resp_hh = await client.get("/?section=hh_ru")
        assert resp_hh.status_code == 200
        html_hh = resp_hh.text
        assert "Младший AI-инженер" in html_hh
        assert "Разработка Telegram-бота на Python" not in html_hh
        assert "Вакансии и найм" in html_hh
        assert "Cortex AI Labs" in html_hh
        assert "О компании:" in html_hh
        assert "Требования к кандидату:" in html_hh
        assert "Чем предстоит заниматься:" in html_hh
        assert "Соответствие резюме Андрея:" in html_hh
        assert "100% совпадение с реальным опытом Андрея" in html_hh
        assert "Пробелы в требованиях (Skills Gap):" in html_hh
        assert "Требуется опыт с Kubernetes и vLLM" in html_hh
        assert "Парирование в Cover Letter:" in html_hh
        assert "Сгенерировать Cover Letter (agy)" in html_hh

        # 3. Проверяем вкладку Профиль поиска в HH
        resp_profile = await client.get("/?section=hh_ru&tab=profile")
        assert resp_profile.status_code == 200
        assert "Пименов Андрей Дмитриевич" in resp_profile.text
        assert "Речевая аналитика звонков" in resp_profile.text
        assert "Cortex IT" in resp_profile.text
        assert "Активные поисковые запросы hh.ru" in resp_profile.text


@pytest.mark.asyncio
async def test_compact_vacancy_telegram_card_and_buttons():
    """Проверка компактного формата карточки вакансии в Telegram и наличия ссылки на сайт."""
    from src.notifiers.telegram_notifier import TelegramNotifier
    from src.bot.keyboards import get_order_inline_keyboard

    notifier = TelegramNotifier(chat_id=12345, bot_token="123456:FAKE")
    order = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="888",
        title="AI Engineer / Python Developer",
        description="Очень длинное описание на 5000 символов...",
        url="https://hh.ru/vacancy/888",
        price=180000.0,
        attachments_text="Компания: Сбер AI\nЛокация: Москва",
    )
    analysis = AnalysisResult(
        take_order=True,
        priority=OrderPriority.HOT,
        score=9,
        is_relevant=True,
        matched_project="RAG-ассистент Cortex IT",
        match_reason="Идеальное совпадение по Python, FastAPI и LangChain",
        candidate_requirements="Опыт от 1 года, Python 3.10+, знание асинхронного программирования, Docker, Git, CI/CD",
        skills_gap="Требуется опыт с Kubernetes",
        skills_gap_counter="Опыт развертывания через Docker Compose и Linux systemd",
        executive_summary="Рекомендуется к отклику",
    )

    card = notifier.format_card(order, analysis)

    # 1. Основные реквизиты должны быть на месте
    assert "ВАКАНСИЯ | СКОР 9/10" in card
    assert "AI Engineer / Python Developer" in card
    assert "Сбер AI" in card
    assert "180 000 ₽" in card
    assert "HH_RU" in card
    assert "Идеальное совпадение" in card
    assert "Полное описание, стек и Cover Letter доступны на сайте" in card

    # 2. Длинные блоки не должны захламлять карточку в Telegram
    assert "Очень длинное описание" not in card
    assert "Опыт развертывания через Docker Compose" not in card

    # 3. Кнопки вакансии содержат переход на сайт
    kb = get_order_inline_keyboard(order_id=888, order_url=order.url, has_proposal=False, is_vacancy=True)
    all_btns = [b for row in kb.inline_keyboard for b in row]
    site_btn = next((b for b in all_btns if "Открыть на сайте" in b.text), None)
    assert site_btn is not None
    assert "jobs.3dvex.ru" in site_btn.url


@pytest.mark.asyncio
async def test_vacancy_settings_api_and_pipeline_salary_filter(tmp_path):
    """Проверка настроек города/формата/мин. зп через API и фильтрации вакансий ниже порога."""
    db_path = tmp_path / "test_vac_settings.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)

    app = create_web_app(repo=repo)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        auth=("Horizontal42", "qaz403111"),
    ) as client:
        # Сохранение настроек вакансий
        resp = await client.post(
            "/api/settings",
            json={
                "vacancy_city": "moscow",
                "vacancy_work_format": "remote",
                "vacancy_min_salary": 150000,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["settings"]["vacancy_city"] == "moscow"
        assert data["settings"]["vacancy_work_format"] == "remote"
        assert data["settings"]["vacancy_min_salary"] == 150000

    # Проверка работы фильтра в пайплайне
    from src.filters.pre_filter import HardFilter
    from src.notifiers.pipeline import LeadsPipeline

    pipeline = LeadsPipeline(
        repo=repo,
        hard_filter=HardFilter(),
        llm_client=None,
    )

    # 1. Вакансия с зарплатой 120 000 ₽ при пороге 150 000 ₽ должна быть отсеяна в трэш
    low_order = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="vac_low_1",
        title="Junior Python Dev",
        description="Разработка бэкенда",
        url="https://hh.ru/1",
        price=120000.0,
    )
    # 2. Вакансия с зарплатой 180 000 ₽ должна пройти
    high_order = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="vac_high_2",
        title="AI Engineer",
        description="Разработка LLM сервисов",
        url="https://hh.ru/2",
        price=180000.0,
    )

    stats = await pipeline.process_orders([low_order, high_order])
    assert stats["filtered_trash"] >= 1

    recent = await repo.get_recent_orders(limit=10)
    saved_low = next((o for o in recent if o["external_id"] == "vac_low_1"), None)
    assert saved_low is not None
    assert saved_low["priority"] == "trash"
    assert "ниже минимальной" in (saved_low.get("filter_reason") or "")

    # 3. Вакансия без зарплаты при vacancy_allow_negotiable=False должна отсеиваться
    await repo.set_setting("vacancy_allow_negotiable", False)
    no_salary_order = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="vac_no_sal_3",
        title="Python Dev",
        description="Разработка",
        url="https://hh.ru/3",
        price=None,
        is_negotiable=True,
    )
    stats3 = await pipeline.process_orders([no_salary_order])
    assert stats3["filtered_trash"] == 1
    saved_no_sal = next((o for o in (await repo.get_recent_orders(limit=10)) if o["external_id"] == "vac_no_sal_3"), None)
    assert saved_no_sal is not None
    assert saved_no_sal["priority"] == "trash"
    assert "не указана" in (saved_no_sal.get("filter_reason") or "").lower()


@pytest.mark.asyncio
async def test_hh_enricher_full_details(monkeypatch):
    from src.collectors.enricher import OrderEnricher

    class MockHhDetailResponse:
        status_code = 200

        def json(self):
            return {
                "id": "9999",
                "description": "<p>Полное подробное описание задач на Python и FastAPI</p>",
                "key_skills": [{"name": "Python"}, {"name": "Docker"}, {"name": "FastAPI"}],
                "schedule": {"name": "Удаленная работа"},
                "employment": {"name": "Полная занятость"},
            }

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            return MockHhDetailResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    order = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="9999",
        title="Python AI Dev",
        description="Краткий сниппет",
        url="https://hh.ru/vacancy/9999",
    )

    enricher = OrderEnricher()
    enriched = await enricher.enrich(order)

    assert "Полное подробное описание задач" in enriched.description
    assert "Python" in enriched.tags
    assert "FastAPI" in enriched.tags
    assert "Docker" in enriched.tags
    assert "🔑 Навыки: Python, Docker, FastAPI" in enriched.attachments_text
    assert "💼 Занятость: Полная занятость" in enriched.attachments_text


@pytest.mark.asyncio
async def test_hh_collector_remote_vacancies_not_filtered_by_city(monkeypatch):
    """Проверка того, что удаленные вакансии не блокируются фильтром города."""
    from unittest.mock import AsyncMock

    captured_params = []

    class MockHhClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, headers=None, params=None):
            captured_params.append(params.copy() if params else {})

            class MockResp:
                status_code = 200

                def json(self):
                    return {"items": []}

            return MockResp()

    monkeypatch.setattr(httpx, "AsyncClient", MockHhClient)

    mock_repo = AsyncMock()

    # 1. Формат "remote": не должно быть параметра area даже если выбран город moscow
    mock_repo.get_setting.side_effect = lambda k, def_val=None: {
        "vacancy_city": "moscow",
        "vacancy_work_format": "remote",
        "vacancy_min_salary": 80000,
        "vacancy_allow_negotiable": True,
    }.get(k, def_val)

    collector = HhRuCollector(token="test_tok", repo=mock_repo)
    await collector.fetch_new_orders()

    assert len(captured_params) > 0
    for p in captured_params:
        assert p.get("schedule") == "remote"
        assert "area" not in p  # Удаленка отовсюду

    # 2. Формат "all" + город "moscow": должны быть запросы и на schedule=remote (без area), и на area=[1]
    captured_params.clear()
    mock_repo.get_setting.side_effect = lambda k, def_val=None: {
        "vacancy_city": "moscow",
        "vacancy_work_format": "all",
        "vacancy_min_salary": 80000,
        "vacancy_allow_negotiable": True,
    }.get(k, def_val)

    collector = HhRuCollector(token="test_tok", repo=mock_repo)
    await collector.fetch_new_orders()

    schedules = [p.get("schedule") for p in captured_params]
    areas = [p.get("area") for p in captured_params]
    assert "remote" in schedules
    assert [1] in areas

