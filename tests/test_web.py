"""Tests for FastAPI web dashboard."""

import pytest
import httpx
from src.models.analysis import AnalysisResult, PertEstimate
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
    order_id = await repo.insert_raw_order(
        order=order,
        status=OrderStatus.ANALYZED,
        priority=OrderPriority.HOT,
    )
    # Сохраняем анализ с рыночной и рекомендуемой ценой
    analysis = AnalysisResult(
        take_order=True,
        priority=OrderPriority.HOT,
        score=9,
        is_relevant=True,
        pert=PertEstimate(
            optimistic_days=1.0,
            most_likely_days=2.0,
            pessimistic_days=4.0,
            expected_days=2.17,
            sigma=0.5,
        ),
        realistic_days=2.0,
        market_price=38000,
        recommended_price=35000,
        price_justification="Бюджет клиента 30к, рыночная цена 38к, рекомендуем 35к",
        complexity=4,
        pure_dev_hours=6.0,
        matched_project="Avia_Pars",
        executive_summary="Разработка бота",
    )
    await repo.update_analysis(order_id, analysis)

    app = create_web_app(repo=repo, enable_auth=False)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        auth=("Horizontal42", "qaz403111"),
    ) as client:
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
        assert "Бюджет клиента:" in html
        assert "30 000 ₽" in html
        assert "Рыночная:" in html
        assert "38 000 ₽" in html
        assert "Рекомендуемая:" in html
        assert "35 000 ₽" in html
        assert "Финансовая оценка и стратегия ставок" in html
        assert "Бюджет клиента 30к, рыночная цена 38к" in html
        assert 'id="scrollToTopBtn"' in html
        assert "scrollToTop()" in html

        # 5. HTML Tabs (analytics, rules, health, settings)
        resp_analytics = await client.get("/?tab=analytics")
        assert resp_analytics.status_code == 200
        assert "Аналитика воронки фриланс-бирж" in resp_analytics.text

        resp_analytics_hh = await client.get("/?section=hh_ru&tab=analytics")
        assert resp_analytics_hh.status_code == 200
        assert "Аналитика воронки вакансий" in resp_analytics_hh.text

        resp_responded = await client.get("/?tab=responded")
        assert resp_responded.status_code == 200

        # Toggle skipped API test
        resp_skip = await client.post(f"/api/orders/{order_id}/toggle-skipped")
        assert resp_skip.status_code == 200
        assert resp_skip.json()["ok"] is True
        assert resp_skip.json()["is_skipped"] is True

        # Unskip back so it remains visible in default active feed
        resp_unskip = await client.post(f"/api/orders/{order_id}/toggle-skipped")
        assert resp_unskip.status_code == 200
        assert resp_unskip.json()["is_skipped"] is False

        # 5b. HTML Target order loading via order_id param
        resp_target = await client.get(f"/?order_id={order_id}")
        assert resp_target.status_code == 200
        assert f'data-id="{order_id}"' in resp_target.text
        assert "Разработка Telegram бота" in resp_target.text

        resp_rules = await client.get("/?tab=rules")
        assert resp_rules.status_code == 200
        assert "Белый список ключевых слов" in resp_rules.text

        from unittest.mock import patch, AsyncMock
        with patch("src.services.health_check.HealthCheckService.run_full_check") as mock_hc:
            mock_hc.return_value = {
                "all_ok": True,
                "checked_at": "28.10.2026 16:00:00",
                "exchanges": [
                    {"name": "Kwork", "url": "https://kwork.ru", "ok": True, "status_code": 200, "latency_ms": 250, "error": None}
                ],
                "services": [
                    {"name": "Mistral API", "ok": True, "status_code": 200, "latency_ms": 150, "details": None, "error": None}
                ],
            }
            resp_health = await client.get("/?tab=health")
            assert resp_health.status_code == 200
            assert "Мониторинг доступности бирж" in resp_health.text
            assert "Kwork" in resp_health.text

            # Health Check API
            resp_api_hc = await client.get("/api/health-check")
            assert resp_api_hc.status_code == 200
            assert resp_api_hc.json()["all_ok"] is True

        # Settings API & Settings Tab
        resp_settings_tab = await client.get("/?tab=settings")
        assert resp_settings_tab.status_code == 200
        assert "Интерактивные настройки мониторинга" in resp_settings_tab.text

        # System Config Tab & Config API
        resp_config_tab = await client.get("/?tab=config")
        assert resp_config_tab.status_code == 200
        assert "Системная конфигурация" in resp_config_tab.text
        assert "yamlConfigEditor" in resp_config_tab.text
        assert "cfg_poll_interval" in resp_config_tab.text
        assert "cfg_filter_min_budget" in resp_config_tab.text
        assert "saveGuiConfig" in resp_config_tab.text

        # Verify advanced filter controls on main dashboard
        resp_main = await client.get("/?tab=hot")
        assert resp_main.status_code == 200
        assert "orderSortSelect" in resp_main.text
        assert "topicChipsContainer" in resp_main.text
        assert "filterPriceMin" in resp_main.text
        assert "applyClientFilters" in resp_main.text

        # GET /api/config
        resp_get_config = await client.get("/api/config")
        assert resp_get_config.status_code == 200
        assert resp_get_config.json()["ok"] is True
        assert "storage" in resp_get_config.json()["yaml"]
        assert "polling" in resp_get_config.json()["config"]

        # POST /api/config with structured GUI config (using mock to avoid mutating production config.yml)
        import copy
        from src.config import settings
        original_cfg = copy.deepcopy(settings.app_config)
        test_yaml_path = tmp_path / "test_config.yml"
        test_yaml_path.write_text(resp_get_config.json()["yaml"], encoding="utf-8")

        with patch("src.config.CONFIG_YAML_PATH", test_yaml_path):
            try:
                resp_post_gui_config = await client.post(
                    "/api/config",
                    json={"config": {"filter": {"min_budget": 25000}}},
                )
                assert resp_post_gui_config.status_code == 200
                assert resp_post_gui_config.json()["ok"] is True

                # POST /api/config validation error test
                resp_post_config_err = await client.post("/api/config", json={"yaml": "storage: invalid_format_not_dict"})
                assert resp_post_config_err.status_code == 400
                assert resp_post_config_err.json()["ok"] is False
            finally:
                settings.app_config = original_cfg

        # GET /api/settings
        resp_get_settings = await client.get("/api/settings")
        assert resp_get_settings.status_code == 200
        assert resp_get_settings.json()["ok"] is True
        assert resp_get_settings.json()["settings"]["min_budget"] == 10000

        # POST /api/settings
        resp_post_settings = await client.post(
            "/api/settings",
            json={"min_budget": 20000, "platform_fl_ru": False, "filter_pro_only": True},
        )
        assert resp_post_settings.status_code == 200
        assert resp_post_settings.json()["ok"] is True
        assert resp_post_settings.json()["settings"]["min_budget"] == 20000
        assert resp_post_settings.json()["settings"]["platform_fl_ru"] is False

        # 6. Generate proposal on-demand with dual price
        from src.models.analysis import ProposalResult
        with patch("src.analyzer.factory.get_llm_client") as mock_get_llm:
            mock_client = AsyncMock()
            mock_client.generate_proposal.return_value = ProposalResult(
                "Готовый отклик на aiogram.",
                recommended_price=42000,
                market_price=48000,
                price_justification="Рыночная ставка 48к, тактическая 42к",
            )
            mock_get_llm.return_value = mock_client

            resp_gen = await client.post("/api/orders/1/generate-proposal")
            assert resp_gen.status_code == 200
            data_gen = resp_gen.json()
            assert data_gen["ok"] is True
            assert data_gen["proposal_text"] == "Готовый отклик на aiogram."
            assert data_gen["recommended_price"] == 42000
            assert data_gen["market_price"] == 48000
            assert "Рыночная ставка 48к" in data_gen["price_justification"]

            # Verify it persisted to DB
            updated_order = await repo.get_by_id(1)
            assert updated_order["proposal_text"] == "Готовый отклик на aiogram."
            assert updated_order["recommended_price"] == 42000
            assert updated_order["market_price"] == 48000

        # 7. Order chat: get empty history, post question, verify persistence
        resp_chat_empty = await client.get("/api/orders/1/chat")
        assert resp_chat_empty.status_code == 200
        assert resp_chat_empty.json()["messages"] == []

        with patch("src.analyzer.factory.get_llm_client") as mock_get_llm:
            mock_client = AsyncMock()
            mock_client.chat_order.return_value = (
                "Стек aiogram 3 идеально подходит, рисков с нагрузкой нет.",
                "Mistral (mistral-small-latest)",
            )
            mock_get_llm.return_value = mock_client

            resp_post_chat = await client.post(
                "/api/orders/1/chat",
                json={"message": "Подойдет ли aiogram 3 для этой задачи?", "model": "auto"},
            )
            assert resp_post_chat.status_code == 200
            data_chat = resp_post_chat.json()
            assert data_chat["ok"] is True
            assert "aiogram 3 идеально подходит" in data_chat["reply"]
            assert data_chat["model"] == "Mistral (mistral-small-latest)"

        # Verify chat history is saved in DB and retrieved
        resp_chat_history = await client.get("/api/orders/1/chat")
        assert resp_chat_history.status_code == 200
        history_msgs = resp_chat_history.json()["messages"]
        assert len(history_msgs) == 2
        assert history_msgs[0]["role"] == "user"
        assert history_msgs[0]["message"] == "Подойдет ли aiogram 3 для этой задачи?"
        assert history_msgs[1]["role"] == "assistant"
        assert "aiogram 3 идеально подходит" in history_msgs[1]["message"]

        # Verify HTML contains chat toggle button
        resp_html = await client.get("/")
        assert "Вопрос по заказу" in resp_html.text


