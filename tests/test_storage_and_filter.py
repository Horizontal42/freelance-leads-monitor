"""Tests for storage layer and hard filter."""

from datetime import datetime
import pytest
from src.filters.pre_filter import HardFilter
from src.models.order import OrderPriority, OrderStatus, RawOrder, SourcePlatform
from src.storage.db import init_db
from src.storage.repository import OrderRepository


def test_hard_filter_stop_words():
    filter_ = HardFilter(min_budget=10000)
    order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="1",
        title="Сделать дипломную работу по Python",
        description="Нужно написать реферат и код для студента",
        url="https://example.com/1",
        price=15000,
    )
    result = filter_.evaluate(order)
    assert result.passed is False
    assert "диплом" in result.reason.lower() or "студент" in result.reason.lower()


def test_hard_filter_budget_too_low():
    filter_ = HardFilter(min_budget=10000)
    order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="2",
        title="Telegram бот на aiogram для пиццерии",
        description="Простой бот с кнопками",
        url="https://example.com/2",
        price=3000,
        is_negotiable=False,
    )
    result = filter_.evaluate(order)
    assert result.passed is False
    assert "ниже минимального порога" in result.reason


def test_hard_filter_negotiable_budget_passes():
    filter_ = HardFilter(min_budget=10000)
    order = RawOrder(
        source=SourcePlatform.FL_RU,
        external_id="3",
        title="Разработка парсера на Python с обходом защиты",
        description="Нужен парсер каталога цен, интеграция в Битрикс24",
        url="https://example.com/3",
        price=None,
        is_negotiable=True,
    )
    result = filter_.evaluate(order)
    assert result.passed is True
    assert "парсер" in result.matched_keywords or "python" in result.matched_keywords


def test_hard_filter_valid_order_passes():
    filter_ = HardFilter(min_budget=10000)
    order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="4",
        title="Создать чат-бота в телеграм для кафе",
        description="Стек: python, aiogram, интеграция с CRM по API",
        url="https://example.com/4",
        price=30000,
    )
    result = filter_.evaluate(order)
    assert result.passed is True
    assert len(result.matched_keywords) >= 2


@pytest.mark.asyncio
async def test_order_repository_flow(tmp_path):
    db_file = tmp_path / "test_jobs.db"
    await init_db(db_file)
    repo = OrderRepository(db_path=db_file)

    order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="1001",
        title="Парсер сайта цен",
        description="Парсер на Python",
        url="https://kwork.ru/projects/1001",
        price=25000,
    )

    # 1. Deduplication check
    assert await repo.is_duplicate(order.source.value, order.external_id) is False

    # 2. Insert order
    order_id = await repo.insert_raw_order(
        order,
        status=OrderStatus.NEW,
        priority=OrderPriority.HOT,
    )
    assert order_id > 0
    assert await repo.is_duplicate(order.source.value, order.external_id) is True

    # 3. Fetch recent
    orders = await repo.get_recent_orders(limit=10)
    assert len(orders) == 1
    assert orders[0]["external_id"] == "1001"
    assert orders[0]["price"] == 25000.0

    # 4. Stats
    stats = await repo.get_stats()
    assert stats["total"] == 1
    assert stats["hot"] == 1
