"""Tests for Non-IT Applied Vacancy funnel, direction filters, prompts, and storage."""

import pytest
from src.analyzer.prompts import build_analysis_prompt, build_non_it_analysis_prompt, DEFAULT_NON_IT_SYSTEM_PROMPT
from src.filters.non_it_filter import NonITHardFilter, NonITDirection
from src.models.order import RawOrder, SourcePlatform
from src.storage.repository import OrderRepository


def test_no_em_dashes_in_non_it_prompt():
    """Проверка жесткого правила типографики: никаких длинных тире (em-dash) в промпте."""
    assert "—" not in DEFAULT_NON_IT_SYSTEM_PROMPT
    assert "–" not in DEFAULT_NON_IT_SYSTEM_PROMPT


def test_non_it_cnc_filter_passes():
    """Тест: оператор станков с ЧПУ проходит фильтр с корректными тегами."""
    flt = NonITHardFilter(min_salary=70000)
    order = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="cnc-101",
        title="Оператор станков с ЧПУ (Fanuc)",
        description="Требуется оператор фрезерного станка ЧПУ со стойкой Fanuc. Изготовление деталей по чертежам, контроль размеров штангенциркулем.",
        price=85000,
        url="https://avito.ru/item/cnc-101",
    )
    res = flt.evaluate(order)
    assert res.passed is True
    assert "non_it" in order.tags
    assert "direction:cnc" in order.tags
    assert order.is_non_it is True


def test_non_it_salary_below_70k_rejected():
    """Тест: зарплата ниже 70 000 руб отсекается."""
    flt = NonITHardFilter(min_salary=70000)
    order = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="cnc-102",
        title="Оператор станка ЧПУ",
        description="Работа на токарном станке ЧПУ, сменный график.",
        price=65000,
        url="https://avito.ru/item/cnc-102",
    )
    res = flt.evaluate(order)
    assert res.passed is False
    assert "ниже минимального порога" in res.reason


def test_non_it_modular_repair_anti_scam():
    """Тест: выездной развод с процентом от чека отсекается как скам."""
    flt = NonITHardFilter(min_salary=70000)
    order = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="rep-scam",
        title="Мастер по ремонту ноутбуков и компьютеров",
        description="Выездной мастер к клиентам на дом, согласование стоимости ремонта на месте, высокий процент от чека, сдача денег в кассу.",
        price=150000,
        url="https://avito.ru/item/rep-scam",
    )
    res = flt.evaluate(order)
    assert res.passed is False
    assert "скам" in res.reason.lower() or "сомнительн" in res.reason.lower()


def test_non_it_modular_repair_genuine_passes():
    """Тест: честный модульный ремонт в сервисе проходит фильтр."""
    flt = NonITHardFilter(min_salary=70000)
    order = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="rep-ok",
        title="Сервисный специалист по модульному ремонту ноутбуков",
        description="В сервисный центр требуется помощник мастера: блочный ремонт ноутбуков, замена матриц, замена дисплея, чистка и замена термопасты. Без пайки BGA.",
        price=80000,
        url="https://avito.ru/item/rep-ok",
    )
    res = flt.evaluate(order)
    assert res.passed is True
    assert "direction:electronics_repair" in order.tags


def test_non_it_postamat_passes():
    """Тест: сервисный техник постаматов 5Post/СДЭК проходит фильтр."""
    flt = NonITHardFilter(min_salary=70000)
    order = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="post-ok",
        title="Сервисный техник постаматов",
        description="Техническое обслуживание постаматов 5Post и терминалов: замена замков ячеек, проверка модемов и плат управления.",
        price=75000,
        url="https://avito.ru/item/post-ok",
    )
    res = flt.evaluate(order)
    assert res.passed is True
    assert "direction:postamat_tech" in order.tags


