"""Unit tests for MarketAnalyticsService, daily trends and skill taxonomy."""

from datetime import datetime
import pytest
from src.models.order import OrderPriority, OrderStatus, RawOrder, SourcePlatform
from src.services.market_analytics import TECH_SKILLS_TAXONOMY, MarketAnalyticsService
from src.storage.db import init_db
from src.storage.repository import OrderRepository


@pytest.mark.asyncio
async def test_market_snapshot_repository_crud(tmp_path):
    db_file = tmp_path / "test_market_crud.db"
    await init_db(db_file)
    repo = OrderRepository(db_path=db_file)

    snapshot_data = {
        "date": "2026-11-07",
        "source_type": "vacancy",
        "scope": "all_it",
        "total_count": 42,
        "responded_count": 5,
        "skipped_count": 2,
        "hot_count": 8,
        "avg_price": 180000.0,
        "median_price": 175000.0,
        "min_price": 90000.0,
        "max_price": 320000.0,
        "top_skills": {"Python": 25, "FastAPI": 15, "Docker / K8s": 18},
        "sources_breakdown": {"hh_ru": 30, "habr_career": 12},
        "ai_summary": "Спрос на Python и AI-агентов стабильно растет.",
    }

    # 1. Сохранение
    snap_id = await repo.save_market_snapshot(snapshot_data)
    assert snap_id > 0

    # 2. Получение по фильтрам
    snaps = await repo.get_market_snapshots(source_type="vacancy", scope="all_it")
    assert len(snaps) == 1
    s = snaps[0]
    assert s["date"] == "2026-11-07"
    assert s["total_count"] == 42
    assert s["top_skills"]["Python"] == 25
    assert s["sources_breakdown"]["hh_ru"] == 30
    assert s["ai_summary"] == "Спрос на Python и AI-агентов стабильно растет."

    # 3. Обновление (ON CONFLICT DO UPDATE)
    snapshot_data["total_count"] = 45
    await repo.save_market_snapshot(snapshot_data)
    snaps_updated = await repo.get_market_snapshots(source_type="vacancy", scope="all_it")
    assert len(snaps_updated) == 1
    assert snaps_updated[0]["total_count"] == 45

    # 4. Обновление AI-сводки
    await repo.save_market_ai_summary(
        date="2026-11-07",
        source_type="vacancy",
        scope="all_it",
        ai_summary="Обновленная выжимка трендов.",
    )
    latest = await repo.get_latest_market_snapshot("vacancy", "all_it")
    assert latest is not None
    assert latest["ai_summary"] == "Обновленная выжимка трендов."


