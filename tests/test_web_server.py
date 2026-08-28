import pytest
from httpx import AsyncClient, ASGITransport
from pathlib import Path
from web_server import app
from database import db
from config import settings


@pytest.mark.asyncio
async def test_health_check(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "db_path", tmp_path / "test_web.db")
    await db.init()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "services" in data
        assert data["port"] == 38291


@pytest.mark.asyncio
async def test_auth_and_magic_link(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "db_path", tmp_path / "test_auth.db")
    monkeypatch.setattr(settings, "WEBUI_AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "WEBUI_AUTH_TOKEN", "test_secret_token_123")
    await db.init()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as ac:
        # 1. Unauthenticated request to / -> should render login page with Çekirdekod branding
        unauth_res = await ac.get("/")
        assert unauth_res.status_code == 200
        assert "Güvenli Giriş" in unauth_res.text
        assert "cekirdekod.com" in unauth_res.text

        # 2. Magic link request: /?token=test_secret_token_123 -> should redirect to / with cookie
        magic_res = await ac.get("/?token=test_secret_token_123")
        assert magic_res.status_code == 302
        assert magic_res.headers["location"] == "/"
        assert "hub_auth=test_secret_token_123" in magic_res.headers.get("set-cookie", "")

        # 3. Request with valid cookie -> should render main dashboard
        cookie_res = await ac.get("/", cookies={"hub_auth": "test_secret_token_123"})
        assert cookie_res.status_code == 200
        assert "Antigravity Hub" in cookie_res.text
        assert "cekirdekod.com" in cookie_res.text

        # 4. API login endpoint test
        login_res = await ac.post("/api/auth/login", json={"token": "test_secret_token_123"})
        assert login_res.status_code == 200
        assert "hub_auth" in login_res.headers.get("set-cookie", "")

        # 5. Invalid token login
        invalid_res = await ac.post("/api/auth/login", json={"token": "wrong_token"})
        assert invalid_res.status_code == 401


@pytest.mark.asyncio
async def test_session_endpoints_with_auth(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "db_path", tmp_path / "test_session.db")
    monkeypatch.setattr(settings, "WEBUI_AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "WEBUI_AUTH_TOKEN", "valid_token_xyz")
    await db.init()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Without auth header/cookie -> 401 Unauthorized
        unauth_api = await ac.get("/api/session?user_id=0")
        assert unauth_api.status_code == 401

        # With valid auth header
        auth_headers = {"Authorization": "Bearer valid_token_xyz"}
        res = await ac.get("/api/session?user_id=0", headers=auth_headers)
        assert res.status_code == 200
        session = res.json()
        assert session["user_id"] == 0

        # Update session
        update_res = await ac.post("/api/session", headers=auth_headers, json={
            "user_id": 0,
            "model": "gemini-3.7-flash-high",
            "effort": "low",
            "auto_approve": True
        })
        assert update_res.status_code == 200
        assert update_res.json()["session"]["effort"] == "low"

        # Reset session
        reset_res = await ac.post("/api/session/reset", headers=auth_headers, json={"user_id": 0})
        assert reset_res.status_code == 200


@pytest.mark.asyncio
async def test_whitelist_endpoints_with_auth(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "db_path", tmp_path / "test_wl.db")
    monkeypatch.setattr(settings, "WEBUI_AUTH_ENABLED", True)
    monkeypatch.setattr(settings, "WEBUI_AUTH_TOKEN", "valid_token_xyz")
    await db.init()

    transport = ASGITransport(app=app)
    auth_headers = {"Authorization": "Bearer valid_token_xyz"}
    async with AsyncClient(transport=transport, base_url="http://test", headers=auth_headers) as ac:
        # Add user
        add_res = await ac.post("/api/whitelist", json={
            "user_id": 987654,
            "username": "testuser",
            "role": "user"
        })
        assert add_res.status_code == 200

        # Get whitelist
        get_res = await ac.get("/api/whitelist")
        assert get_res.status_code == 200
        users = get_res.json()["users"]
        assert any(u["user_id"] == 987654 for u in users)

        # Delete user
        del_res = await ac.delete("/api/whitelist/987654")
        assert del_res.status_code == 200
