"""Feedback cho từng câu trả lời của trợ lý."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

from backend.app.api.guest_sessions import resolve_guest_session
from backend.app.auth.dependencies import OptionalUser
from backend.app.db.postgres import engine

router = APIRouter(tags=["feedback"])


class AnswerFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback: Literal["like", "dislike"] | None
    reasons: list[str] = Field(default_factory=list, max_length=8)
    comment: str = Field(default="", max_length=1000)


@router.post("/chat/messages/{message_id}/feedback")
def update_answer_feedback(
    message_id: UUID,
    payload: AnswerFeedbackRequest,
    request: Request,
    user: OptionalUser,
) -> dict[str, Any]:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT m.session_id, s.user_id
                  FROM chat_messages m
                  JOIN chat_sessions s ON s.id = m.session_id
                 WHERE m.id = :message_id
                   AND m.role = 'assistant'
                """
            ),
            {"message_id": message_id},
        ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy câu trả lời.")

    session_id = row["session_id"]
    owner_id = row["user_id"]
    if owner_id is None:
        guest = resolve_guest_session(request)
        if guest is None or str(guest["id"]) != str(session_id):
            raise HTTPException(status_code=401, detail="Phiên khách đã hết hạn hoặc không hợp lệ.")
    elif user is None or int(user["id"]) != int(owner_id):
        raise HTTPException(status_code=403, detail="Bạn không có quyền đánh giá câu trả lời này.")

    with engine.begin() as conn:
        if payload.feedback is None:
            conn.execute(
                text(
                    """
                    UPDATE chat_messages
                       SET metadata = COALESCE(metadata, '{}'::jsonb) - 'feedback'
                     WHERE id = :message_id
                    """
                ),
                {"message_id": message_id},
            )
        else:
            feedback = {
                "value": payload.feedback,
                "reasons": [reason.strip()[:200] for reason in payload.reasons if reason.strip()],
                "comment": payload.comment.strip()[:1000],
                "updated_at": datetime.now(UTC).isoformat(),
            }
            conn.execute(
                text(
                    """
                    UPDATE chat_messages
                       SET metadata = jsonb_set(
                           COALESCE(metadata, '{}'::jsonb),
                           '{feedback}',
                           CAST(:feedback AS jsonb),
                           true
                       )
                     WHERE id = :message_id
                    """
                ),
                {"message_id": message_id, "feedback": json.dumps(feedback, ensure_ascii=False)},
            )

    return {"message_id": str(message_id), "feedback": payload.feedback}