@pytest.mark.asyncio
async def test_calculate_daily_snapshot_separation(tmp_path, monkeypatch):
    db_file = tmp_path / "test_market_separation.db"
    await init_db(db_file)
    repo = OrderRepository(db_path=db_file)

    # Вставляем разнородные заказы за 2026-11-07
    now = datetime(2026, 11, 7, 12, 0, 0)

    # 1. Фриланс-заказ (Kwork) - профильный Python + Telegram
    order_freelance = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="kw_101",
        title="Разработка Telegram-бота на Python и aiogram",
        description="Интеграция с Bitrix24 и базой PostgreSQL",
        url="https://kwork.ru/101",
        price=35000,
        created_at=now,
    )
    await repo.insert_raw_order(order_freelance, status=OrderStatus.ANALYZED, priority=OrderPriority.HOT)

    # 2. Фриланс-заказ (FL.ru) - нецелевой треш (дизайн/верстка)
    order_trash = RawOrder(
        source=SourcePlatform.FL_RU,
        external_id="fl_102",
        title="Дизайн логотипа и полиграфии",
        description="Отрисовать макеты в Figma",
        url="https://fl.ru/102",
        price=15000,
        created_at=now,
    )
    await repo.insert_raw_order(order_trash, status=OrderStatus.REJECTED, priority=OrderPriority.TRASH)

    # 3. Вакансия (HeadHunter) - общее IT (Java / Spring)
    vacancy_java = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="hh_201",
        title="Java Backend Developer (Spring Boot)",
        description="Разработка микросервисов, Docker, PostgreSQL, REST API",
        url="https://hh.ru/vacancy/201",
        price=220000,
        created_at=now,
    )
    await repo.insert_raw_order(vacancy_java, status=OrderStatus.ANALYZED, priority=OrderPriority.NORMAL)

    # 4. Вакансия (Хабр Карьера) - AI / LLM
    vacancy_ai = RawOrder(
        source=SourcePlatform.HABR_CAREER,
        external_id="habr_202",
        title="AI Engineer / RAG Specialist",
        description="Python, LangChain, Qdrant векторная база, OpenAI API",
        url="https://career.habr.com/202",
        price=260000,
        created_at=now,
    )
    await repo.insert_raw_order(vacancy_ai, status=OrderStatus.ANALYZED, priority=OrderPriority.HOT)

    service = MarketAnalyticsService(repo=repo)

    # А. Расчет снимка по Вакансиям (все IT)
    snap_vac_all = await service.calculate_daily_snapshot(
        target_date="2026-11-07", source_type="vacancy", scope="all_it"
    )
    assert snap_vac_all["total_count"] == 2
    assert snap_vac_all["avg_price"] == 240000.0  # (220k + 260k) / 2
    assert "Java" in snap_vac_all["top_skills"]
    assert "Python" in snap_vac_all["top_skills"]
    assert "LLM / Agents / GPT" in snap_vac_all["top_skills"] or "RAG / Vector DB" in snap_vac_all["top_skills"]

    # Б. Расчет снимка по Фриланс-заказам (только специализация)
    snap_ord_spec = await service.calculate_daily_snapshot(
        target_date="2026-11-07", source_type="order", scope="specialized"
    )
    assert snap_ord_spec["total_count"] == 1  # Только Kwork, FL.ru отсеян так как priority=trash
    assert snap_ord_spec["avg_price"] == 35000.0
    assert "Telegram Bot" in snap_ord_spec["top_skills"]
    assert "Python" in snap_ord_spec["top_skills"]

    # В. Расчет снимка по Фриланс-заказам (все IT, включая трэш)
    snap_ord_all = await service.calculate_daily_snapshot(
        target_date="2026-11-07", source_type="order", scope="all_it"
    )
    assert snap_ord_all["total_count"] == 2  # Kwork + FL.ru

    # Г. Проверяем получение агрегированных трендов за период
    trends = await service.get_trends_data(source_type="vacancy", scope="all_it", days=7)
    assert trends["days_count"] >= 1
    assert len(trends["aggregated_skills"]) > 0
    top_skill_names = [s["name"] for s in trends["aggregated_skills"]]
    assert "Python" in top_skill_names or "PostgreSQL / SQL" in top_skill_names

    # Д. Проверяем расчет рейтинга по зарплатам (где средний чек выше)
    assert "top_paying_skills" in trends
    assert len(trends["top_paying_skills"]) > 0
    # Проверяем, что навыки отсортированы по убыванию avg_price
    prices = [s["avg_price"] for s in trends["top_paying_skills"]]
    assert prices == sorted(prices, reverse=True)

    # Е. Проверяем сравнение площадок по среднему чеку
    assert "sources_ranking" in trends
    assert len(trends["sources_ranking"]) > 0
    sources_in_ranking = [s["source"] for s in trends["sources_ranking"]]
    assert "hh_ru" in sources_in_ranking or "habr_career" in sources_in_ranking


@pytest.mark.asyncio
async def test_generate_ai_market_summary_mock(tmp_path, monkeypatch):
    db_file = tmp_path / "test_market_ai.db"
    await init_db(db_file)
    repo = OrderRepository(db_path=db_file)

    now = datetime(2026, 11, 7, 10, 0, 0)
    order = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="hh_301",
        title="Middle Python AI-разработчик",
        description="LLM, FastAPI, Docker",
        url="https://hh.ru/301",
        price=180000,
        created_at=now,
    )
    await repo.insert_raw_order(order, status=OrderStatus.ANALYZED, priority=OrderPriority.HOT)

    service = MarketAnalyticsService(repo=repo)
    await service.calculate_daily_snapshot("2026-11-07", source_type="vacancy", scope="all_it")

    # Мок LLM-клиента
    class DummyMistral:
        api_key = "dummy"
        model = "ministral-14b-latest"
        api_url = "https://api.mistral.ai/v1/chat/completions"
        timeout_seconds = 10.0
        semaphore = None
        rate_limiter = None

    class DummyClient:
        mistral = DummyMistral()

    # Мокаем вызов метода генерации текста
    async def mock_call_mistral_text(m_client, prompt):
        assert "ноябрь 2026" in prompt
        return "1. Спрос на Python и AI-агентов вырос на 30%.\n2. Средняя вилка держится около 180 000 руб.\n3. Рекомендуется фокусироваться на RAG и FastAPI."

    monkeypatch.setattr(service, "_call_mistral_text", mock_call_mistral_text)

    summary = await service.generate_ai_market_summary(
        llm_client=DummyClient(),
        source_type="vacancy",
        scope="all_it",
        days=7,
    )

    assert "Спрос на Python и AI-агентов" in summary
    # Проверяем, что сохранилось в БД
    latest = await repo.get_latest_market_snapshot("vacancy", "all_it")
    assert latest is not None
    assert latest["ai_summary"] == summary
