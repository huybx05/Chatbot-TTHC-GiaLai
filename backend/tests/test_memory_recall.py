from __future__ import annotations

import uuid
from uuid import UUID

import pytest
from backend.app.api.chat_sessions import persist_chat_message
from backend.app.db.postgres import engine
from backend.app.main import app
from backend.app.memory.reader import load_topic_turns
from fastapi.testclient import TestClient
from sqlalchemy import text


def _register(client: TestClient) -> tuple[str, int, dict[str, str]]:
    username = f"test_recall_{uuid.uuid4().hex[:12]}"
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "matkhau123"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return username, int(body["user"]["id"]), {"Authorization": f"Bearer {body['access_token']}"}


def _create_session(client: TestClient, headers: dict[str, str]) -> UUID:
    response = client.post("/api/v1/chat-sessions", headers=headers)
    assert response.status_code == 201, response.text
    return UUID(response.json()["id"])


def _add_pair(
    client: TestClient,
    headers: dict[str, str],
    session_id: UUID,
    *,
    content: str,
    code: str,
    status: str = "answered",
) -> None:
    del client, headers
    with engine.connect() as conn:
        user_id = int(
            conn.execute(
                text("SELECT user_id FROM chat_sessions WHERE id = :session_id"),
                {"session_id": session_id},
            ).scalar_one()
        )
    persist_chat_message(
        session_id=session_id,
        user_id=user_id,
        role="user",
        content=f"hỏi {content}",
    )
    persist_chat_message(
        session_id=session_id,
        user_id=user_id,
        role="assistant",
        content=f"đáp {content}",
        metadata={
            "status": status,
            "procedure": {
                "procedure_code": code,
                "procedure_name": f"Thủ tục {code}",
            },
        },
    )


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


def test_recall_lay_dung_cap_cu_cua_topic(client: TestClient) -> None:
    username, user_id, headers = _register(client)
    try:
        session_id = _create_session(client, headers)
        _add_pair(client, headers, session_id, content="A1", code="A")
        _add_pair(client, headers, session_id, content="B1", code="B")
        _add_pair(client, headers, session_id, content="A2", code="A")

        with engine.connect() as conn:
            turns = load_topic_turns(
                conn,
                user_id=user_id,
                session_id=session_id,
                procedure_code="A",
                limit_pairs=2,
            )

        assert [turn.role for turn in turns] == [
            "user",
            "assistant",
            "user",
            "assistant",
        ]
        assert "A1" in turns[0].content
        assert "A2" in turns[2].content
        assert all("B1" not in turn.content for turn in turns)
    finally:
        _cleanup(username)


def test_recall_bo_qua_luot_abstained_cung_ma(client: TestClient) -> None:
    username, user_id, headers = _register(client)
    try:
        session_id = _create_session(client, headers)
        _add_pair(
            client,
            headers,
            session_id,
            content="A-abstained",
            code="A",
            status="abstained",
        )
        _add_pair(client, headers, session_id, content="A-answered", code="A")

        with engine.connect() as conn:
            turns = load_topic_turns(
                conn,
                user_id=user_id,
                session_id=session_id,
                procedure_code="A",
                limit_pairs=2,
            )

        assert [turn.content for turn in turns] == ["hỏi A-answered", "đáp A-answered"]
    finally:
        _cleanup(username)


def test_recall_khong_doc_session_cua_user_khac(client: TestClient) -> None:
    username_a, _, headers_a = _register(client)
    username_b, user_b_id, _ = _register(client)
    try:
        session_a = _create_session(client, headers_a)
        _add_pair(client, headers_a, session_a, content="A", code="A")

        with engine.connect() as conn:
            turns = load_topic_turns(
                conn,
                user_id=user_b_id,
                session_id=session_a,
                procedure_code="A",
            )

        assert turns == []
    finally:
        _cleanup(username_a)
        _cleanup(username_b)


def test_recall_chi_truy_van_assistant_dung_ma_thu_tuc() -> None:
    queries: list[str] = []

    class Result:
        def first(self):
            return 1

        def mappings(self):
            return self

        def all(self):
            return []

    class Connection:
        def execute(self, statement, _params):
            queries.append(str(statement))
            return Result()

    turns = load_topic_turns(
        Connection(),  # type: ignore[arg-type]
        user_id=1,
        session_id=uuid.uuid4(),
        procedure_code="1.001699",
    )

    assert turns == []
    assert "metadata -> 'procedure' ->> 'procedure_code' = :procedure_code" in queries[-1]