@pytest.mark.asyncio
async def test_web_basic_auth(tmp_path):
    """Проверка защиты дашборда и API через HTTP Basic Auth."""
    db_path = tmp_path / "test_auth.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)

    # Приложение с включенной авторизацией
    app = create_web_app(repo=repo, enable_auth=True)
    transport = httpx.ASGITransport(app=app)

    # 1. Запрос без авторизации -> 401 Unauthorized
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client_anon:
        resp = await client_anon.get("/")
        assert resp.status_code == 401
        assert "WWW-Authenticate" in resp.headers
        assert "Basic" in resp.headers["WWW-Authenticate"]

        # API эндпоинты также закрыты
        resp_api = await client_anon.get("/api/stats")
        assert resp_api.status_code == 401

        # Но healthcheck остается открытым для внешнего мониторинга (GET и HEAD)
        resp_hc = await client_anon.get("/health")
        assert resp_hc.status_code == 200
        assert resp_hc.json()["status"] == "ok"

        resp_head = await client_anon.head("/health")
        assert resp_head.status_code == 200

    # 2. Запрос с неверным паролем -> 401 Unauthorized
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        auth=("Horizontal42", "wrong_password"),
    ) as client_wrong:
        resp_wrong = await client_wrong.get("/")
        assert resp_wrong.status_code == 401

    # 3. Запрос с корректными учетными данными -> 200 OK
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        auth=("Horizontal42", "qaz403111"),
    ) as client_auth:
        resp_ok = await client_auth.get("/")
        assert resp_ok.status_code == 200

        resp_api_ok = await client_auth.get("/api/stats")
        assert resp_api_ok.status_code == 200

    # 4. Приложение с отключенной авторизацией (enable_auth=False)
    app_no_auth = create_web_app(repo=repo, enable_auth=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_no_auth),
        base_url="http://test",
    ) as client_disabled:
        resp_disabled = await client_disabled.get("/")
        assert resp_disabled.status_code == 200


