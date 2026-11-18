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
    assert "неоконченное высшее" in prompt
    assert "СПбГАСУ" not in prompt
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


def test_direction_specific_focus_injection():
    """Тест: инъекция специализированного фокуса анализа по 5 прикладным направлениям."""
    from src.analyzer.prompts import build_non_it_analysis_prompt

    # ЧПУ
    order_cnc = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="cnc-focus",
        title="Оператор ЧПУ",
        description="Работа на Fanuc",
        price=85000,
        url="https://avito.ru/1",
        tags=["non_it", "direction:cnc"],
    )
    prompt_cnc = build_non_it_analysis_prompt(order_cnc)
    assert "ЦЕЛЕВОЕ НАПРАВЛЕНИЕ: Оператор станков с ЧПУ" in prompt_cnc
    assert "Fanuc" in prompt_cnc

    # Модульный ремонт
    order_repair = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="rep-focus",
        title="Мастер по ремонту",
        description="Ремонт ноутбуков",
        price=80000,
        url="https://avito.ru/2",
        tags=["non_it", "direction:electronics_repair"],
    )
    prompt_repair = build_non_it_analysis_prompt(order_repair)
    assert "Мастер модульного ремонта электроники" in prompt_repair
    assert "замена экранов/матриц" in prompt_repair

    # Постаматы
    order_post = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="post-focus",
        title="Техник постаматов",
        description="ТО постаматов",
        price=75000,
        url="https://avito.ru/3",
        tags=["non_it", "direction:postamat_tech"],
    )
    prompt_post = build_non_it_analysis_prompt(order_post)
    assert "Сервисный техник постаматов и терминалов" in prompt_post

    # Trade-In
    order_trade = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="trade-focus",
        title="Специалист Trade-In",
        description="Входной контроль техники",
        price=75000,
        url="https://avito.ru/4",
        tags=["non_it", "direction:trade_in_testing"],
    )
    prompt_trade = build_non_it_analysis_prompt(order_trade)
    assert "Специалист входного контроля и Trade-In техники" in prompt_trade

    # Helpdesk
    order_hd = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="hd-focus",
        title="Helpdesk L1",
        description="Техподдержка офиса",
        price=70000,
        url="https://avito.ru/5",
        tags=["non_it", "direction:helpdesk_l1"],
    )
    prompt_hd = build_non_it_analysis_prompt(order_hd)
    assert "Младший специалист техподдержки (Helpdesk L1" in prompt_hd


def test_non_it_cover_letter_routing():
    """Тест: генерация отклика для не-IT вакансии переключается на прикладное сопроводительное письмо."""
    from src.analyzer.prompts import build_proposal_prompt, DEFAULT_NON_IT_COVER_LETTER_TEMPLATE

    # Проверка типографики шаблона
    assert "—" not in DEFAULT_NON_IT_COVER_LETTER_TEMPLATE
    assert "–" not in DEFAULT_NON_IT_COVER_LETTER_TEMPLATE

    # Не-IT вакансия с Авито
    order = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="nit-avito-letter",
        title="Оператор станка ЧПУ (Fanuc)",
        description="Требуется оператор на токарный станок Fanuc в Санкт-Петербурге.",
        price=90000,
        url="https://avito.ru/item/nit-avito-letter",
        tags=["non_it", "direction:cnc"],
    )
    prompt = build_proposal_prompt(order)
    assert "неоконченное высшее" in prompt
    assert "СПбГАСУ" not in prompt
    assert "чертежей" in prompt
    assert "штангенциркулем" in prompt
    # Гарантия, что IT-стек не затянулся
    assert "WhisperX" not in prompt
    assert "FastAPI" not in prompt
    assert "LangChain" not in prompt
    assert "Qdrant" not in prompt
    assert "—" not in prompt


