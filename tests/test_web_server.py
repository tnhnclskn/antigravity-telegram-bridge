import pytest
from httpx import AsyncClient, ASGITransport
from pathlib import Path
from web_server import app
from database import db


@pytest.mark.asyncio
async def test_health_check(tmp_path: Path, monkeypatch):
    # Set temp db
    monkeypatch.setattr(db, "db_path", tmp_path / "test_web.db")
    await db.init()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "services" in data

        # Test index page
        index_res = await ac.get("/")
        assert index_res.status_code == 200
        assert "Antigravity Hub" in index_res.text


@pytest.mark.asyncio
async def test_session_endpoints(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "db_path", tmp_path / "test_session.db")
    await db.init()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Get session
        res = await ac.get("/api/session?user_id=0")
        assert res.status_code == 200
        session = res.json()
        assert session["user_id"] == 0

        # Update session
        update_res = await ac.post("/api/session", json={
            "user_id": 0,
            "model": "gemini-3.7-flash-high",
            "effort": "low",
            "auto_approve": True
        })
        assert update_res.status_code == 200
        assert update_res.json()["session"]["effort"] == "low"

        # Reset session
        reset_res = await ac.post("/api/session/reset", json={"user_id": 0})
        assert reset_res.status_code == 200


@pytest.mark.asyncio
async def test_whitelist_endpoints(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(db, "db_path", tmp_path / "test_wl.db")
    await db.init()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
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
