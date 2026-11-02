from __future__ import annotations

import json
from collections.abc import Generator
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.auth.dependencies import CurrentUser
from backend.app.db.postgres import engine

router = APIRouter(prefix="/chat-sessions", tags=["chat sessions"])

#: Tiêu đề mặc định khi tạo phiên. Khi tin nhắn đầu tiên là của người dùng,
#: tiêu đề được thay bằng nội dung câu hỏi (xem `_title_from_content`).
DEFAULT_TITLE = "Cuộc trò chuyện mới"
MAX_MESSAGE_CONTENT = 20_000
MAX_MESSAGES_PER_SESSION = 500


def get_connection() -> Generator[Connection, None, None]:
    with engine.connect() as conn:
        yield conn


DBConn = Annotated[Connection, Depends(get_connection)]


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    is_pinned: bool
    message_count: int = 0
    created_at: datetime
    updated_at: datetime


class ChatSessionListResponse(BaseModel):
    items: list[ChatSessionResponse]


class RenameChatSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        title = value.strip()

        if not 1 <= len(title) <= 120:
            raise ValueError("Tên cuộc trò chuyện phải có từ 1 đến 120 ký tự.")

        return title


class PinChatSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_pinned: bool


class ChatMessageResponse(BaseModel):
    id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ChatMessageListResponse(BaseModel):
    items: list[ChatMessageResponse]


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Không tìm thấy cuộc trò chuyện.",
    )


#: Một cuộc trò chuyện kèm số tin nhắn. Dùng chung cho mọi endpoint để response
#: luôn có `message_count` nhất quán, không phải đếm lại ở phía giao diện.
_SESSION_SELECT = """
    SELECT
        s.id::text AS id,
        s.title,
        s.is_pinned,
        s.created_at,
        s.updated_at,
        (
            SELECT count(*)
              FROM chat_messages m
             WHERE m.session_id = s.id
        ) AS message_count
      FROM chat_sessions s
     WHERE s.id = :session_id
       AND s.user_id = :user_id
       AND s.deleted_at IS NULL
"""


def _session_row(
    conn: Connection,
    session_id: UUID,
    user_id: int | None,
    *,
    for_update: bool = False,
    guest: bool = False,
) -> Any:
    sql = _SESSION_SELECT + (" FOR UPDATE" if for_update else "")
    if guest:
        sql = sql.replace("AND s.user_id = :user_id", "AND s.user_id IS NULL")
    row = conn.execute(
        text(sql),
        {"session_id": session_id, "user_id": user_id},
    ).mappings().first()
    if row is None:
        raise _not_found()
    return row


def _session_response(row: Any) -> ChatSessionResponse:
    return ChatSessionResponse.model_validate(dict(row))


def _message_response(row: Any) -> ChatMessageResponse:
    return ChatMessageResponse.model_validate(dict(row))


def _title_from_content(content: str) -> str:
    text_value = " ".join(content.split())
    if len(text_value) <= 48:
        return text_value
    return text_value[:47].rstrip() + "…"


def persist_chat_message(
    *,
    session_id: UUID,
    user_id: int | None,
    role: Literal["user", "assistant"],
    content: str,
    metadata: dict[str, Any] | None = None,
    guest: bool = False,
) -> str:
    """Lưu message do chính backend tạo; không mở endpoint ghi trực tiếp cho client."""
    clean_content = content.strip()
    if not 1 <= len(clean_content) <= MAX_MESSAGE_CONTENT:
        raise ValueError(
            f"Nội dung tin nhắn phải có từ 1 đến {MAX_MESSAGE_CONTENT} ký tự."
        )

    with engine.begin() as conn:
        session = _session_row(conn, session_id, user_id, for_update=True, guest=guest)
        next_title = session["title"]
        if role == "user" and next_title == DEFAULT_TITLE:
            next_title = _title_from_content(clean_content)

        conn.execute(
            text(
                """
                UPDATE chat_sessions
                   SET title = :title,
                       updated_at = NOW()
                 WHERE id = :session_id
                   AND (
                        (CAST(:user_id AS BIGINT) IS NOT NULL
                         AND user_id = CAST(:user_id AS BIGINT))
                        OR (CAST(:user_id AS BIGINT) IS NULL AND user_id IS NULL)
                   )
                """
            ),
            {
                "title": next_title,
                "session_id": session_id,
                "user_id": user_id,
            },
        )
        message_id = conn.execute(
            text(
                """
                INSERT INTO chat_messages (session_id, role, content, metadata)
                VALUES (:session_id, :role, :content, CAST(:metadata AS JSONB))
                RETURNING id::text
                """
            ),
            {
                "session_id": session_id,
                "role": role,
                "content": clean_content,
                "metadata": json.dumps(metadata or {}, ensure_ascii=False),
            },
        ).scalar_one()
    return str(message_id)


