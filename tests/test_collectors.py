"""Tests for all collectors: Kwork, FL.ru, Freelance.ru, Pchel.net."""

import pytest
from src.collectors.fl_ru import FlRuCollector
from src.collectors.freelance_ru import FreelanceRuCollector
from src.collectors.kwork import KworkCollector
from src.collectors.pchel_net import PchelNetCollector
from src.collectors.remote_job import RemoteJobCollector
from src.models.order import SourcePlatform


def test_kwork_state_extraction():
    collector = KworkCollector()
    mock_html = """
    <html>
    <head><title>Test</title></head>
    <body>
    <script>
    window.stateData = {"wantsListData": {"wants": [{"id": 12345, "name": "Бот для Telegram", "priceLimit": 15000, "description": "Сделать бота", "category_id": 41}]}};
    </script>
    </body>
    </html>
    """
    data = collector._extract_state_data(mock_html)
    assert data is not None
    assert "wantsListData" in data
    wants = data["wantsListData"]["wants"]
    assert len(wants) == 1
    order = collector._parse_order(wants[0])
    assert order is not None
    assert order.external_id == "12345"
    assert order.title == "Бот для Telegram"
    assert order.price == 15000.0
    assert order.source == SourcePlatform.KWORK


def test_fl_ru_price_and_id_extraction():
    collector = FlRuCollector()
    link = "https://www.fl.ru/projects/5526844/python-razrabotchik.html"
    ext_id = collector._extract_external_id(link)
    assert ext_id == "5526844"

    price, negotiable = collector._extract_price("Сделать парсер. Бюджет: 35 000 руб.")
    assert price == 35000.0
    assert negotiable is False

    price2, negotiable2 = collector._extract_price("Сделать бота. Цена по договоренности")
    assert price2 is None
    assert negotiable2 is True


def test_freelance_ru_article_parsing():
    collector = FreelanceRuCollector()
    mock_article = """
    <article class="task-card">
        <a class="task-card__title-link" href="/task/view/9999" title="Парсинг сайта на Python">
            Парсинг сайта на Python
        </a>
        <p class="task-card__desc">Нужно написать скрипт на Python с использованием httpx.</p>
        <div class="task-card__side">
            <div class="task-card__budget">
                <span class="bold">25 000 &#8381;</span>
            </div>
        </div>
        <div class="task-card__chips">
            <span class="task-chip">Python</span>
            <span class="task-chip">Парсинг</span>
        </div>
        <span class="task-card__foot-item" title="26.10.2026 18:30"></span>
    </article>
    """
    order = collector._parse_article(mock_article)
    assert order is not None
    assert order.external_id == "9999"
    assert order.title == "Парсинг сайта на Python"
    assert order.price == 25000.0
    assert order.is_negotiable is False
    assert order.source == SourcePlatform.FREELANCE_RU
    assert "Python" in order.tags


def test_pchel_net_block_parsing():
    collector = PchelNetCollector(usd_rate=100.0)
    mock_block = """
    <div class="project-block-cont">
        <div class="price">$150</div>
        <div class="project-title">
            <a href="/jobs/programming/parser-avito-123456/" class="b-link">Парсер цен Авито</a>
        </div>
        <div class="project-text">
            <p>Написать парсер цен на Python и сохранить в базу.</p>
        </div>
    </div>
    """
    order = collector._parse_block(mock_block)
    assert order is not None
    assert order.external_id == "123456"
    assert order.title == "Парсер цен Авито"
    # $150 * 100.0 = 15000.0 RUB
    assert order.price == 15000.0
    assert order.is_negotiable is False
    assert order.source == SourcePlatform.PCHEL_NET


def test_remote_job_card_parsing_fixed_budget():
    collector = RemoteJobCollector()
    mock_card = """
    <div class="row">
        <div class="col-xs-10 col-sm-10 col-md-10 col-lg-10 text-left">
            <h2>
                <a target="_blank" href="/project_work/project_show/806478/ai-agenty-integrirovat-nejroset-claude-v-revit-2023-distanczionnaya-rabota">
                    AI-агенты. Интегрировать нейросеть Claude в revit 2023 (Дистанционная работа)
                </a>
            </h2>
            <h3>Бюджет: 35 000 руб.</h3>
        </div>
        <div class="col-xs-12 col-sm-12 col-md-12 col-lg-12 text-left">
            У меня установлен revit 23, нужно подключить Claude через MCP.
        </div>
    </div>
    """
    order = collector._parse_card(mock_card)
    assert order is not None
    assert order.external_id == "806478"
    assert order.title == "AI-агенты. Интегрировать нейросеть Claude в revit 2023"
    assert order.price == 35000.0
    assert order.is_negotiable is False
    assert order.source == SourcePlatform.REMOTE_JOB
    assert "revit 23" in order.description


def test_remote_job_card_parsing_negotiable_budget():
    collector = RemoteJobCollector()
    mock_card = """
    <div class="row">
        <div class="col-xs-10 col-sm-10 col-md-10 col-lg-10 text-left">
            <h2>
                <a target="_blank" href="/project_work/project_show/806483/sistemnyj-programmist-nuzhen-soft-distanczionnaya-rabota">
                    Системный программист. Нужен софт (Дистанционная работа)
                </a>
            </h2>
            <h3>Бюджет не указан</h3>
        </div>
        <div class="col-xs-12 col-sm-12 col-md-12 col-lg-12 text-left">
            Разработка ПО на Python/C++.
        </div>
    </div>
    """
    order = collector._parse_card(mock_card)
    assert order is not None
    assert order.external_id == "806483"
    assert order.title == "Системный программист. Нужен софт"
    assert order.price is None
    assert order.is_negotiable is True
    assert order.source == SourcePlatform.REMOTE_JOB


@pytest.mark.asyncio
async def test_order_enricher():
    from src.collectors.enricher import OrderEnricher
    from src.models.order import RawOrder

    enricher = OrderEnricher()

    # 1. Kwork enrichment with attached files in raw_payload
    kwork_order = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="12345",
        title="Скрипт с файлом ТЗ",
        description="Краткое описание",
        url="https://kwork.ru/projects/12345",
        price=15000,
        raw_payload={
            "files": [
                {"fname": "tz.pdf", "url": "https://kwork.ru/files/tz.pdf", "size": 102400},
                {"fname": "archive.zip", "url": "https://kwork.ru/files/archive.zip", "size": 204800},
            ]
        },
    )

    enriched_kwork = await enricher.enrich(kwork_order)
    assert enriched_kwork.attachments_text is not None
    assert "tz.pdf" in enriched_kwork.attachments_text
    assert "archive.zip" in enriched_kwork.attachments_text

    # 2. FL.ru enrichment error resilience (e.g. invalid url doesn't crash)
    broken_order = RawOrder(
        source=SourcePlatform.FL_RU,
        external_id="000",
        title="Тест",
        description="Исходное описание",
        url="http://invalid-fl-url-test-404.example.com",
    )
    res = await enricher.enrich(broken_order)
    assert res.description == "Исходное описание"


@pytest.mark.asyncio
async def test_live_fl_ru_rss():
    """Live smoke test to verify FL.ru RSS is reachable and parses."""
    collector = FlRuCollector()
    orders = await collector.fetch_new_orders()
    assert isinstance(orders, list)
    if not orders:
        pytest.skip("FL.ru RSS временно вернул 0 заказов или сетевой таймаут")
    assert orders[0].source == SourcePlatform.FL_RU
