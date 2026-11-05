"""Tests for HeadHunter applicant service and 1-click apply integration."""

import json
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from src.config import settings
from src.models.order import OrderPriority, OrderStatus, RawOrder, SourcePlatform
from src.services.hh_applicant_service import HhApplicantService
from src.storage.db import init_db
from src.storage.repository import OrderRepository
from src.web.app import create_web_app


@pytest.mark.asyncio
async def test_hh_applicant_status_and_auth_url(tmp_path, monkeypatch):
    db_path = tmp_path / "test_hh.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)
    svc = HhApplicantService(repo)

    monkeypatch.setattr(settings.secrets, "HH_CLIENT_ID", "test_client_id")
    monkeypatch.setattr(settings.secrets, "HH_REDIRECT_URI", "https://jobs.3dvex.ru/callback")

    url = svc.get_auth_url()
    assert "https://hh.ru/oauth/authorize" in url
    assert "client_id=test_client_id" in url
    assert "redirect_uri=https://jobs.3dvex.ru/callback" in url

    # Default: not connected
    status = await svc.get_applicant_status()
    assert status["connected"] is False
    assert status["resume_id"] is None

    # After saving token and resume_id: connected
    await repo.set_setting("hh_user_token", "test_user_tok")
    await repo.set_setting("hh_resume_id", "res_123")
    await repo.set_setting("hh_resume_title", "Senior Python / AI Engineer")

    status2 = await svc.get_applicant_status()
    assert status2["connected"] is True
    assert status2["resume_id"] == "res_123"
    assert status2["resume_title"] == "Senior Python / AI Engineer"


@pytest.mark.asyncio
async def test_hh_applicant_exchange_code(tmp_path, monkeypatch):
    db_path = tmp_path / "test_hh_code.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)
    svc = HhApplicantService(repo)

    monkeypatch.setattr(settings.secrets, "HH_CLIENT_ID", "cid_123")
    monkeypatch.setattr(settings.secrets, "HH_CLIENT_SECRET", "csec_456")
    monkeypatch.setattr(settings.secrets, "HH_REDIRECT_URI", "https://jobs.3dvex.ru/callback")

    def mock_transport(request: httpx.Request):
        if request.url.path == "/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "acc_tok_999",
                    "refresh_token": "ref_tok_999",
                    "expires_in": 1209600,
                },
            )
        elif request.url.path == "/resumes/mine":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "resume_abc_1",
                            "title": "Python & AI Developer",
                            "status": {"id": "published"},
                        }
                    ]
                },
            )
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_transport))
    with patch("httpx.AsyncClient", return_value=client):
        res = await svc.exchange_code("code_xyz")

    assert res["ok"] is True
    assert res["resume_id"] == "resume_abc_1"
    assert res["resume_title"] == "Python & AI Developer"

    saved_tok = await repo.get_setting("hh_user_token")
    assert saved_tok == "acc_tok_999"


@pytest.mark.asyncio
async def test_hh_applicant_apply_to_vacancy(tmp_path, monkeypatch):
    db_path = tmp_path / "test_hh_apply.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)
    svc = HhApplicantService(repo)

    # 1. Without auth
    res_no_auth = await svc.apply_to_vacancy("112233", "Письмо")
    assert res_no_auth["ok"] is False
    assert res_no_auth["need_auth"] is True

    # 2. With auth
    await repo.set_setting("hh_user_token", "user_tok_valid")
    await repo.set_setting("hh_resume_id", "resume_target")

    captured_payload = {}

    def mock_transport(request: httpx.Request):
        nonlocal captured_payload
        if request.url.path == "/negotiations":
            content_str = request.content.decode("utf-8")
            from urllib.parse import parse_qs
            captured_payload = parse_qs(content_str)
            return httpx.Response(201, json={"id": "negotiation_101"})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_transport))
    with patch("httpx.AsyncClient", return_value=client):
        raw_letter = (
            "Здравствуйте! Ознакомился с вакансией.\n\n"
            "Мой стек: Python, FastAPI, LangChain.\n\n"
            "Буду рад обсудить задачи ROOMGRAM, кейсы автоматизации и детали решений на звонке или личной встрече.\n\n"
            "С уважением, Андрей Пименов"
        )
        apply_res = await svc.apply_to_vacancy("998877", raw_letter)

    assert apply_res["ok"] is True
    assert apply_res["status"] == "applied"
    assert captured_payload["vacancy_id"] == ["998877"]
    assert captured_payload["resume_id"] == ["resume_target"]
    sent_letter = captured_payload["message"][0]
    # Check boilerplate is sanitized
    assert "Буду рад обсудить задачи ROOMGRAM" not in sent_letter
    assert "Мой стек: Python, FastAPI, LangChain." in sent_letter


