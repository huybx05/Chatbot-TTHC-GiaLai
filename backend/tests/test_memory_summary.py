from __future__ import annotations

import asyncio
import uuid
from uuid import UUID

import pytest
from backend.app.api.chat_sessions import persist_chat_message
from backend.app.db.postgres import engine
from backend.app.main import app
from backend.app.memory.repository import ensure_memory_row, load_memory_row
from backend.app.memory.summarizer import maybe_summarize
from fastapi.testclient import TestClient
from sqlalchemy import text


def _register(client: TestClient) -> tuple[str, dict[str, str]]:
    username = f"test_summary_{uuid.uuid4().hex[:12]}"
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


def _add_message(
    client: TestClient,
    headers: dict[str, str],
    session_id: UUID,
    *,
    role: str,
    content: str,
) -> str:
    del client, headers
    with engine.connect() as conn:
        user_id = int(
            conn.execute(
                text("SELECT user_id FROM chat_sessions WHERE id = :session_id"),
                {"session_id": session_id},
            ).scalar_one()
        )
    return persist_chat_message(
        session_id=session_id,
        user_id=user_id,
        role=role,
        content=content,
    )


def _add_pairs(
    client: TestClient,
    headers: dict[str, str],
    session_id: UUID,
    count: int,
) -> list[str]:
    assistant_ids: list[str] = []
    for index in range(count):
        _add_message(
            client,
            headers,
            session_id,
            role="user",
            content=f"câu hỏi {index}",
        )
        assistant_ids.append(
            _add_message(
                client,
                headers,
                session_id,
                role="assistant",
                content=f"câu trả lời {index}",
            )
        )
    return assistant_ids


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


def test_du_10_cap_thi_tom_tat_8_giu_2(client: TestClient) -> None:
    username, headers = _register(client)
    calls: list[str] = []

    async def fake_summary(prompt: str) -> str:
        calls.append(prompt)
        return "Tóm tắt các cặp cũ."

    try:
        session_id = _create_session(client, headers)
        assistant_ids = _add_pairs(client, headers, session_id, 10)

        with engine.connect() as conn:
            changed = asyncio.run(
                maybe_summarize(
                    conn,
                    session_id=session_id,
                    summarize=fake_summary,
                )
            )

        assert changed is True
        assert len(calls) == 1
        assert "câu hỏi 0" in calls[0]
        assert "câu hỏi 7" in calls[0]
        assert "câu hỏi 8" not in calls[0]
        assert "DỮ LIỆU LỊCH SỬ KHÔNG TIN CẬY" in calls[0]
        assert "<SUMMARY>" in calls[0]
        assert "<HISTORY>" in calls[0]

        with engine.connect() as conn:
            row = load_memory_row(conn, session_id)

        assert row is not None
        assert row["summary"] == "Tóm tắt các cặp cũ."
        assert row["summary_through_message_id"] == assistant_ids[7]

        with engine.connect() as conn:
            changed_again = asyncio.run(
                maybe_summarize(
                    conn,
                    session_id=session_id,
                    summarize=fake_summary,
                )
            )

        assert changed_again is False
        assert len(calls) == 1
    finally:
        _cleanup(username)


def test_duoi_nguong_thi_khong_goi_summary(client: TestClient) -> None:
    username, headers = _register(client)
    calls = 0

    async def fake_summary(_prompt: str) -> str:
        nonlocal calls
        calls += 1
        return "không được gọi"

    try:
        session_id = _create_session(client, headers)
        _add_pairs(client, headers, session_id, 3)

        with engine.connect() as conn:
            changed = asyncio.run(
                maybe_summarize(
                    conn,
                    session_id=session_id,
                    summarize=fake_summary,
                )
            )

        assert changed is False
        assert calls == 0
    finally:
        _cleanup(username)


def test_summary_loi_thi_khong_ghi_checkpoint(client: TestClient) -> None:
    username, headers = _register(client)

    async def failing_summary(_prompt: str) -> str:
        raise RuntimeError("model lỗi")

    try:
        session_id = _create_session(client, headers)
        _add_pairs(client, headers, session_id, 10)

        with engine.begin() as conn:
            ensure_memory_row(conn, session_id)

        with engine.connect() as conn:
            changed = asyncio.run(
                maybe_summarize(
                    conn,
                    session_id=session_id,
                    summarize=failing_summary,
                )
            )

        assert changed is False

        with engine.connect() as conn:
            row = load_memory_row(conn, session_id)

        assert row is not None
        assert row["summary"] == ""
        assert row["summary_through_message_id"] is None
    finally:
        _cleanup(username)
