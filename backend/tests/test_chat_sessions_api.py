"""API chat_sessions + chat_messages: quyền sở hữu và lưu lịch sử.

Các bài này dùng PostgreSQL thật để kiểm tra cả khoá ngoại và JSONB. Mỗi bài tạo
người dùng tạm với tên ngẫu nhiên rồi xoá; xoá user sẽ cascade session + message.
"""

from __future__ import annotations

import uuid

import pytest
from backend.app.api.chat_sessions import persist_chat_message
from backend.app.db.postgres import engine
from backend.app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import text


def _register(client: TestClient) -> tuple[str, dict[str, str]]:
    username = f"test_chat_{uuid.uuid4().hex[:12]}"
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "matkhau123"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["access_token"]
    return username, {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _cleanup(*usernames: str) -> None:
    if not usernames:
        return
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM users WHERE username = ANY(:names)"),
            {"names": list(usernames)},
        )


def test_delete_session_giu_lai_log(client: TestClient) -> None:
    username, headers = _register(client)
    try:
        created = client.post("/api/v1/chat-sessions", headers=headers)
        session_id = uuid.UUID(created.json()["id"])
        with engine.connect() as conn:
            user_id = conn.execute(
                text("SELECT id FROM users WHERE username = :name"),
                {"name": username},
            ).scalar_one()
        persist_chat_message(
            session_id=session_id,
            user_id=user_id,
            role="user",
            content="Xin chào",
        )
        persist_chat_message(
            session_id=session_id,
            user_id=user_id,
            role="assistant",
            content="Chào bạn.",
        )

        assert client.delete(
            f"/api/v1/chat-sessions/{session_id}", headers=headers
        ).status_code == 200
        with engine.connect() as conn:
            count = conn.execute(
                text("SELECT count(*) FROM chat_messages WHERE session_id = :id"),
                {"id": session_id},
            ).scalar_one()
            deleted_at = conn.execute(
                text("SELECT deleted_at FROM chat_sessions WHERE id = :id"),
                {"id": session_id},
            ).scalar_one()
        assert count == 2
        assert deleted_at is not None
        assert client.get("/api/v1/chat-sessions", headers=headers).json()["items"] == []
    finally:
        _cleanup(username)


def test_client_khong_duoc_tu_ghi_tin_nhan(client: TestClient) -> None:
    username, headers = _register(client)
    try:
        created = client.post("/api/v1/chat-sessions", headers=headers)
        assert created.status_code == 201, created.text
        session = created.json()
        session_id = session["id"]
        assert session["message_count"] == 0
        assert session["title"] == "Cuộc trò chuyện mới"

        user_message = client.post(
            f"/api/v1/chat-sessions/{session_id}/messages",
            headers=headers,
            json={"role": "user", "content": "Tôi muốn hỏi về sổ đỏ"},
        )
        assert user_message.status_code == 405, user_message.text

        assistant_message = client.post(
            f"/api/v1/chat-sessions/{session_id}/messages",
            headers=headers,
            json={
                "role": "assistant",
                "content": "Bạn cần chuẩn bị hồ sơ.",
                "metadata": {
                    "citations": [{"title": "Nguồn", "url": "https://example.test"}],
                    "status": "answered",
                },
            },
        )
        assert assistant_message.status_code == 405, assistant_message.text

        listed = client.get("/api/v1/chat-sessions", headers=headers)
        assert listed.status_code == 200
        item = listed.json()["items"][0]
        assert item["id"] == session_id
        assert item["message_count"] == 0

        messages = client.get(
            f"/api/v1/chat-sessions/{session_id}/messages", headers=headers
        )
        assert messages.status_code == 200
        rows = messages.json()["items"]
        assert rows == []

        deleted = client.delete(f"/api/v1/chat-sessions/{session_id}", headers=headers)
        assert deleted.status_code == 200
        missing = client.get(
            f"/api/v1/chat-sessions/{session_id}/messages", headers=headers
        )
        assert missing.status_code == 404
    finally:
        _cleanup(username)


def test_khong_doc_duoc_session_cua_nguoi_khac(client: TestClient) -> None:
    owner, owner_headers = _register(client)
    intruder, intruder_headers = _register(client)
    try:
        created = client.post("/api/v1/chat-sessions", headers=owner_headers)
        session_id = created.json()["id"]

        assert (
            client.get("/api/v1/chat-sessions", headers=intruder_headers).json()["items"]
            == []
        )
        assert (
            client.get(
                f"/api/v1/chat-sessions/{session_id}/messages",
                headers=intruder_headers,
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/v1/chat-sessions/{session_id}/messages",
                headers=intruder_headers,
                json={"role": "user", "content": "chen vào"},
            ).status_code
            == 405
        )
        assert (
            client.delete(
                f"/api/v1/chat-sessions/{session_id}", headers=intruder_headers
            ).status_code
            == 404
        )
    finally:
        _cleanup(owner, intruder)
