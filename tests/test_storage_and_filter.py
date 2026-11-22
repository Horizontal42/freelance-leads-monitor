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


def test_hard_filter_engineering_vs_visual_design():
    filter_ = HardFilter(min_budget=10000)
    # 1. Инженерный дизайн (System Design) должен успешно проходить
    tech_order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="tech_1",
        title="Python AI-разработчик микросервисов",
        description="Требуется понимание System Design, построение архитектуры и интеграция LLM через FastAPI",
        url="https://example.com/tech_1",
        price=50000,
    )
    res_tech = filter_.evaluate(tech_order)
    assert res_tech.passed is True

    # 2. Визуальный дизайн (UI/UX, баннеры, логотипы, полиграфия) должен отсекаться
    visual_order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="vis_1",
        title="UI/UX дизайнер для мобильного приложения",
        description="Разработка дизайн-макетов в Figma и дизайн карточек товаров",
        url="https://example.com/vis_1",
        price=40000,
    )
    res_vis = filter_.evaluate(visual_order)
    assert res_vis.passed is False
    assert any(term in res_vis.reason.lower() for term in ["дизайн", "дизайнер", "ui/ux", "figma"])


def test_hard_filter_budget_too_low():
    filter_ = HardFilter(min_budget=10000, allow_quick_orders=False)
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


def test_hard_filter_quick_orders():
    filter_ = HardFilter(min_budget=10000, allow_quick_orders=True, quick_min_budget=2000)

    # 1. Быстрый точечный скрипт (3 000 ₽) проходит как Quick Win
    quick_order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="q1",
        title="Написать скрипт парсинга на Python для сбора цен",
        description="Простой парсер с выгрузкой в CSV через pandas",
        url="https://example.com/q1",
        price=3000,
        is_negotiable=False,
    )
    res_quick = filter_.evaluate(quick_order)
    assert res_quick.passed is True
    assert "quick win" in res_quick.reason.lower()

    # 1.1 Парсер маркетплейса под ключ (5 000 ₽) также должен проходить как Quick Win
    wb_parser = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="q1_wb",
        title="Парсер Wildberries под ключ на Python",
        description="Нужен скрипт парсинга цен и остатков с выгрузкой в Excel",
        url="https://example.com/q1_wb",
        price=5000,
        is_negotiable=False,
    )
    res_wb = filter_.evaluate(wb_parser)
    assert res_wb.passed is True
    assert "quick win" in res_wb.reason.lower()

    # 2. Комплексный комбайн / продукт за 3 000 ₽ отсекается
    heavy_order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="q2",
        title="Разработка маркетплейса под ключ на Python",
        description="Нужен маркетплейс под ключ с личным кабинетом и платежкой",
        url="https://example.com/q2",
        price=3000,
        is_negotiable=False,
    )
    res_heavy = filter_.evaluate(heavy_order)
    assert res_heavy.passed is False
    assert "не является быстрым" in res_heavy.reason

    # 3. Заказ ниже quick_min_budget (1 000 ₽) отсекается
    cheap_order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="q3",
        title="Написать скрипт на Python",
        description="Простой скрипт",
        url="https://example.com/q3",
        price=1000,
        is_negotiable=False,
    )
    res_cheap = filter_.evaluate(cheap_order)
    assert res_cheap.passed is False
    assert "ниже минимального порога" in res_cheap.reason


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


