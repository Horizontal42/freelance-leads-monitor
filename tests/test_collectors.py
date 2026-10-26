"""Tests for Kwork and FL.ru collectors."""

import pytest
from src.collectors.fl_ru import FlRuCollector
from src.collectors.kwork import KworkCollector
from src.models.order import SourcePlatform


def test_kwork_state_extraction():
    collector = KworkCollector()
    mock_html = """
    <html>
    <head><title>Test</title></head>
    <body>
    <script>
    window.stateData = {"wantsListData": {"wants": [{"id": 12345, "name": "Бот для Telegram", "priceLimit": 15000, "description": "Сделать бота", "category_id": 41}]}};
    </script>
    </body>
    </html>
    """
    data = collector._extract_state_data(mock_html)
    assert data is not None
    assert "wantsListData" in data
    wants = data["wantsListData"]["wants"]
    assert len(wants) == 1
    order = collector._parse_order(wants[0])
    assert order is not None
    assert order.external_id == "12345"
    assert order.title == "Бот для Telegram"
    assert order.price == 15000.0
    assert order.source == SourcePlatform.KWORK


def test_fl_ru_price_and_id_extraction():
    collector = FlRuCollector()
    link = "https://www.fl.ru/projects/5526844/python-razrabotchik.html"
    ext_id = collector._extract_external_id(link)
    assert ext_id == "5526844"

    price, negotiable = collector._extract_price("Сделать парсер. Бюджет: 35 000 руб.")
    assert price == 35000.0
    assert negotiable is False

    price2, negotiable2 = collector._extract_price("Сделать бота. Цена по договоренности")
    assert price2 is None
    assert negotiable2 is True


@pytest.mark.asyncio
async def test_live_fl_ru_rss():
    """Live smoke test to verify FL.ru RSS is reachable and parses."""
    collector = FlRuCollector()
    orders = await collector.fetch_new_orders()
    assert isinstance(orders, list)
    # FL.ru RSS is active and returns orders
    assert len(orders) > 0
    assert orders[0].source == SourcePlatform.FL_RU