@router.get("", response_model=ChatSessionListResponse)
def list_chat_sessions(
    user: CurrentUser,
    conn: DBConn,
) -> ChatSessionListResponse:
    rows = conn.execute(
        text(
            """
            SELECT
                s.id::text AS id,
                s.title,
                s.is_pinned,
                s.created_at,
                s.updated_at,
                (
                    SELECT count(*)
                      FROM chat_messages m
                     WHERE m.session_id = s.id
                ) AS message_count
              FROM chat_sessions s
             WHERE s.user_id = :user_id
               AND s.deleted_at IS NULL
             ORDER BY s.is_pinned DESC, s.updated_at DESC
             LIMIT 100
            """
        ),
        {"user_id": user["id"]},
    ).mappings().all()

    return ChatSessionListResponse(
        items=[_session_response(row) for row in rows],
    )


@router.post("", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
def create_chat_session(
    user: CurrentUser,
    conn: DBConn,
) -> ChatSessionResponse:
    session_id = conn.execute(
        text(
            """
            INSERT INTO chat_sessions (user_id)
            VALUES (:user_id)
            RETURNING id
            """
        ),
        {"user_id": user["id"]},
    ).scalar_one()

    conn.commit()
    row = _session_row(conn, session_id, user["id"])
    return _session_response(row)


@router.patch("/{session_id}", response_model=ChatSessionResponse)
def rename_chat_session(
    session_id: UUID,
    payload: RenameChatSessionRequest,
    user: CurrentUser,
    conn: DBConn,
) -> ChatSessionResponse:
    updated = conn.execute(
        text(
            """
            UPDATE chat_sessions
            SET title = :title,
                updated_at = NOW()
            WHERE id = :session_id
              AND user_id = :user_id
              AND deleted_at IS NULL
            RETURNING id
            """
        ),
        {
            "title": payload.title,
            "session_id": session_id,
            "user_id": user["id"],
        },
    ).first()

    if updated is None:
        conn.rollback()
        raise _not_found()

    conn.commit()
    return _session_response(_session_row(conn, session_id, user["id"]))


@router.patch("/{session_id}/pin", response_model=ChatSessionResponse)
def pin_chat_session(
    session_id: UUID,
    payload: PinChatSessionRequest,
    user: CurrentUser,
    conn: DBConn,
) -> ChatSessionResponse:
    updated = conn.execute(
        text(
            """
            UPDATE chat_sessions
            SET is_pinned = :is_pinned,
                updated_at = NOW()
            WHERE id = :session_id
              AND user_id = :user_id
              AND deleted_at IS NULL
            RETURNING id
            """
        ),
        {
            "is_pinned": payload.is_pinned,
            "session_id": session_id,
            "user_id": user["id"],
        },
    ).first()

    if updated is None:
        conn.rollback()
        raise _not_found()

    conn.commit()
    return _session_response(_session_row(conn, session_id, user["id"]))


@router.delete("/{session_id}")
def delete_chat_session(
    session_id: UUID,
    user: CurrentUser,
    conn: DBConn,
) -> dict[str, bool]:
    row = conn.execute(
        text(
            """
            UPDATE chat_sessions
               SET deleted_at = NOW()
             WHERE id = :session_id
               AND user_id = :user_id
               AND deleted_at IS NULL
            RETURNING id
            """
        ),
        {
            "session_id": session_id,
            "user_id": user["id"],
        },
    ).first()

    if row is None:
        conn.rollback()
        raise _not_found()

    conn.commit()
    return {"deleted": True}


@router.get("/{session_id}/messages", response_model=ChatMessageListResponse)
def list_chat_messages(
    session_id: UUID,
    user: CurrentUser,
    conn: DBConn,
) -> ChatMessageListResponse:
    _session_row(conn, session_id, user["id"])

    rows = conn.execute(
        text(
            """
            SELECT
                id::text AS id,
                session_id::text AS session_id,
                role,
                content,
                metadata,
                created_at
              FROM chat_messages
             WHERE session_id = :session_id
             ORDER BY created_at ASC, id ASC
             LIMIT :limit
            """
        ),
        {"session_id": session_id, "limit": MAX_MESSAGES_PER_SESSION},
    ).mappings().all()

    return ChatMessageListResponse(
        items=[_message_response(row) for row in rows],
    )


