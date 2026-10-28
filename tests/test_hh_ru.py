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
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
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
