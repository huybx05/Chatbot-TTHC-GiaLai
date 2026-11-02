from __future__ import annotations

from uuid import uuid4

from backend.app.db.postgres import engine
from backend.app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import text

client = TestClient(app)


def test_session_cookie_dung_duoc_cho_cac_api_can_dang_nhap() -> None:
    username = f"session_{uuid4().hex[:12]}"
    user_id: int | None = None

    try:
        registered = client.post(
            "/api/v1/auth/register",
            json={"username": username, "password": "Test-pass-123"},
        )
        assert registered.status_code == 201
        user_id = int(registered.json()["user"]["id"])
        assert client.cookies.get("session_id")

        me = client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json()["username"] == username

        sessions = client.get("/api/v1/chat-sessions")
        assert sessions.status_code == 200
        assert "items" in sessions.json()

        logged_out = client.post("/api/v1/auth/logout")
        assert logged_out.status_code == 200
        assert client.get("/api/v1/auth/me").status_code == 401
    finally:
        client.cookies.clear()
        if user_id is not None:
            with engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM audit_logs WHERE user_id = :id"),
                    {"id": user_id},
                )
                conn.execute(
                    text("DELETE FROM sessions WHERE user_id = :id"),
                    {"id": user_id},
                )
                conn.execute(
                    text("DELETE FROM users WHERE id = :id"),
                    {"id": user_id},
                )