def test_non_it_trade_in_passes():
    """Тест: специалист входного контроля и Trade-In проходит фильтр."""
    flt = NonITHardFilter(min_salary=70000)
    order = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="tradein-ok",
        title="Контролер качества / специалист Trade-In техники",
        description="Входной контроль и тестирование электроники: проверка техники, дефектовка смартфонов и ноутбуков на складе уценки.",
        price=75000,
        url="https://avito.ru/item/tradein-ok",
    )
    res = flt.evaluate(order)
    assert res.passed is True
    assert "direction:trade_in_testing" in order.tags


def test_non_it_helpdesk_passes():
    """Тест: младший специалист техподдержки L1 проходит фильтр."""
    flt = NonITHardFilter(min_salary=70000)
    order = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="helpdesk-ok",
        title="Младший специалист техподдержки (Helpdesk 1 линия)",
        description="Подготовка рабочих мест, обжимка витой пары, установка Windows 10/11, замена комплектующих и картриджей оргтехники.",
        price=70000,
        url="https://avito.ru/item/helpdesk-ok",
    )
    res = flt.evaluate(order)
    assert res.passed is True
    assert "direction:helpdesk_l1" in order.tags


def test_prompt_routing_for_non_it():
    """Тест: order.is_non_it автоматически переключает промпт анализа на non-it."""
    order = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="cnc-prompt-check",
        title="Оператор ЧПУ токарной группы",
        description="Работа на токарных станках со стойками ЧПУ Fanuc.",
        price=80000,
        url="https://avito.ru/item/cnc-prompt-check",
        tags=["non_it", "direction:cnc"],
    )
    prompt = build_analysis_prompt(order)
    assert "ПРОАНАЛИЗИРУЙ ПРИКЛАДНУЮ (НЕ-IT) ВАКАНСИЮ" in prompt
    assert "СПбГАСУ" in prompt
    assert "—" not in prompt


@pytest.mark.asyncio
async def test_repository_non_it_isolation(tmp_path):
    """Тест: изоляция прикладных вакансий от фриланса и IT-вакансий в БД."""
    from src.storage.db import init_db
    db_file = tmp_path / "test_non_it.db"
    await init_db(str(db_file))
    repo = OrderRepository(db_path=str(db_file))

    # 1. Заказ фриланса
    freelance_order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="fr-1",
        title="Скрипт Python для парсинга",
        description="Нужен парсер",
        url="https://kwork.ru/1",
        price=15000,
    )
    await repo.insert_raw_order(freelance_order)

    # 2. IT-вакансия
    it_vacancy = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="it-1",
        title="Python Backend Developer",
        description="FastAPI, PostgreSQL",
        url="https://hh.ru/vacancy/1",
        price=120000,
    )
    await repo.insert_raw_order(it_vacancy)

    # 3. Прикладная вакансия Не-IT
    non_it_job = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="nit-1",
        title="Оператор станков ЧПУ",
        description="Фрезерный станок Fanuc",
        url="https://avito.ru/item/nit-1",
        price=85000,
        tags=["non_it", "direction:cnc"],
    )
    await repo.insert_raw_order(non_it_job)

    # Проверяем get_recent_orders
    non_it_list = await repo.get_recent_orders(section="non_it")
    assert len(non_it_list) == 1
    assert non_it_list[0]["external_id"] == "nit-1"

    freelance_list = await repo.get_recent_orders(section="freelance")
    assert len(freelance_list) == 1
    assert freelance_list[0]["external_id"] == "fr-1"

    it_list = await repo.get_recent_orders(section="hh_ru")
    assert len(it_list) == 1
    assert it_list[0]["external_id"] == "it-1"

    # Проверяем фильтрацию по direction
    cnc_list = await repo.get_recent_orders(section="non_it", direction="cnc")
    assert len(cnc_list) == 1

    repair_list = await repo.get_recent_orders(section="non_it", direction="electronics_repair")
    assert len(repair_list) == 0

    # Проверяем extended_stats
    stats = await repo.get_extended_stats()
    assert stats["non_it"]["total"] == 1
    assert stats["freelance"]["total"] == 1
    assert stats["hh_ru"]["total"] == 1
