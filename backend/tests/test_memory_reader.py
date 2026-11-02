from __future__ import annotations

import uuid
from uuid import UUID

import pytest
from backend.app.api.chat_sessions import persist_chat_message
from backend.app.db.postgres import engine
from backend.app.main import app
from backend.app.memory.reader import load_session_memory
from backend.app.memory.repository import (
    ensure_memory_row,
    update_summary,
    update_topics,
)
from fastapi.testclient import TestClient
from sqlalchemy import text


def _register(client: TestClient) -> tuple[str, int, dict[str, str]]:
    username = f"test_reader_{uuid.uuid4().hex[:12]}"
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


def _add_message(
    client: TestClient,
    headers: dict[str, str],
    session_id: UUID,
    *,
    role: str,
    content: str,
    metadata: dict | None = None,
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
        metadata=metadata,
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


def test_reader_chi_lay_cap_hoan_chinh_va_bo_qua_cau_hoi_hien_tai(
    client: TestClient,
) -> None:
    username, user_id, headers = _register(client)
    try:
        session_id = _create_session(client, headers)
        for index in range(4):
            _add_message(
                client,
                headers,
                session_id,
                role="user",
                content=f"câu hỏi {index}",
            )
            _add_message(
                client,
                headers,
                session_id,
                role="assistant",
                content=f"câu trả lời {index}",
                metadata={
                    "procedure": {
                        "procedure_code": "A" if index in (0, 2, 3) else "B",
                        "procedure_name": "Thủ tục A" if index != 1 else "Thủ tục B",
                    },
                    "status": "answered",
                },
            )

        current_id = _add_message(
            client,
            headers,
            session_id,
            role="user",
            content="câu hỏi hiện tại",
        )

        with engine.connect() as conn:
            memory = load_session_memory(
                conn,
                user_id=user_id,
                session_id=session_id,
                current_message_id=UUID(current_id),
            )

        assert memory is not None
        assert len(memory.recent_turns) == 6
        assert all(
            turn.content != "câu hỏi hiện tại" for turn in memory.recent_turns
        )
        assert [topic.procedure_code for topic in memory.topics] == ["A", "B"]
        assert memory.active_procedure is not None
        assert memory.active_procedure.code == "A"
    finally:
        _cleanup(username)


def test_reader_khong_nhan_procedure_tu_luot_abstained(
    client: TestClient,
) -> None:
    username, user_id, headers = _register(client)
    try:
        session_id = _create_session(client, headers)
        _add_message(
            client,
            headers,
            session_id,
            role="user",
            content="Tôi làm rơi chứng chỉ, xin lại thủ tục nào?",
        )
        _add_message(
            client,
            headers,
            session_id,
            role="assistant",
            content="Tôi cần biết bạn muốn hỏi thủ tục nào.",
            metadata={
                "status": "abstained",
                "procedure": {
                    "procedure_code": "1.014100",
                    "procedure_name": "Cấp lại Chứng chỉ hành nghề dược",
                },
            },
        )

        with engine.begin() as conn:
            ensure_memory_row(conn, session_id)
            update_topics(
                conn,
                session_id,
                [
                    {
                        "order": 1,
                        "procedure_code": "1.014100",
                        "procedure_name": "Cấp lại Chứng chỉ hành nghề dược",
                    }
                ],
            )

        with engine.connect() as conn:
            memory = load_session_memory(
                conn,
                user_id=user_id,
                session_id=session_id,
            )

        assert memory is not None
        assert memory.topics == []
        assert memory.active_procedure is None
        assert all(turn.procedure_code is None for turn in memory.recent_turns)
    finally:
        _cleanup(username)


def test_reader_tra_ve_none_khi_session_khong_thuoc_user(client: TestClient) -> None:
    username_a, _, headers_a = _register(client)
    username_b, user_b_id, _ = _register(client)
    try:
        session_a = _create_session(client, headers_a)

        with engine.connect() as conn:
            memory = load_session_memory(
                conn,
                user_id=user_b_id,
                session_id=session_a,
            )

        assert memory is None
    finally:
        _cleanup(username_a)
        _cleanup(username_b)


def test_reader_doc_summary_va_checkpoint_tu_bo_nho(client: TestClient) -> None:
    username, user_id, headers = _register(client)
    try:
        session_id = _create_session(client, headers)
        _add_message(
            client,
            headers,
            session_id,
            role="user",
            content="Hồ sơ gồm gì?",
        )
        assistant_id = _add_message(
            client,
            headers,
            session_id,
            role="assistant",
            content="Hồ sơ gồm đơn.",
            metadata={"status": "answered"},
        )

        with engine.begin() as conn:
            ensure_memory_row(conn, session_id)
            update_summary(
                conn,
                session_id,
                summary="Người dùng đã hỏi về hồ sơ.",
                through_message_id=UUID(assistant_id),
            )

        with engine.connect() as conn:
            memory = load_session_memory(
                conn,
                user_id=user_id,
                session_id=session_id,
            )

        assert memory is not None
        assert memory.summary == "Người dùng đã hỏi về hồ sơ."
        assert memory.summary_through_message_id == assistant_id
        assert len(memory.recent_turns) == 2
    finally:
        _cleanup(username)


def test_reader_doc_clarify_options_gan_nhat(client: TestClient) -> None:
    username, user_id, headers = _register(client)
    try:
        session_id = _create_session(client, headers)
        _add_message(
            client,
            headers,
            session_id,
            role="user",
            content="Tôi cần làm thủ tục gì?",
        )
        _add_message(
            client,
            headers,
            session_id,
            role="assistant",
            content="Bạn muốn chọn thủ tục nào?",
            metadata={
                "status": "clarify",
                "options": [
                    {"value": "1.001699", "label": "Thủ tục A"},
                    {"value": "1.014758", "label": "Thủ tục B"},
                ],
            },
        )

        with engine.connect() as conn:
            memory = load_session_memory(
                conn,
                user_id=user_id,
                session_id=session_id,
            )

        assert memory is not None
        assert memory.last_outcome == "clarify"
        assert memory.last_clarify_options[0]["value"] == "1.001699"
    finally:
        _cleanup(username)