@pytest.mark.asyncio
async def test_toggle_responded_and_skipped(tmp_path):
    """Проверка переключения откликов, скипов, временных меток и расширенной аналитики."""
    db_path = tmp_path / "test_resp_skip.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)
    order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="resp_skip_test",
        title="Тест отклика и скипа",
        description="Разработка Telegram-бота на Python и FastAPI",
        url="https://kwork.ru/test",
        price=15000.0,
    )
    order_id = await repo.insert_raw_order(order, priority=OrderPriority.HOT)

    # 1. Toggle responded
    is_resp = await repo.toggle_responded(order_id)
    assert is_resp is True
    o = await repo.get_by_id(order_id)
    assert o["is_responded"] == 1
    assert o["responded_at"] is not None

    # 2. Toggle skipped
    is_skip = await repo.toggle_skipped(order_id)
    assert is_skip is True
    o = await repo.get_by_id(order_id)
    assert o["is_skipped"] == 1
    assert o["skipped_at"] is not None

    # 3. get_recent_orders filtering
    # Default hides skipped
    recent_active = await repo.get_recent_orders(hide_skipped=True)
    assert len(recent_active) == 0

    # Only responded
    recent_resp = await repo.get_recent_orders(only_responded=True)
    assert len(recent_resp) == 1

    # Only skipped
    recent_skip = await repo.get_recent_orders(only_skipped=True)
    assert len(recent_skip) == 1

    # 4. Section analytics
    analytics = await repo.get_section_analytics("freelance")
    assert analytics["resp_total"] == 1
    assert analytics["resp_today"] == 1
    assert analytics["skipped_total"] == 1
    assert analytics["hot_total"] == 1
    assert analytics["hot_responded"] == 1
    assert analytics["hot_conversion"] == 100.0


def test_hard_filter_it_vacancy_rejection_rules():
    filter_ = HardFilter()

    # 1. Вакансия с чужим языком в названии (C#)
    csharp_vac = RawOrder(
        source=SourcePlatform.HABR_CAREER,
        external_id="1000169750",
        title="Автотестировщик (C#)",
        description="Разработка тестов с использованием Selenium, Playwright и C#.",
        url="https://career.habr.com/vacancies/1000169750",
    )
    res_csharp = filter_.evaluate(csharp_vac)
    assert res_csharp.passed is False
    assert "непрофильный основной стек" in res_csharp.reason.lower()

    # 2. Вакансия уровня Senior в названии
    senior_vac = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="998877",
        title="Senior Python Developer / Тимлид",
        description="Архитектура сервисов, управление командой разработки, Python, FastAPI.",
        url="https://hh.ru/vacancy/998877",
    )
    res_senior = filter_.evaluate(senior_vac)
    assert res_senior.passed is False
    assert "senior/lead" in res_senior.reason.lower()

    # 3. Вакансия со сеньорским тегом
    tag_vac = RawOrder(
        source=SourcePlatform.HABR_CAREER,
        external_id="998878",
        title="Python разработчик",
        description="Разработка сервисов на Python и Docker.",
        url="https://career.habr.com/vacancies/998878",
        tags=["Python", "Senior", "PostgreSQL"],
    )
    res_tag = filter_.evaluate(tag_vac)
    assert res_tag.passed is False
    assert "теги уровня senior/lead" in res_tag.reason.lower()

    # 4. Вакансия с завышенным опытом работы (от 5 лет)
    exp_vac = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="998879",
        title="Python разработчик",
        description="Требования: опыт коммерческой разработки на Python от 5 лет, глубокое знание распределенных систем.",
        url="https://hh.ru/vacancy/998879",
    )
    res_exp = filter_.evaluate(exp_vac)
    assert res_exp.passed is False
    assert "от 5+ лет" in res_exp.reason.lower()

    # 5. Целевая вакансия Junior+/Middle Python
    target_vac = RawOrder(
        source=SourcePlatform.HABR_CAREER,
        external_id="998880",
        title="Junior+ Python разработчик / AI Automation",
        description="Разработка микросервисов на FastAPI, Telegram-ботов и интеграция LLM/RAG пайплайнов. Опыт от 1 года.",
        url="https://career.habr.com/vacancies/998880",
        tags=["Python", "FastAPI", "Junior"],
    )
    res_target = filter_.evaluate(target_vac)
    assert res_target.passed is True
    assert "прошел фильтр" in res_target.reason.lower()

    # 6. Объявление исполнителя из раздела Авито 'Предложения услуг'
    avito_service_order = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="8436557292",
        title="ML-модели для бизнеса: прогноз, скоринг. Санкт-Петербург",
        description="Разработка ML-моделей на заказ",
        url="https://www.avito.ru/sankt-peterburg/predlozheniya_uslug/ml-modeli_8436557292",
    )
    res_avito_service = filter_.evaluate(avito_service_order)
    assert res_avito_service.passed is False
    assert "предложения услуг" in res_avito_service.reason.lower()
