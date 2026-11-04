"""Unit tests for OrderImporterService."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.models.analysis import AnalysisResult
from src.models.order import OrderPriority, OrderStatus, RawOrder, SourcePlatform
from src.services.order_importer import OrderImporterService
from src.storage.db import init_db
from src.storage.repository import OrderRepository


def test_detect_platform_and_id():
    service = OrderImporterService()

    plat, ext = service.detect_platform_and_id("https://hh.ru/vacancy/138921986?query=python")
    assert plat == SourcePlatform.HH_RU
    assert ext == "138921986"

    plat, ext = service.detect_platform_and_id("https://career.habr.com/vacancies/1000123456")
    assert plat == SourcePlatform.HABR_CAREER
    assert ext == "1000123456"

    plat, ext = service.detect_platform_and_id("https://kwork.ru/projects/3271034")
    assert plat == SourcePlatform.KWORK
    assert ext == "3271034"

    plat, ext = service.detect_platform_and_id("https://www.fl.ru/projects/54321/")
    assert plat == SourcePlatform.FL_RU
    assert ext == "54321"

    plat, ext = service.detect_platform_and_id("https://freelance.ru/projects/999888.html")
    assert plat == SourcePlatform.FREELANCE_RU
    assert ext == "999888"

    plat, ext = service.detect_platform_and_id("https://pchel.net/jobs/112233.html")
    assert plat == SourcePlatform.PCHEL_NET
    assert ext == "112233"


@pytest.mark.asyncio
async def test_import_or_lookup_existing(tmp_path):
    db_path = tmp_path / "test_import.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)

    raw = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="138921986",
        title="ML-инженер",
        description="Разработка AI-агентов",
        url="https://hh.ru/vacancy/138921986",
    )
    oid = await repo.insert_raw_order(raw, status=OrderStatus.ANALYZED, priority=OrderPriority.HOT)

    service = OrderImporterService()
    res = await service.import_or_lookup("https://hh.ru/vacancy/138921986", repo, None)
    assert res["ok"] is True
    assert res["status"] == "found"
    assert res["order"]["id"] == oid


@pytest.mark.asyncio
async def test_import_or_lookup_new_order(tmp_path):
    db_path = tmp_path / "test_import_new.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)

    service = OrderImporterService()
    mock_raw = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="777777",
        title="Парсер Авито",
        description="Нужен парсер",
        url="https://kwork.ru/projects/777777",
        price=25000,
    )
    service.fetch_raw_order = AsyncMock(return_value=mock_raw)
    service.enricher.enrich = AsyncMock(return_value=mock_raw)

    mock_llm = MagicMock()
    mock_analysis = AnalysisResult(
        take_order=True,
        priority=OrderPriority.HOT,
        score=9,
        is_relevant=True,
        realistic_days=2.0,
        recommended_price=25000,
        market_price=30000,
        executive_summary="Разработка парсера Авито",
    )
    mock_llm.analyze_order = AsyncMock(return_value=mock_analysis)

    res = await service.import_or_lookup("https://kwork.ru/projects/777777", repo, mock_llm)
    assert res["ok"] is True
    assert res["status"] == "created"
    assert res["order"]["external_id"] == "777777"
    assert res["order"]["score"] == 9
