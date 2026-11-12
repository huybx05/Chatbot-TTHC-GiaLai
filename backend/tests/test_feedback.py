from __future__ import annotations

from io import BytesIO
from uuid import UUID

from openpyxl import load_workbook
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


def test_admin_can_export_filtered_conversations() -> None:
    created = client.post("/chat/guest-session")
    session_id = UUID(created.json()["session_id"])
    persist_chat_message(
        session_id=session_id,
        user_id=None,
        role="user",
        content="Câu hỏi để xuất Excel.",
        guest=True,
    )
    persist_chat_message(
        session_id=session_id,
        user_id=None,
        role="assistant",
        content="Câu trả lời để xuất Excel.",
        metadata={
            "status": "answered",
            "source": "fact_lookup",
            "procedure": {"procedure_code": "1.001699", "procedure_name": "Thủ tục thử"},
            "citations": [{"title": "Thủ tục thử", "section": "Hồ sơ", "url": "https://example.test"}],
            "ttft_ms": 120,
            "total_ms": 450,
        },
        guest=True,
    )

    response = client.get("/api/admin/conversations/export?date_range=today&source=fact_lookup")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    sheet = load_workbook(BytesIO(response.content)).active
    assert [cell.value for cell in sheet[1]][:4] == ["STT", "Mã hội thoại", "Thời gian", "Người dùng"]
    assert any(row[4] == "Câu hỏi để xuất Excel." for row in sheet.iter_rows(min_row=2, values_only=True))
