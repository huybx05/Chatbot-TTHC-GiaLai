from __future__ import annotations

import uuid
from uuid import UUID

import pytest
from backend.app.api import chat as chat_api
from backend.app.db.postgres import engine
from backend.app.main import app
from backend.app.memory.rewriter import RewriteResult
from backend.app.memory.types import SessionMemory
from backend.app.rag import retrieval
from fastapi.testclient import TestClient
from sqlalchemy import text


def _register(client: TestClient) -> tuple[str, dict[str, str]]:
    username = f"test_memchat_{uuid.uuid4().hex[:12]}"
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
    chat_api._luot_goi.clear()
    chat_api.xoa_cache()
    with TestClient(app) as test_client:
        yield test_client
    chat_api._luot_goi.clear()
    chat_api.xoa_cache()


def test_chat_truyen_memory_da_load_vao_retrieval(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    username, headers = _register(client)
    captured: dict = {}

    calls: list[SessionMemory] = []

    async def fake(question: str, **kwargs) -> dict:
        captured["question"] = question
        captured["memory"] = kwargs.get("memory")
        calls.append(kwargs["memory"])
        return {
            "outcome": "answered",
            "answer": "Câu trả lời kiểm thử.",
            "answerable": True,
            "answered_procedure": {
                "code": "1.001699",
                "name": "Thủ tục A",
                "source": "resolution",
            },
            "citations": [
                {
                    "procedure_code": "1.001699",
                    "procedure_name": "Thủ tục A",
                    "detail_url": "https://example.test",
                }
            ],
            "resolution": {"code": "1.001699", "name": "Thủ tục A"},
        }

    async def no_rewrite(question: str, _memory: SessionMemory) -> RewriteResult:
        return RewriteResult(
            original_question=question,
            retrieval_question=question,
            used=False,
            is_followup=False,
            anchor=None,
            confidence=1.0,
            reason="test",
        )

    try:
        session_id = _create_session(client, headers)
        monkeypatch.setattr(retrieval, "retrieve", fake)
        monkeypatch.setattr(chat_api, "rewrite_question_with_memory", no_rewrite)
        first = client.post(
            "/chat",
            headers=headers,
            json={
                "question": "Tôi muốn làm thủ tục xác nhận khuyết tật thì cần hồ sơ gì?",
                "session_id": str(session_id),
            },
        )
        assert first.status_code == 200, first.text

        response = client.post(
            "/chat",
            headers=headers,
            json={
                "question": "Lệ phí và thời hạn của thủ tục này là bao nhiêu?",
                "session_id": str(session_id),
            },
        )

        assert response.status_code == 200, response.text
        memory = calls[-1]
        assert isinstance(memory, SessionMemory)
        assert memory.active_procedure is not None
        assert memory.active_procedure.code == "1.001699"
        assert len(memory.recent_turns) == 2

        stored = client.get(
            f"/api/v1/chat-sessions/{session_id}/messages",
            headers=headers,
        )
        assert stored.status_code == 200, stored.text
        rows = stored.json()["items"]
        assert [row["role"] for row in rows] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        assert rows[1]["metadata"]["procedure"]["procedure_code"] == "1.001699"
        assert rows[1]["metadata"]["citations"][0]["url"] == "https://example.test"
    finally:
        _cleanup(username)


def test_chat_stream_tu_luu_user_va_assistant_message(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    username, headers = _register(client)

    async def fake(_question: str, **_kwargs) -> dict:
        return {
            "outcome": "clarify",
            "answer": "",
            "clarify": {
                "question": "Bạn muốn hỏi thủ tục nào?",
                "options": [
                    {"value": "1.001699", "label": "Xác định mức độ khuyết tật"}
                ],
            },
            "citations": [],
        }

    async def no_rewrite(question: str, _memory: SessionMemory) -> RewriteResult:
        return RewriteResult(
            original_question=question,
            retrieval_question=question,
            used=False,
            is_followup=False,
            anchor=None,
            confidence=1.0,
            reason="test",
        )

    try:
        session_id = _create_session(client, headers)
        monkeypatch.setattr(retrieval, "retrieve", fake)
        monkeypatch.setattr(chat_api, "rewrite_question_with_memory", no_rewrite)

        with client.stream(
            "POST",
            "/chat/stream",
            headers=headers,
            json={"question": "Thủ tục này cần gì?", "session_id": str(session_id)},
        ) as response:
            assert response.status_code == 200, response.text
            body = "".join(response.iter_text())
        assert "event: done" in body

        stored = client.get(
            f"/api/v1/chat-sessions/{session_id}/messages",
            headers=headers,
        )
        rows = stored.json()["items"]
        assert [row["role"] for row in rows] == ["user", "assistant"]
        assert rows[1]["metadata"]["status"] == "clarify"
        assert rows[1]["metadata"]["options"] == []
    finally:
        _cleanup(username)


def test_chat_xep_summary_sau_khi_luu_cau_tra_loi(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    username, headers = _register(client)
    called: list[UUID] = []

    async def fake_retrieve(_question: str, **_kwargs) -> dict:
        return {"outcome": "answered", "answer": "Câu trả lời.", "citations": []}

    async def fake_summary(session_id: UUID) -> bool:
        called.append(session_id)
        return False

    try:
        session_id = _create_session(client, headers)
        monkeypatch.setattr(retrieval, "retrieve", fake_retrieve)
        monkeypatch.setattr(chat_api, "summarize_session_memory", fake_summary, raising=False)

        response = client.post(
            "/chat",
            headers=headers,
            json={"question": "Thủ tục này cần gì?", "session_id": str(session_id)},
        )

        assert response.status_code == 200, response.text
        assert called == [session_id]
    finally:
        _cleanup(username)


def test_chat_stream_xep_summary_sau_khi_luu_cau_tra_loi(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    username, headers = _register(client)
    called: list[UUID] = []

    async def fake_retrieve(_question: str, **_kwargs) -> dict:
        return {"outcome": "answered", "answer": "Câu trả lời.", "citations": []}

    async def fake_summary(session_id: UUID) -> bool:
        called.append(session_id)
        return False

    try:
        session_id = _create_session(client, headers)
        monkeypatch.setattr(retrieval, "retrieve", fake_retrieve)
        monkeypatch.setattr(chat_api, "summarize_session_memory", fake_summary)

        with client.stream(
            "POST",
            "/chat/stream",
            headers=headers,
            json={"question": "Thủ tục này cần gì?", "session_id": str(session_id)},
        ) as response:
            assert response.status_code == 200, response.text
            _ = "".join(response.iter_text())

        assert called == [session_id]
    finally:
        _cleanup(username)


def test_chat_khong_tom_tat_neu_khong_luu_duoc_assistant_message(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    username, headers = _register(client)
    called: list[UUID] = []

    async def fake_retrieve(_question: str, **_kwargs) -> dict:
        return {"outcome": "answered", "answer": "Câu trả lời.", "citations": []}

    async def failed_assistant_persist(*_args, role: str, **_kwargs) -> bool:
        return role == "user"

    async def fake_summary(session_id: UUID) -> bool:
        called.append(session_id)
        return False

    try:
        session_id = _create_session(client, headers)
        monkeypatch.setattr(retrieval, "retrieve", fake_retrieve)
        monkeypatch.setattr(chat_api, "_persist_message", failed_assistant_persist)
        monkeypatch.setattr(chat_api, "summarize_session_memory", fake_summary)

        response = client.post(
            "/chat",
            headers=headers,
            json={"question": "Thủ tục này cần gì?", "session_id": str(session_id)},
        )

        assert response.status_code == 200, response.text
        assert called == []
    finally:
        _cleanup(username)
