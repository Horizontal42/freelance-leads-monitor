"""End-to-end test for LeadsPipeline."""

import pytest
from src.analyzer.base import BaseLLMClient
from src.filters.pre_filter import HardFilter
from src.models.analysis import AnalysisResult, PertEstimate
from src.models.order import OrderPriority, OrderStatus, RawOrder, SourcePlatform
from src.notifiers.pipeline import LeadsPipeline
from src.storage.db import init_db
from src.storage.repository import OrderRepository


class MockLLMClient(BaseLLMClient):
    """Мок LLM для детерминированного тестирования пайплайна."""

    def __init__(self, score: int = 8, priority: OrderPriority = OrderPriority.HOT) -> None:
        self.score = score
        self.priority = priority

    async def analyze_order(self, order: RawOrder) -> AnalysisResult:
        return AnalysisResult(
            take_order=True,
            score=self.score,
            priority=self.priority,
            executive_summary="Хороший мэтч по парсингу",
            recommended_price=25000.0,
            price_justification="Вход по 25к",
            realistic_days=3.0,
            matched_project="Avia_Pars",
            complexity=5,
            pure_dev_hours=10.0,
            risks_and_pitfalls=["Лимиты запросов"],
            proposal_text="Добрый день. Делал парсер на python - реализуем.",
            pert=PertEstimate(
                optimistic_days=2.0,
                most_likely_days=3.0,
                pessimistic_days=5.0,
                expected_days=3.17,
                sigma=0.5,
            ),
        )


@pytest.mark.asyncio
async def test_pipeline_routing_flow(tmp_path):
    db_path = tmp_path / "test_pipeline.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)
    hard_filter = HardFilter(min_budget=10000)
    llm_client = MockLLMClient(score=9, priority=OrderPriority.HOT)

    pipeline = LeadsPipeline(
        repo=repo,
        hard_filter=hard_filter,
        llm_client=llm_client,
        tg_notifier=None,  # skip tg sending in unit test
    )

    orders = [
        # 1. Трэш (стоп-слово: диплом)
        RawOrder(
            source=SourcePlatform.KWORK,
            external_id="101",
            title="Дипломная работа по Python",
            description="Сделать диплом",
            url="https://kwork.ru/projects/101",
            price=15000,
        ),
        # 2. Трэш (бюджет < 10к)
        RawOrder(
            source=SourcePlatform.KWORK,
            external_id="102",
            title="Бот для Telegram на python",
            description="Простой бот",
            url="https://kwork.ru/projects/102",
            price=3000,
            is_negotiable=False,
        ),
        # 3. Горячий заказ (пройдет фильтр и получит score 9)
        RawOrder(
            source=SourcePlatform.FL_RU,
            external_id="103",
            title="Python-разработчик (Обход Cloudflare / WAF)",
            description="Стек: python, curl_cffi, прокси для автоматизации",
            url="https://www.fl.ru/projects/103",
            price=35000,
        ),
    ]

    stats = await pipeline.process_orders(orders)
    assert stats["received"] == 3
    assert stats["filtered_trash"] == 2
    assert stats["duplicates"] == 0

    # Проверяем записи в базе данных
    db_orders = await repo.get_recent_orders(limit=10)
    assert len(db_orders) == 3

    trash_orders = [o for o in db_orders if o["priority"] == "trash"]
    assert len(trash_orders) == 2
    for to in trash_orders:
        assert to["status"] == "rejected"
        assert to["filter_reason"] is not None

    hot_orders = [o for o in db_orders if o["priority"] == "hot"]
    assert len(hot_orders) == 1
    assert hot_orders[0]["external_id"] == "103"
    assert hot_orders[0]["score"] == 9
    assert hot_orders[0]["matched_project"] == "Avia_Pars"
    assert "дефис" in hot_orders[0]["proposal_text"] or "-" in hot_orders[0]["proposal_text"]

    # Проверяем повторный прогон на дубликаты
    stats2 = await pipeline.process_orders(orders)
    assert stats2["duplicates"] == 3
