"""Tests for Non-IT HH.ru Collector."""

import pytest
import httpx
from src.collectors.hh_ru import NonITHhRuCollector
from src.models.order import SourcePlatform


@pytest.mark.asyncio
async def test_non_it_hh_collector_fetch(monkeypatch):
    """Тест: NonITHhRuCollector запрашивает вакансии в СПб с зарплатой от 70k и ставит non_it теги."""
    sample_items = [
        {
            "id": "2001",
            "name": "Оператор станков с ЧПУ (токарная группа)",
            "employer": {"name": "ООО СпецМаш"},
            "area": {"name": "Санкт-Петербург"},
            "schedule": {"name": "Сменный график"},
            "experience": {"name": "От 1 года до 3 лет"},
            "salary": {"from": 85000, "to": 110000, "currency": "RUR"},
            "alternate_url": "https://hh.ru/vacancy/2001?from=share",
            "snippet": {
                "requirement": "Опыт работы на стойках Fanuc, чтение чертежей.",
                "responsibility": "Изготовление деталей, контроль размеров.",
            },
        }
    ]

    captured_params = []

    class MockAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, headers=None, params=None):
            captured_params.append(params)

            class MockResponse:
                status_code = 200

                def json(self):
                    return {"items": sample_items}

            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockAsyncClient)

    collector = NonITHhRuCollector(token="test_token", area=2, min_salary=70000)
    orders = await collector.fetch_new_orders()

    assert len(orders) == 1
    ord1 = orders[0]
    assert ord1.source == SourcePlatform.HH_RU
    assert ord1.external_id == "2001"
    assert ord1.title == "Оператор станков с ЧПУ (токарная группа)"
    assert ord1.price == 110000.0
    assert "non_it" in ord1.tags
    assert "прикладное" in ord1.tags
    assert "hh_ru" in ord1.tags
    assert "Санкт-Петербург" in ord1.tags
    assert "ООО СпецМаш" in ord1.attachments_text
    assert ord1.url == "https://hh.ru/vacancy/2001"

    # Проверяем, что параметры запроса к HH API содержат area=2 и salary=70000
    assert len(captured_params) > 0
    for p in captured_params:
        assert p["area"] == 2
        assert p["salary"] == 70000
