from __future__ import annotations

import uuid
from uuid import UUID

import pytest
from backend.app.db.postgres import engine
from backend.app.main import app
from backend.app.memory.repository import (
    ensure_memory_row,
    load_memory_row,
    update_summary,
    update_topics,
)
from fastapi.testclient import TestClient
from sqlalchemy import text


def _register(client: TestClient) -> tuple[str, dict[str, str]]:
    username = f"test_memory_{uuid.uuid4().hex[:12]}"
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "matkhau123"},
    )
    assert response.status_code == 201, response.text
    return username, {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_session(client: TestClient, headers: dict[str, str]) -> UUID:
    response = client.post("/api/v1/chat-sessions", headers=headers)
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


def _cleanup(username: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM users WHERE username = :username"),
            {"username": username},
        )


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def test_ensure_memory_row_is_idempotent(client: TestClient) -> None:
    username, headers = _register(client)
    try:
        session_id = _create_session(client, headers)

        with engine.begin() as conn:
            ensure_memory_row(conn, session_id)
            ensure_memory_row(conn, session_id)
            row = load_memory_row(conn, session_id)

        assert row is not None
        assert row["session_id"] == str(session_id)
        assert row["summary"] == ""
        assert row["summary_through_message_id"] is None
        assert row["topics"] == []
        assert row["updated_at"] is not None
    finally:
        _cleanup(username)


def test_update_summary_and_topics(client: TestClient) -> None:
    username, headers = _register(client)
    try:
        session_id = _create_session(client, headers)
        topics = [
            {
                "order": 1,
                "procedure_code": "1.001699",
                "procedure_name": "Xác định mức độ khuyết tật",
                "first_message_id": str(uuid.uuid4()),
                "last_message_id": str(uuid.uuid4()),
            }
        ]

        with engine.begin() as conn:
            ensure_memory_row(conn, session_id)
            update_summary(
                conn,
                session_id,
                summary="Người dùng đã hỏi về hồ sơ.",
                through_message_id=None,
            )
            update_topics(conn, session_id, topics)
            row = load_memory_row(conn, session_id)

        assert row is not None
        assert row["summary"] == "Người dùng đã hỏi về hồ sơ."
        assert row["topics"] == topics
    finally:
        _cleanup(username)


def test_delete_session_cascades_memory(client: TestClient) -> None:
    username, headers = _register(client)
    try:
        session_id = _create_session(client, headers)

        with engine.begin() as conn:
            ensure_memory_row(conn, session_id)

        with engine.begin() as conn:
            conn.execute(
                text("DELETE FROM chat_sessions WHERE id = :session_id"),
                {"session_id": session_id},
            )
            count = conn.execute(
                text(
                    "SELECT count(*) FROM chat_session_memory "
                    "WHERE session_id = :session_id"
                ),
                {"session_id": session_id},
            ).scalar_one()

        assert count == 0
    finally:
        _cleanup(username)
