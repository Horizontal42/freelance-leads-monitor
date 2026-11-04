"""Unit tests for DatabaseRecalculator."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.models.analysis import AnalysisResult
from src.models.order import OrderPriority, OrderStatus, RawOrder, SourcePlatform
from src.services.recalculator import DatabaseRecalculator
from src.storage.db import init_db
from src.storage.repository import OrderRepository


@pytest.mark.asyncio
async def test_recalculator_recovers_trash_order(tmp_path):
    db_path = tmp_path / "test_recalc.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)

    # Заказ со словом AI-first, который ранее был отсеян
    raw = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="138842424",
        title="AI-first Developer",
        description="Разработка AI-агентов на Python",
        url="https://spb.hh.ru/vacancy/138842424",
    )
    oid = await repo.insert_raw_order(
        order=raw,
        status=OrderStatus.REJECTED,
        priority=OrderPriority.TRASH,
        filter_reason="Нет совпадений с белым списком ключевых слов",
    )

    recalculator = DatabaseRecalculator(repo=repo)

    mock_llm = MagicMock()
    mock_analysis = AnalysisResult(
        take_order=True,
        priority=OrderPriority.HOT,
        score=9,
        is_relevant=True,
        realistic_days=2.0,
        recommended_price=200000,
        market_price=220000,
        executive_summary="AI-first разработка",
    )
    mock_llm.analyze_order = AsyncMock(return_value=mock_analysis)

    res = await recalculator.run(scope="trash", limit=10, analyze_llm=True, llm_client=mock_llm)
    assert res["ok"] is True
    assert res["total_processed"] == 1
    assert res["recovered"] == 1

    updated = await repo.get_by_id(oid)
    assert updated["priority"] == "hot"
    assert updated["status"] == "analyzed"
    assert updated["score"] == 9
