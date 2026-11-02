"""Phiên khách ẩn danh: token cookie, TTL trượt và xoá theo yêu cầu."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from backend.app.config import settings
from backend.app.db.postgres import engine

router = APIRouter(prefix="/chat/guest-session", tags=["guest sessions"])

COOKIE_NAME = lambda: settings.guest_cookie_name  # noqa: E731
MAX_MESSAGES = 800


class GuestMessage(BaseModel):
    id: str
    session_id: str
    role: Literal["user", "assistant"]
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class GuestSessionResponse(BaseModel):
    session_id: str
    expires_at: datetime | None = None
    messages: list[GuestMessage] = Field(default_factory=list)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cleanup(conn) -> None:
    conn.execute(
        text(
            """
            UPDATE chat_sessions
               SET deleted_at = NOW()
             WHERE user_id IS NULL
               AND expires_at IS NOT NULL
               AND expires_at < NOW()
               AND deleted_at IS NULL
            """
        )
    )


def resolve_guest_session(request: Request) -> dict[str, Any] | None:
    """Trả session khách hợp lệ theo cookie; ``None`` nếu không có cookie."""
    token = request.cookies.get(COOKIE_NAME())
    if not token:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT id::text, title, expires_at
                  FROM chat_sessions
                 WHERE user_id IS NULL
                   AND guest_token_hash = :token_hash
                   AND expires_at > NOW()
                   AND deleted_at IS NULL
                """
            ),
            {"token_hash": _hash(token)},
        ).mappings().first()
    return dict(row) if row else None


def touch_guest_session(session_id: UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE chat_sessions
                   SET last_seen_at = NOW(),
                       expires_at = NOW() + (:ttl * INTERVAL '1 second'),
                       updated_at = NOW()
                 WHERE id = :session_id
                   AND user_id IS NULL
                   AND deleted_at IS NULL
                """
            ),
            {"session_id": session_id, "ttl": settings.guest_session_ttl_seconds},
        )


def delete_guest_session(session_id: UUID, token: str | None) -> None:
    with engine.begin() as conn:
        if token:
            conn.execute(
                text(
                    """
                    UPDATE chat_sessions
                       SET deleted_at = NOW()
                     WHERE id = :session_id
                       AND user_id IS NULL
                       AND guest_token_hash = :token_hash
                       AND deleted_at IS NULL
                    """
                ),
                {"session_id": session_id, "token_hash": _hash(token)},
            )


def _set_cookie(response: Response, token: str) -> None:
    # Cookie phiên (không Max-Age): server kiểm soát TTL 10 phút; đóng trình duyệt
    # cũng làm mất phiên, phù hợp phạm vi "một phiên khách".
    response.set_cookie(
        key=COOKIE_NAME(),
        value=token,
        httponly=True,
        secure=(
            settings.guest_cookie_secure
            or settings.app_env.lower() in {"production", "prod"}
        ),
        samesite="lax",
        path="/",
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME(), path="/")


@router.post("", response_model=GuestSessionResponse, status_code=status.HTTP_201_CREATED)
def create_guest_session(response: Response) -> GuestSessionResponse:
    token = secrets.token_urlsafe(32)
    with engine.begin() as conn:
        _cleanup(conn)
        row = conn.execute(
            text(
                """
                INSERT INTO chat_sessions (user_id, guest_token_hash, expires_at, last_seen_at)
                VALUES (NULL, :token_hash,
                        NOW() + (:ttl * INTERVAL '1 second'), NOW())
                RETURNING id::text, expires_at
                """
            ),
            {"token_hash": _hash(token), "ttl": settings.guest_session_ttl_seconds},
        ).mappings().one()
    _set_cookie(response, token)
    return GuestSessionResponse(session_id=row["id"], expires_at=row["expires_at"])


@router.get("", response_model=GuestSessionResponse)
def get_guest_session(request: Request) -> GuestSessionResponse:
    session = resolve_guest_session(request)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không có phiên khách.")
    session_id = UUID(session["id"])
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE chat_sessions
                   SET last_seen_at = NOW(),
                       expires_at = NOW() + (:ttl * INTERVAL '1 second')
                 WHERE id = :session_id AND user_id IS NULL
                """
            ),
            {"session_id": session_id, "ttl": settings.guest_session_ttl_seconds},
        )
        rows = conn.execute(
            text(
                """
                SELECT id::text, session_id::text, role, content, metadata, created_at
                  FROM chat_messages
                 WHERE session_id = :session_id
                 ORDER BY created_at, id
                 LIMIT :limit
                """
            ),
            {"session_id": session_id, "limit": MAX_MESSAGES},
        ).mappings().all()
    return GuestSessionResponse(
        session_id=str(session_id),
        expires_at=session["expires_at"],
        messages=[GuestMessage.model_validate(dict(row)) for row in rows],
    )


@router.delete("")
def delete_current_guest_session(request: Request, response: Response) -> dict[str, bool]:
    session = resolve_guest_session(request)
    if session is not None:
        delete_guest_session(UUID(session["id"]), request.cookies.get(COOKIE_NAME()))
    _clear_cookie(response)
    return {"deleted": True}


def cleanup_expired_guest_sessions() -> None:
    with engine.begin() as conn:
        _cleanup(conn)
