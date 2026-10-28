"""Tests for FastAPI web dashboard."""

import pytest
import httpx
from src.models.order import OrderPriority, OrderStatus, RawOrder, SourcePlatform
from src.storage.db import init_db
from src.storage.repository import OrderRepository
from src.web.app import create_web_app


@pytest.mark.asyncio
async def test_web_dashboard_endpoints(tmp_path):
    db_path = tmp_path / "test_web.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)

    # Добавляем тестовый заказ
    order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="888",
        title="Разработка Telegram бота с кнопками",
        description="Нужен бот на aiogram",
        url="https://kwork.ru/projects/888",
        price=30000,
    )
    await repo.insert_raw_order(
        order=order,
        status=OrderStatus.ANALYZED,
        priority=OrderPriority.HOT,
    )

    app = create_web_app(repo=repo)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Health check
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # 2. Stats API
        resp = await client.get("/api/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["hot"] == 1

        # 3. Orders API
        resp = await client.get("/api/orders?priority=hot")
        assert resp.status_code == 200
        orders_data = resp.json()["orders"]
        assert len(orders_data) == 1
        assert orders_data[0]["external_id"] == "888"

        # 4. HTML Dashboard
        resp = await client.get("/")
        assert resp.status_code == 200
        html = resp.text
        assert "Freelance Leads Monitor" in html
        assert "jobs.3dvex.ru" in html
        assert "Разработка Telegram бота" in html
