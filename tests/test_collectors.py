"""Tests for all collectors: Kwork, FL.ru, Freelance.ru, Pchel.net."""

import pytest
from src.collectors.fl_ru import FlRuCollector
from src.collectors.freelance_ru import FreelanceRuCollector
from src.collectors.habr_career import HabrCareerCollector
from src.collectors.kwork import KworkCollector
from src.collectors.pchel_net import PchelNetCollector
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


@pytest.mark.asyncio
async def test_habr_career_card_parsing_fixed_salary(monkeypatch):
    collector = HabrCareerCollector()
    mock_rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Хабр Карьера</title>
        <item>
          <title>Требуется «Python разработчик / Python Developer» (Москва, от 240 000 до 260 000 ₽)</title>
          <link>https://career.habr.com/vacancies/1000168482</link>
          <guid>1000168482</guid>
          <author>СОГАЗ</author>
          <description>Компания СОГАЗ ищет разработчика. Требуемые навыки: #Python, #FastAPI, #PostgreSQL</description>
        </item>
      </channel>
    </rss>
    """
    import httpx
    async def mock_get(self, url, *args, **kwargs):
        req = httpx.Request("GET", str(url))
        return httpx.Response(status_code=200, text=mock_rss, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
    vacancies = await collector.fetch_new_orders()
    assert len(vacancies) == 1
    v = vacancies[0]
    assert v.external_id == "1000168482"
    assert v.title == "Python разработчик / Python Developer"
    assert v.price == 240000.0
    assert v.is_negotiable is False
    assert v.source == SourcePlatform.HABR_CAREER
    assert "FastAPI" in v.tags
    assert "СОГАЗ" in v.attachments_text


@pytest.mark.asyncio
async def test_habr_career_card_parsing_negotiable_salary(monkeypatch):
    collector = HabrCareerCollector()
    mock_rss = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>Хабр Карьера</title>
        <item>
          <title>Требуется «ML Инженер» (Новосибирск)</title>
          <link>https://career.habr.com/vacancies/1000168375</link>
          <guid>1000168375</guid>
          <author>True Engineering</author>
          <description>Требуемые навыки: #PyTorch, #Python</description>
        </item>
      </channel>
    </rss>
    """
    import httpx
    async def mock_get(self, url, *args, **kwargs):
        req = httpx.Request("GET", str(url))
        return httpx.Response(status_code=200, text=mock_rss, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)
    vacancies = await collector.fetch_new_orders()
    assert len(vacancies) == 1
    v = vacancies[0]
    assert v.title == "ML Инженер"
    assert v.price is None
    assert v.is_negotiable is True
    assert v.source == SourcePlatform.HABR_CAREER


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
async def test_freelance_ru_category_pagination_and_cold_start(monkeypatch):
    """Проверка пагинации по категориям IT и логики холодного старта FreelanceRuCollector."""
    import httpx
    collector = FreelanceRuCollector(categories=[4, 724], normal_pages=1, backfill_pages=3)

    requested_urls = []

    mock_article = """
    <article class="task-card">
        <a class="task-card__title-link" href="/task/view/{id}" title="Бот">Бот {id}</a>
        <p class="task-card__desc">Сделать Telegram-бота на Python</p>
        <div class="task-card__budget">15 000 руб</div>
    </article>
    """

    async def mock_get(self, url, *args, **kwargs):
        requested_urls.append(str(url))
        req = httpx.Request("GET", str(url))
        # Генерируем карточки в ответе с числовыми ID
        html_resp = "".join(mock_article.format(id=f"{len(requested_urls)}{i}01") for i in range(2))
        return httpx.Response(status_code=200, text=html_resp, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    # 1. Первый запуск (cold start backfill) - глубина 3 страницы для категорий
    orders_cold = await collector.fetch_new_orders()
    assert len(orders_cold) > 0
    # Проверяем, что запрашивались страницы категорий c[]=4 и c[]=724 с глубиной
    assert any("c[]=4" in u and "page=2" in u for u in requested_urls)
    assert any("c[]=724" in u for u in requested_urls)

    # 2. Второй запуск (обычный легкий режим) - глубина 1 страница
    requested_urls.clear()
    orders_normal = await collector.fetch_new_orders()
    assert len(orders_normal) > 0
    # На обычном проходе page=2 для c[]=4 не должен запрашиваться (так как normal_pages=1)
    assert not any("page=2" in u for u in requested_urls)


@pytest.mark.asyncio
async def test_pchel_net_cold_start_backfill(monkeypatch):
    """Проверка начального бэкфилла для PchelNetCollector."""
    import httpx
    pchel = PchelNetCollector(normal_pages=1, backfill_pages=3)
    pchel_urls = []

    async def mock_get(self, url, *args, **kwargs):
        u = str(url)
        req = httpx.Request("GET", u)
        if "pchel.net" in u:
            pchel_urls.append(u)
            card = '<div class="project-block-cont"><div class="project-title"><a href="/jobs/programming/test-101/">Тест</a></div><div class="project-text">Текст</div><div class="price">15000 руб</div></div></div></div>'
            return httpx.Response(status_code=200, text=card, request=req)
        return httpx.Response(status_code=404, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    # Холодный запуск: должны пройти 3 страницы
    await pchel.fetch_new_orders(is_cold_start=True)
    assert len(pchel_urls) == 3
    assert any("page-2" in u for u in pchel_urls)
    assert any("page-3" in u for u in pchel_urls)

    # Обычный запуск: только 1 страница
    pchel_urls.clear()
    await pchel.fetch_new_orders(is_cold_start=False)
    assert len(pchel_urls) == 1


@pytest.mark.asyncio
async def test_live_fl_ru_rss():
    """Live smoke test to verify FL.ru RSS is reachable and parses."""
    collector = FlRuCollector()
    orders = await collector.fetch_new_orders()
    assert isinstance(orders, list)
    if not orders:
        pytest.skip("FL.ru RSS временно вернул 0 заказов или сетевой таймаут")
    assert orders[0].source == SourcePlatform.FL_RU


@pytest.mark.asyncio
async def test_freelance_ru_pro_and_free_detection():
    collector = FreelanceRuCollector()

    # Premium / PRO article
    premium_html = """
    <article class="task-card task-card--premium">
        <a class="task-card__title-link" href="/task/view/13998" title="Дизайн">Разработка сайта</a>
        <span class="task-badge task-badge--premium">★ Только для Премиум</span>
        <div class="task-card__budget">50 000 руб</div>
    </article>
    """
    order_pro = collector._parse_article(premium_html)
    assert order_pro is not None
    assert order_pro.is_pro_only is True

    # Free / Open to all article
    free_html = """
    <article class="task-card">
        <a class="task-card__title-link" href="/task/view/13999" title="Скрипт">Скрипт парсера</a>
        <span class="task-badge task-badge--all">Видно всем</span>
        <div class="task-card__budget">10 000 руб</div>
    </article>
    """
    order_free = collector._parse_article(free_html)
    assert order_free is not None
    assert order_free.is_pro_only is False


@pytest.mark.asyncio
async def test_fl_ru_pro_and_paid_detection(monkeypatch):
    import httpx
    collector = FlRuCollector()

    catalog_html = """
    <div class="b-post topprjpay" id="project-item5527049">
        <img src="https://st.fl.ru/images/urgently-1.png">
        <a href="/projects/5527049/test.html">Платный проект</a>
    </div>
    <div class="b-post" id="project-item5527122">
        <a href="/projects/5527122/test.html">Обычный проект</a>
    </div>
    """

    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>FL.ru RSS</title>
        <item>
          <title>Полный аудит проекта в нише 18+ (для всех)</title>
          <link>https://www.fl.ru/projects/5527049/test.html</link>
          <guid>5527049</guid>
          <description>Описание платного проекта</description>
        </item>
        <item>
          <title>Инженер-конструктор: раскладка (Бюджет: 30 000  &#8381;, для всех)</title>
          <link>https://www.fl.ru/projects/5527122/test.html</link>
          <guid>5527122</guid>
          <description>Описание открытого проекта</description>
        </item>
        <item>
          <title>Нужно сделать макет в кореле (Бюджет: 1 000  &#8381;)</title>
          <link>https://www.fl.ru/projects/5527137/test.html</link>
          <guid>5527137</guid>
          <description>Описание проекта без бейджа для всех</description>
        </item>
      </channel>
    </rss>
    """

    async def mock_get(self, url, *args, **kwargs):
        u = str(url)
        req = httpx.Request("GET", u)
        if "rss" in u or "xml" in u:
            return httpx.Response(status_code=200, text=rss_xml, request=req)
        return httpx.Response(status_code=200, text=catalog_html, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    orders = await collector.fetch_new_orders()
    assert len(orders) == 3

    # 1. Платное объявление (даже если в RSS написано 'для всех') -> is_pro_only = True
    paid_order = next(o for o in orders if o.external_id == "5527049")
    assert paid_order.is_pro_only is True
    assert "(для всех)" not in paid_order.title

    # 2. Обычный проект с '(Бюджет: ..., для всех)' -> is_pro_only = False
    free_order = next(o for o in orders if o.external_id == "5527122")
    assert free_order.is_pro_only is False
    assert "для всех" not in free_order.title
    assert free_order.price == 30000.0

    # 3. Обычный проект без '(для всех)' -> is_pro_only = True
    pro_order = next(o for o in orders if o.external_id == "5527137")
    assert pro_order.is_pro_only is True


@pytest.mark.asyncio
async def test_enricher_pro_detection(monkeypatch):
    from src.collectors.enricher import OrderEnricher
    from src.models.order import RawOrder
    import httpx

    enricher = OrderEnricher()

    order_fl = RawOrder(
        source=SourcePlatform.FL_RU,
        external_id="5527049",
        title="Тест",
        description="Кратко",
        url="https://www.fl.ru/projects/5527049/test.html",
        is_pro_only=False,
    )

    async def mock_fl_get(self, url, *args, **kwargs):
        html = '<div class="b-layout"><a href="/payed-emp/">Платный</a><div id="projectp5527049">Полное ТЗ</div></div>'
        req = httpx.Request("GET", str(url))
        return httpx.Response(status_code=200, text=html, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_fl_get)
    res_fl = await enricher.enrich(order_fl)
    assert res_fl.is_pro_only is True
    assert "Полное ТЗ" in res_fl.description

    order_fr = RawOrder(
        source=SourcePlatform.FREELANCE_RU,
        external_id="13998",
        title="Тест",
        description="Кратко",
        url="https://freelance.ru/task/view/13998",
        is_pro_only=False,
    )

    async def mock_fr_get(self, url, *args, **kwargs):
        html = '<div class="task-badge task-badge--premium">Только для Премиум</div><h1>Заголовок</h1>Полное описание ТЗ<div>footer</div>'
        req = httpx.Request("GET", str(url))
        return httpx.Response(status_code=200, text=html, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_fr_get)
    res_fr = await enricher.enrich(order_fr)
    assert res_fr.is_pro_only is True
    assert "Полное описание ТЗ" in res_fr.description