@pytest.mark.asyncio
async def test_web_dashboard_vacancy_bullet_formatting(tmp_path):
    """Проверка форматирования анализа вакансий на сайте в аккуратные буллеты без сырых скобок."""
    db_path = tmp_path / "test_vac_format.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)

    vac = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="hh_777",
        title="Junior ML-инженер",
        description="Разработка компьютерного зрения",
        url="https://hh.ru/vacancy/777",
        price=150000,
    )
    vac_id = await repo.insert_raw_order(order=vac, status=OrderStatus.ANALYZED, priority=OrderPriority.HOT)

    raw_reqs = "['Python (обязательно)', 'PyTorch/TensorFlow'] {'years': '1-3 года'} ['Docker (базовый)']"
    raw_match = "['Опыт работы с **YOLOv8** (AgroTech CV)', 'Работа с **FastAPI**']"

    analysis = AnalysisResult(
        take_order=True,
        score=9,
        priority=OrderPriority.HOT,
        candidate_requirements=raw_reqs,
        match_reason=raw_match,
        company_overview="АО Концерн ЦНИИ",
        job_responsibilities="Разработка CV алгоритмов",
        pert=PertEstimate(
            optimistic_days=1.0,
            most_likely_days=2.0,
            pessimistic_days=3.0,
            expected_days=2.0,
            sigma=0.3,
        ),
        realistic_days=2.0,
        complexity=3,
        pure_dev_hours=4.0,
        matched_project="Cortex IT",
        executive_summary="Junior ML Инженер",
    )
    await repo.update_analysis(vac_id, analysis)

    app = create_web_app(repo=repo, enable_auth=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/?section=hh_ru&tab=hot")
        assert resp.status_code == 200
        html_text = resp.text

        # Проверяем отсутствие сырого мусора
        assert "['Python (обязательно)'" not in html_text
        assert "['Опыт работы с" not in html_text

        # Проверяем наличие чистого HTML-списка и выделения
        assert "Python (обязательно)" in html_text
        assert "PyTorch/TensorFlow" in html_text
        assert "Docker (базовый)" in html_text
        assert '<strong class="text-white font-semibold">YOLOv8</strong>' in html_text
        assert '<strong class="text-white font-semibold">FastAPI</strong>' in html_text


@pytest.mark.asyncio
async def test_web_generate_proposal_fallback_and_api(tmp_path, monkeypatch):
    """Проверка генерации отклика по требованию и отображения контейнера отклика без анализа."""
    db_path = tmp_path / "test_gen_prop.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)

    # Заказ без анализа (например, только поступил или trash/normal без analysis_json)
    raw = RawOrder(
        source=SourcePlatform.KWORK,
        external_id="raw_123",
        title="Парсер сайта объявлений",
        description="Нужен парсер на Python с экспортом в CSV",
        url="https://kwork.ru/projects/raw_123",
        price=15000,
    )
    raw_id = await repo.insert_raw_order(order=raw, status=OrderStatus.NEW, priority=OrderPriority.NORMAL)

    # Мокируем get_llm_client
    class FakeProposalResult:
        def __init__(self):
            self.proposal_text = "Здравствуйте! Имею подтвержденный опыт разработки парсеров на Playwright."
            self.recommended_price = 16000
            self.market_price = 18000
            self.price_justification = "Рыночная цена парсинга объявлений"
            self.estimated_days = 2.0

        def __str__(self):
            return self.proposal_text

    class FakeLLMClient:
        async def generate_proposal(self, order, analysis_data):
            return FakeProposalResult()

        async def chat_order(self, order, analysis_data, proposal_text, history, user_message, model_preference):
            return "Ответ модели по стеку и рискам", "fake-gemini"

    fake_client = FakeLLMClient()
    monkeypatch.setattr("src.analyzer.factory.get_llm_client", lambda: fake_client)

    app = create_web_app(repo=repo, enable_auth=False)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Проверяем наличие proposal-box даже для заказа без анализа
        resp = await client.get("/?tab=all")
        assert resp.status_code == 200
        assert f'id="proposal-box-{raw_id}"' in resp.text
        assert f"generateProposal('{raw_id}', this)" in resp.text

        # 2. Вызываем API генерации отклика
        gen_resp = await client.post(f"/api/orders/{raw_id}/generate-proposal")
        assert gen_resp.status_code == 200
        gen_data = gen_resp.json()
        assert gen_data["ok"] is True
        assert "Имею подтвержденный опыт разработки" in gen_data["proposal_text"]
        assert gen_data["recommended_price"] == 16000
        assert gen_data["market_price"] == 18000

        # 3. Проверяем чат по заказу
        chat_post = await client.post(
            f"/api/orders/{raw_id}/chat",
            json={"message": "Какой стек лучше использовать?", "model": "auto"},
        )
        assert chat_post.status_code == 200
        chat_data = chat_post.json()
        assert chat_data["ok"] is True
        assert chat_data["reply"] == "Ответ модели по стеку и рискам"

        # 4. Проверяем получение истории чата
        chat_get = await client.get(f"/api/orders/{raw_id}/chat")
        assert chat_get.status_code == 200
        history = chat_get.json()["messages"]
        assert len(history) == 2
        assert history[0]["message"] == "Какой стек лучше использовать?"
        assert history[1]["message"] == "Ответ модели по стеку и рискам"

        # 5. Проверяем сохранение настроек вакансий через /api/settings
        settings_post = await client.post(
            "/api/settings",
            json={
                "vacancy_city": "Москва",
                "vacancy_min_salary": 90000,
                "vacancy_work_format": "remote",
                "vacancy_allow_negotiable": True,
            },
        )
        assert settings_post.status_code == 200
        assert settings_post.json()["ok"] is True
        assert settings_post.json()["settings"]["vacancy_city"] == "Москва"
        assert settings_post.json()["settings"]["vacancy_min_salary"] == 90000

        # 6. Проверяем поиск существующего заказа по URL через /api/orders/lookup-or-add
        lookup_resp = await client.post(
            "/api/orders/lookup-or-add",
            json={"url": "https://kwork.ru/projects/raw_123"},
        )
        assert lookup_resp.status_code == 200
        lookup_data = lookup_resp.json()
        assert lookup_data["ok"] is True
        assert lookup_data["status"] == "found"
        assert lookup_data["order"]["id"] == raw_id
        assert lookup_data["order"]["external_id"] == "raw_123"

        # 7. Проверяем валидацию пустого URL
        empty_resp = await client.post(
            "/api/orders/lookup-or-add",
            json={"url": ""},
        )
        assert empty_resp.status_code == 400
        assert empty_resp.json()["ok"] is False

        # 8. Проверяем API локального пересчета /api/orders/recalculate
        recalc_resp = await client.post(
            "/api/orders/recalculate",
            json={"scope": "trash", "limit": 10, "analyze_llm": False},
        )
        assert recalc_resp.status_code == 200
        recalc_data = recalc_resp.json()
        assert recalc_data["ok"] is True
        assert "Локальный пересчет завершен" in recalc_data["message"]