def test_direction_profile_isolation():
    """Тест: строгая изоляция профилей кандидата между направлениями без смешивания."""
    from src.analyzer.prompts import build_proposal_prompt

    # 1. Заказ ЧПУ
    order_cnc = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="cnc-iso-1",
        title="Оператор фрезерного станка ЧПУ",
        description="Работа со стойкой Fanuc, фрезеровка деталей по чертежам.",
        price=85000,
        url="https://avito.ru/item/cnc-iso-1",
        tags=["non_it", "direction:cnc"],
    )
    prompt_cnc = build_proposal_prompt(order_cnc)
    assert "Fanuc" in prompt_cnc
    assert "AutoCut" in prompt_cnc
    assert "штангенциркулем" in prompt_cnc
    # Проверка изоляции: нет ноутбуков и AIDA64
    assert "Dell Precision" not in prompt_cnc
    assert "AIDA64" not in prompt_cnc
    assert "Gamer" not in prompt_cnc
    assert "—" not in prompt_cnc

    # 2. Заказ сервисного ремонта
    order_repair = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="rep-iso-1",
        title="Сервисный инженер по ремонту ноутбуков",
        description="Модульный ремонт, замена матриц, чистка систем охлаждения.",
        price=80000,
        url="https://avito.ru/item/rep-iso-1",
        tags=["non_it", "direction:electronics_repair"],
    )
    prompt_repair = build_proposal_prompt(order_repair)
    assert "Dell Precision" in prompt_repair
    assert "HP EliteBook" in prompt_repair
    assert "AIDA64" in prompt_repair
    assert "LaptopTester" in prompt_repair
    # Проверка изоляции: нет стоек Fanuc и чертежей ЕСКД
    assert "Fanuc" not in prompt_repair
    assert "AutoCut" not in prompt_repair
    assert "G54-G59" not in prompt_repair
    assert "—" not in prompt_repair

    # 3. Заказ Helpdesk
    order_hd = RawOrder(
        source=SourcePlatform.AVITO,
        external_id="hd-iso-1",
        title="Специалист технической поддержки пользователей L1",
        description="Обслуживание ПК, решение инцидентов, сети.",
        price=75000,
        url="https://avito.ru/item/hd-iso-1",
        tags=["non_it", "direction:helpdesk_l1"],
    )
    prompt_hd = build_proposal_prompt(order_hd)
    assert "Gamer" in prompt_hd
    assert "LANGAME" in prompt_hd
    assert "35" in prompt_hd
    assert "Fanuc" not in prompt_hd
    assert "—" not in prompt_hd


def test_non_it_anti_false_positives():
    """Тест: отсев непрофильных вакансий (стройматериалы, сантехника, пилорамы, служба заботы)."""
    flt = NonITHardFilter(min_salary=70000)

    # 1. Стройматериалы под видом Trade-In
    order_building = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="false-build",
        title="Ведущий специалист входного контроля строительных материалов",
        description="Входной контроль бетонных смесей, арматуры и кирпича на объекте.",
        price=85000,
        url="https://hh.ru/vacancy/false-build",
    )
    res_b = flt.evaluate(order_building)
    assert res_b.passed is False
    assert "строительн" in res_b.reason.lower() or "стройматериал" in res_b.reason.lower()

    # 2. Сантехника и эксплуатация зданий под видом Helpdesk
    order_bld_maint = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="false-maint",
        title="Специалист по эксплуатации и обслуживанию зданий",
        description="Обслуживание здания, сантехника, ремонт помещений, работа с оргтехникой офиса.",
        price=75000,
        url="https://hh.ru/vacancy/false-maint",
    )
    res_m = flt.evaluate(order_bld_maint)
    assert res_m.passed is False
    assert any(w in res_m.reason.lower() for w in ["эксплуатация зданий", "обслуживание зданий", "сантехник", "ремонт помещений"])

    # 3. Пилорама под видом ЧПУ
    order_saw = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="false-saw",
        title="Станочник д/о станков (распиловщик)",
        description="Станочник деревообрабатывающего оборудования, распиловка бруса.",
        price=80000,
        url="https://hh.ru/vacancy/false-saw",
    )
    res_s = flt.evaluate(order_saw)
    assert res_s.passed is False
    assert "д/о станк" in res_s.reason.lower() or "деревообраб" in res_s.reason.lower() or "распиловщик" in res_s.reason.lower()

    # 4. Служба заботы под видом Helpdesk
    order_care = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="false-care",
        title="Руководитель службы заботы о пользователях",
        description="Поддержка пользователей сервиса, мотивация сотрудников службы заботы, без железа.",
        price=90000,
        url="https://hh.ru/vacancy/false-care",
    )
    res_c = flt.evaluate(order_care)
    assert res_c.passed is False
    assert "забот" in res_c.reason.lower()


def test_non_it_cover_letter_contacts_and_formatting():
    """Тест: единые контакты и запрет скобок в шаблонах сопроводительных писем не-IT."""
    from src.analyzer.prompts import DEFAULT_NON_IT_COVER_LETTER_TEMPLATE, build_proposal_prompt
    from src.models.analysis import sanitize_proposal_text

    # Проверка контактов в шаблоне
    assert "+79097825505" in DEFAULT_NON_IT_COVER_LETTER_TEMPLATE
    assert "@Horizontal84" in DEFAULT_NON_IT_COVER_LETTER_TEMPLATE
    assert "pimenoffandrew@gmail.com" in DEFAULT_NON_IT_COVER_LETTER_TEMPLATE
    assert "@horizontal42" not in DEFAULT_NON_IT_COVER_LETTER_TEMPLATE
    assert "frolka84@gmail.com" not in DEFAULT_NON_IT_COVER_LETTER_TEMPLATE

    # Проверка нормализации контактов через санитизатор
    raw_text = "Контакты:\nТелефон: +7 (909) 7825505\nTelegram: @horizontal42\nEmail: frolka84@gmail.com"
    cleaned = sanitize_proposal_text(raw_text)
    assert "+79097825505" in cleaned
    assert "@Horizontal84" in cleaned
    assert "pimenoffandrew@gmail.com" in cleaned
    assert "+7 (909) 7825505" not in cleaned
    assert "@horizontal42" not in cleaned
    assert "frolka84@gmail.com" not in cleaned
