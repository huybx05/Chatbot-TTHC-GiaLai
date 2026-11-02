from __future__ import annotations

from uuid import UUID

from backend.app.api.chat_sessions import persist_chat_message
from backend.app.db.postgres import engine
from backend.app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import text

client = TestClient(app)


def test_guest_can_like_and_remove_feedback() -> None:
    created = client.post("/chat/guest-session")
    session_id = UUID(created.json()["session_id"])
    message_id = persist_chat_message(
        session_id=session_id,
        user_id=None,
        role="assistant",
        content="Câu trả lời thử nghiệm.",
        guest=True,
    )

    liked = client.post(
        f"/chat/messages/{message_id}/feedback",
        json={"feedback": "like", "reasons": [], "comment": ""},
    )
    assert liked.status_code == 200
    assert liked.json()["feedback"] == "like"

    with engine.connect() as conn:
        metadata = conn.execute(
            text("SELECT metadata FROM chat_messages WHERE id = :id"),
            {"id": message_id},
        ).scalar_one()
    assert metadata["feedback"]["value"] == "like"

    logs = client.get("/api/admin/conversations").json()["items"]
    row = next(item for item in logs if item["id"] == message_id)
    assert row["feedback"]["value"] == "like"

    removed = client.post(
        f"/chat/messages/{message_id}/feedback",
        json={"feedback": None},
    )
    assert removed.status_code == 200
    with engine.connect() as conn:
        metadata = conn.execute(
            text("SELECT metadata FROM chat_messages WHERE id = :id"),
            {"id": message_id},
        ).scalar_one()
    assert "feedback" not in metadata