@pytest.mark.asyncio
async def test_web_hh_apply_and_oauth_routes(tmp_path, monkeypatch):
    db_path = tmp_path / "test_web_hh.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)
    app = create_web_app(repo=repo, enable_auth=False)

    monkeypatch.setattr(settings.secrets, "HH_CLIENT_ID", "test_cid")
    monkeypatch.setattr(settings.secrets, "HH_CLIENT_SECRET", "test_csec")
    monkeypatch.setattr(settings.secrets, "HH_REDIRECT_URI", "https://jobs.3dvex.ru/callback")

    # Set up user token & resume
    await repo.set_setting("hh_user_token", "test_user_tok")
    await repo.set_setting("hh_resume_id", "resume_999")

    # Insert test HH vacancy
    order = RawOrder(
        source=SourcePlatform.HH_RU,
        external_id="12345678",
        title="AI Engineer (LLM Agents)",
        description="Требуется разработчик агентных систем",
        url="https://hh.ru/vacancy/12345678",
        price=250000,
    )
    order_id = await repo.insert_raw_order(
        order=order,
        status=OrderStatus.ANALYZED,
        priority=OrderPriority.HOT,
    )
    await repo.update_proposal(order_id, proposal_text="Здравствуйте! Готов реализовать агентов.")

    def mock_transport(request: httpx.Request):
        if request.url.path == "/negotiations":
            return httpx.Response(201, json={"created": True})
        return httpx.Response(404)

    client_mock = httpx.AsyncClient(transport=httpx.MockTransport(mock_transport))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        # Test /hh/auth redirect
        auth_resp = await ac.get("/hh/auth", follow_redirects=False)
        assert auth_resp.status_code == 307
        assert "https://hh.ru/oauth/authorize" in auth_resp.headers["location"]

        # Test 1-click apply API endpoint
        with patch("httpx.AsyncClient", return_value=client_mock):
            apply_resp = await ac.post(f"/api/vacancies/{order_id}/apply")

        assert apply_resp.status_code == 200
        apply_json = apply_resp.json()
        assert apply_json["ok"] is True
        assert apply_json["status"] == "applied"

        # Check database is_responded status toggled to True
        updated_order = await repo.get_by_id(order_id)
        assert updated_order["is_responded"] == 1


@pytest.mark.asyncio
async def test_hh_applicant_apply_closed_vacancy(tmp_path, monkeypatch):
    db_path = tmp_path / "test_hh_closed.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)
    svc = HhApplicantService(repo)

    await repo.set_setting("hh_user_token", "user_tok_valid")
    await repo.set_setting("hh_resume_id", "resume_target")

    def mock_transport(request: httpx.Request):
        if request.url.path == "/negotiations":
            return httpx.Response(403, json={"errors": [{"type": "forbidden"}]})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(mock_transport))
    with patch("httpx.AsyncClient", return_value=client):
        res = await svc.apply_to_vacancy("139178355", "Письмо")

    assert res["ok"] is False
    assert res["status"] == "closed"
    assert "закрыта работодателем" in res["message"]


@pytest.mark.asyncio
async def test_web_client_log_and_no_cache_middleware(tmp_path):
    db_path = tmp_path / "test_client_log.db"
    await init_db(db_path)
    repo = OrderRepository(db_path=db_path)
    app = create_web_app(repo=repo, enable_auth=False)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        # Test client log endpoint
        resp = await ac.post(
            "/api/client-log",
            json={"action": "click_apply_hh", "order_id": "123", "msg": "user clicked apply"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Test no-cache headers on GET /
        get_resp = await ac.get("/")
        assert get_resp.status_code == 200
        assert "no-store" in get_resp.headers.get("cache-control", "").lower()
        assert "no-cache" in get_resp.headers.get("cache-control", "").lower()
