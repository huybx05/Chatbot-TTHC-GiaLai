from __future__ import annotations

import asyncio
from uuid import UUID

from backend.app.api.chat_sessions import persist_chat_message
from backend.app.api.guest_sessions import cleanup_expired_guest_sessions
from backend.app.db.postgres import engine
from backend.app.main import app
from backend.app.memory.service import load_chat_memory
from fastapi.testclient import TestClient
from sqlalchemy import text

client = TestClient(app)


def test_guest_session_lifecycle() -> None:
    created = client.post("/chat/guest-session")
    assert created.status_code == 201
    session_id = created.json()["session_id"]
    assert client.cookies.get("dsh_guest_token")

    got = client.get("/chat/guest-session")
    assert got.status_code == 200
    assert got.json()["session_id"] == session_id

    deleted = client.delete("/chat/guest-session")
    assert deleted.status_code == 200
    assert client.get("/chat/guest-session").status_code == 404


def test_guest_session_expires() -> None:
    created = client.post("/chat/guest-session")
    session_id = created.json()["session_id"]
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE chat_sessions SET expires_at = NOW() - INTERVAL '1 second' "
                "WHERE id = :id"
            ),
            {"id": session_id},
        )
    assert client.get("/chat/guest-session").status_code == 404


def test_guest_delete_giu_lai_log() -> None:
    created = client.post("/chat/guest-session")
    session_id = UUID(created.json()["session_id"])
    persist_chat_message(
        session_id=session_id,
        user_id=None,
        role="user",
        content="Xin chào",
        guest=True,
    )
    assert client.delete("/chat/guest-session").status_code == 200
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM chat_messages WHERE session_id = :id"),
            {"id": session_id},
        ).scalar_one()
        deleted_at = conn.execute(
            text("SELECT deleted_at FROM chat_sessions WHERE id = :id"),
            {"id": session_id},
        ).scalar_one()
    assert count == 1
    assert deleted_at is not None


def test_guest_cleanup_giu_lai_log() -> None:
    created = client.post("/chat/guest-session")
    session_id = UUID(created.json()["session_id"])
    persist_chat_message(
        session_id=session_id,
        user_id=None,
        role="user",
        content="Xin chào",
        guest=True,
    )
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE chat_sessions SET expires_at = NOW() - INTERVAL '1 second' "
                "WHERE id = :id"
            ),
            {"id": session_id},
        )
    cleanup_expired_guest_sessions()
    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM chat_messages WHERE session_id = :id"),
            {"id": session_id},
        ).scalar_one()
    assert count == 1


def test_guest_memory_persist_va_doc_lai() -> None:
    created = client.post("/chat/guest-session")
    session_id = UUID(created.json()["session_id"])
    persist_chat_message(
        session_id=session_id,
        user_id=None,
        role="user",
        content="Hồ sơ gồm gì?",
        guest=True,
    )
    persist_chat_message(
        session_id=session_id,
        user_id=None,
        role="assistant",
        content="Gồm đơn đề nghị.",
        guest=True,
    )

    memory = asyncio.run(
        load_chat_memory(
            user_id=None,
            session_id=session_id,
            current_message_id=None,
            allow_guest=True,
        )
    )
    assert memory is not None
    assert [turn.role for turn in memory.recent_turns] == ["user", "assistant"]
