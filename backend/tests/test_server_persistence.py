from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

import pytest
from backend.app.api import chat as chat_api
from backend.app.db.postgres import engine
from backend.app.main import app
from backend.app.memory.rewriter import RewriteResult
from backend.app.rag import retrieval
from fastapi.testclient import TestClient
from sqlalchemy import text


def _register(client: TestClient) -> tuple[str, dict[str, str]]:
    username = f"test_persist_{uuid.uuid4().hex[:12]}"
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "matkhau123"},
    )
    assert response.status_code == 201, response.text
    return username, {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_session(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/api/v1/chat-sessions", headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _delete_user(username: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE username = :name"), {"name": username})


def _messages(session_id: str) -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT role, content, metadata
                  FROM chat_messages
                 WHERE session_id = :session_id
                 ORDER BY created_at ASC, id ASC
                """
            ),
            {"session_id": UUID(session_id)},
        ).mappings().all()
    return [dict(row) for row in rows]


def _fake_retrieve(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(_question: str, **_kwargs) -> dict:
        return {
            "outcome": "answered",
            "answer": "Câu trả lời kiểm thử.",
            "citations": [],
            "answerable": True,
            "resolution": {"code": "1.001699", "name": "Thủ tục A"},
            "answered_procedure": {
                "code": "1.001699",
                "name": "Thủ tục A",
                "source": "resolution",
            },
        }

    monkeypatch.setattr(retrieval, "retrieve", fake)


@pytest.fixture
def client() -> TestClient:
    chat_api._luot_goi.clear()
    chat_api.xoa_cache()
    with TestClient(app) as test_client:
        yield test_client
    chat_api._luot_goi.clear()
    chat_api.xoa_cache()


def test_chat_tu_choi_field_metadata_tu_client(client: TestClient) -> None:
    response = client.post(
        "/chat",
        json={
            "question": "Hồ sơ gồm gì?",
            "metadata": {
                "procedure": {"procedure_code": "9.999999", "procedure_name": "Giả"}
            },
        },
    )

    assert response.status_code == 422


def test_server_luu_user_va_assistant_tu_metadata_that(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    username, headers = _register(client)
    try:
        session_id = _create_session(client, headers)
        _fake_retrieve(monkeypatch)

        response = client.post(
            "/chat",
            headers=headers,
            json={
                "question": "Hồ sơ thủ tục A gồm gì?",
                "session_id": session_id,
            },
        )

        assert response.status_code == 200, response.text
        assert response.json()["procedure"]["procedure_code"] == "1.001699"

        rows = _messages(session_id)
        assert [row["role"] for row in rows] == ["user", "assistant"]
        assert rows[0]["content"] == "Hồ sơ thủ tục A gồm gì?"
        assert rows[1]["content"] == "Câu trả lời kiểm thử."
        assert rows[1]["metadata"]["procedure"]["procedure_code"] == "1.001699"
        assert rows[1]["metadata"]["status"] == "answered"
    finally:
        _delete_user(username)


def test_server_luu_chuoi_hai_cau_va_memory_doc_lai_duoc(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    username, headers = _register(client)
    try:
        session_id = _create_session(client, headers)
        _fake_retrieve(monkeypatch)
        captured: dict[str, Any] = {}

        async def fake_rewrite(_question: str, memory):
            captured["memory"] = memory
            return RewriteResult(
                original_question="Còn lệ phí thì sao?",
                retrieval_question="Còn lệ phí thì sao?",
                used=False,
                is_followup=False,
                anchor=None,
                confidence=0.0,
                reason="not_followup",
            )

        monkeypatch.setattr(chat_api, "rewrite_question_with_memory", fake_rewrite)

        first = client.post(
            "/chat",
            headers=headers,
            json={
                "question": "Hồ sơ thủ tục A gồm gì?",
                "session_id": session_id,
            },
        )
        assert first.status_code == 200, first.text

        second = client.post(
            "/chat",
            headers=headers,
            json={
                "question": "Còn lệ phí thì sao?",
                "session_id": session_id,
            },
        )

        assert second.status_code == 200, second.text
        memory = captured["memory"]
        assert memory.active_procedure is not None
        assert memory.active_procedure.code == "1.001699"
        assert len(memory.recent_turns) >= 2

        rows = _messages(session_id)
        assert [row["role"] for row in rows] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
    finally:
        _delete_user(username)


def test_summary_duoc_xep_sau_khi_luu_assistant(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    username, headers = _register(client)
    try:
        session_id = _create_session(client, headers)
        _fake_retrieve(monkeypatch)
        called: list[str] = []

        async def fake_summary(value) -> bool:
            called.append(str(value))
            return True

        monkeypatch.setattr(chat_api, "summarize_session_memory", fake_summary)

        response = client.post(
            "/chat",
            headers=headers,
            json={
                "question": "Hồ sơ thủ tục A gồm gì?",
                "session_id": session_id,
            },
        )

        assert response.status_code == 200, response.text
        assert called == [session_id]
        rows = _messages(session_id)
        assert [row["role"] for row in rows] == ["user", "assistant"]
    finally:
        _delete_user(username)


def test_stream_cung_luu_assistant_metadata_that(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    username, headers = _register(client)
    try:
        session_id = _create_session(client, headers)

        async def fake(_question: str, **_kwargs) -> dict:
            return {
                "outcome": "clarify",
                "clarify": {
                    "question": "Bạn muốn hỏi thủ tục nào?",
                    "options": [],
                },
                "resolution": {},
            }

        monkeypatch.setattr(retrieval, "retrieve", fake)

        response = client.post(
            "/chat/stream",
            headers=headers,
            json={
                "question": "Thủ tục này cần gì?",
                "session_id": session_id,
            },
        )

        assert response.status_code == 200, response.text
        assert "event: done" in response.text

        rows = _messages(session_id)
        assert [row["role"] for row in rows] == ["user", "assistant"]
        assert rows[1]["metadata"]["status"] == "clarify"
        assert rows[1]["content"].strip()
    finally:
        _delete_user(username)
