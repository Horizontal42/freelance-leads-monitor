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
        title="Разработка сервиса на Python с открытым бюджетом",
        description="Нужен сервис выгрузки каталога цен, интеграция в Битрикс24",
        url="https://example.com/3",
        price=None,
        is_negotiable=True,
    )
    result = filter_.evaluate(order)
    assert result.passed is True
    assert "python" in result.matched_keywords or "битрикс24" in result.matched_keywords


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


def test_hard_filter_expanded_b2b_and_ai_keywords():
    """Тест фильтрации заказов из новых сфер: amoCRM, МойСклад, RAG, Whisper, эквайринг."""
    filter_ = HardFilter(min_budget=10000)

    # 1. B2B / CRM / Платежи
    order_b2b = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="10",
        title="Синхронизация МойСклад и amoCRM, подключение ЮKassa",
        description="Нужно настроить вебхуки и обмен заказами",
        url="https://kwork.ru/10",
        price=45000,
    )
    res_b2b = filter_.evaluate(order_b2b)
    assert res_b2b.passed is True
    assert "amocrm" in res_b2b.matched_keywords or "мойсклад" in res_b2b.matched_keywords
    assert "юкасса" in res_b2b.matched_keywords or "вебхук" in res_b2b.matched_keywords

    # 2. AI / RAG / Речевая аналитика
    order_ai = RawOrder(
        source=SourcePlatform.FL_RU,
        external_id="11",
        title="AI-ассистент с базой знаний (RAG) и транскрибация звонков",
        description="Развернуть Qdrant, подключить Whisper и DeepSeek для отдела продаж",
        url="https://fl.ru/11",
        price=60000,
    )
    res_ai = filter_.evaluate(order_ai)
    assert res_ai.passed is True
    assert "rag" in res_ai.matched_keywords or "ассистент" in res_ai.matched_keywords
    assert "qdrant" in res_ai.matched_keywords or "whisper" in res_ai.matched_keywords


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

    # 5. Update proposal with market price from agy
    await repo.update_proposal(
        order_id,
        proposal_text="Отклик от agy",
        recommended_price=35000.0,
        price_justification="Анализ цен на биржах",
    )
    updated = await repo.get_by_id(order_id)
    assert updated["proposal_text"] == "Отклик от agy"
    assert updated["recommended_price"] == 35000.0
