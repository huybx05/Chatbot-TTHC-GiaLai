"""Đọc bộ nhớ ngắn hạn của một phiên từ PostgreSQL.

Phase 2 chỉ đọc:
- 2–3 cặp Q/A gần nhất trước câu hỏi hiện tại;
- summary + checkpoint;
- topic ledger có thứ tự;
- anchor thủ tục và lựa chọn hỏi lại gần nhất.

Không ghi memory, không tóm tắt, không resolve câu hỏi.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from backend.app.config import settings
from backend.app.memory.repository import load_memory_row
from backend.app.memory.topics import derive_topics, merge_topics, procedure_for_memory
from backend.app.memory.types import (
    MemoryTurn,
    ProcedureAnchor,
    SessionMemory,
    TopicRef,
)


def _as_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _procedure_code(metadata: Any) -> str | None:
    found = procedure_for_memory(metadata)
    return found[0] if found is not None else None


def _options(metadata: Any) -> list[dict[str, Any]]:
    data = _as_metadata(metadata)
    options = data.get("options")
    if not isinstance(options, list):
        return []
    return [option for option in options if isinstance(option, dict)]


def _truncate(content: str) -> str:
    limit = settings.memory_message_max_chars
    if len(content) <= limit:
        return content
    return content[: max(0, limit - 1)] + "…"


def _turn(row: Mapping[str, Any]) -> MemoryTurn:
    role = str(row["role"])
    if role not in {"user", "assistant"}:
        role = "assistant"
    metadata = row.get("metadata")
    return MemoryTurn(
        id=str(row["id"]),
        role=role,  # type: ignore[arg-type]
        content=_truncate(str(row.get("content") or "")),
        procedure_code=_procedure_code(metadata) if role == "assistant" else None,
        outcome=str(_as_metadata(metadata).get("status") or "") or None,
        options=_options(metadata) if role == "assistant" else [],
        created_at=row["created_at"],
    )


def _complete_pairs(
    messages: Iterable[Mapping[str, Any]],
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    """Chỉ giữ cặp user → assistant hoàn chỉnh, theo đúng thứ tự."""
    pairs: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    pending_user: Mapping[str, Any] | None = None

    for message in messages:
        role = str(message.get("role") or "")
        if role == "user":
            pending_user = message
        elif role == "assistant" and pending_user is not None:
            pairs.append((pending_user, message))
            pending_user = None

    return pairs


def _load_recent_messages(
    conn: Connection,
    *,
    session_id: UUID,
    current_message_id: UUID | None,
) -> list[Mapping[str, Any]]:
    current = None
    if current_message_id is not None:
        current = conn.execute(
            text(
                """
                SELECT created_at, id
                  FROM chat_messages
                 WHERE id = :current_message_id
                   AND session_id = :session_id
                """
            ),
            {
                "current_message_id": current_message_id,
                "session_id": session_id,
            },
        ).mappings().first()

    where_current = ""
    params: dict[str, Any] = {
        "session_id": session_id,
        "limit": settings.memory_recent_messages * 2,
    }
    if current is not None:
        where_current = (
            "AND (created_at, id) < (:current_created_at, :current_message_id)"
        )
        params["current_created_at"] = current["created_at"]
        params["current_message_id"] = current_message_id

    rows = conn.execute(
        text(
            f"""
            SELECT id::text AS id, role, content, metadata, created_at
              FROM chat_messages
             WHERE session_id = :session_id
               {where_current}
             ORDER BY created_at DESC, id DESC
             LIMIT :limit
            """
        ),
        params,
    ).mappings().all()

    return list(reversed(rows))


def _load_topic_messages(
    conn: Connection,
    *,
    session_id: UUID,
) -> list[Mapping[str, Any]]:
    return conn.execute(
        text(
            """
            SELECT id::text AS id, role, metadata, created_at
              FROM chat_messages
             WHERE session_id = :session_id
               AND role = 'assistant'
             ORDER BY created_at ASC, id ASC
            """
        ),
        {"session_id": session_id},
    ).mappings().all()


def _stored_topics(row: Mapping[str, Any] | None) -> list[TopicRef]:
    if row is None:
        return []

    result: list[TopicRef] = []
    for item in row.get("topics") or []:
        if not isinstance(item, dict):
            continue
        code = str(item.get("procedure_code") or "").strip()
        if not code:
            continue
        result.append(
            TopicRef(
                order=int(item.get("order") or len(result) + 1),
                procedure_code=code,
                procedure_name=str(item.get("procedure_name") or code),
                first_message_id=str(item.get("first_message_id") or ""),
                last_message_id=str(item.get("last_message_id") or ""),
            )
        )
    return sorted(result, key=lambda topic: topic.order)


def _active_procedure(
    recent_turns: list[MemoryTurn],
    topics: list[TopicRef],
) -> ProcedureAnchor | None:
    for turn in reversed(recent_turns):
        if turn.role != "assistant" or not turn.procedure_code:
            continue
        topic = next(
            (
                item
                for item in topics
                if item.procedure_code == turn.procedure_code
            ),
            None,
        )
        return ProcedureAnchor(
            code=turn.procedure_code,
            name=topic.procedure_name if topic else turn.procedure_code,
        )
    if topics:
        last = topics[-1]
        return ProcedureAnchor(code=last.procedure_code, name=last.procedure_name)
    return None


def load_session_memory(
    conn: Connection,
    *,
    user_id: int | None,
    session_id: UUID,
    current_message_id: UUID | None = None,
) -> SessionMemory | None:
    """Đọc memory của session; ``None`` nếu session không thuộc chủ sở hữu."""
    owned = conn.execute(
        text(
            """
            SELECT 1
              FROM chat_sessions
             WHERE id = :session_id
               AND deleted_at IS NULL
               AND (
                    (CAST(:user_id AS BIGINT) IS NOT NULL
                     AND user_id = CAST(:user_id AS BIGINT))
                    OR (CAST(:user_id AS BIGINT) IS NULL AND user_id IS NULL)
               )
            """
        ),
        {"session_id": session_id, "user_id": user_id},
    ).first()
    if owned is None:
        return None

    memory_row = load_memory_row(conn, session_id)
    summary = str(memory_row.get("summary") or "") if memory_row else ""
    preferred_name = (
        str(memory_row.get("preferred_name") or "").strip() or None
        if memory_row
        else None
    )
    checkpoint = (
        memory_row.get("summary_through_message_id") if memory_row else None
    )

    recent_messages = _load_recent_messages(
        conn,
        session_id=session_id,
        current_message_id=current_message_id,
    )
    pairs = _complete_pairs(recent_messages)
    max_pairs = max(1, settings.memory_recent_messages // 2)
    recent_turns = [
        _turn(message)
        for pair in pairs[-max_pairs:]
        for message in pair
    ]

    discovered = derive_topics(
        _load_topic_messages(conn, session_id=session_id)
    )
    allowed_codes = {topic.procedure_code for topic in discovered}
    stored = [
        topic
        for topic in _stored_topics(memory_row)
        if topic.procedure_code in allowed_codes
    ]
    topics = merge_topics(stored, discovered)

    last_assistant = next(
        (turn for turn in reversed(recent_turns) if turn.role == "assistant"),
        None,
    )
    last_outcome = last_assistant.outcome if last_assistant else ""
    last_clarify_options = (
        last_assistant.options
        if last_assistant is not None and last_assistant.outcome == "clarify"
        else []
    )
    total_chars = len(summary) + sum(
        len(turn.content) for turn in recent_turns
    )

    return SessionMemory(
        summary=summary,
        summary_through_message_id=(
            str(checkpoint) if checkpoint is not None else None
        ),
        recent_turns=recent_turns,
        topics=topics,
        active_procedure=_active_procedure(recent_turns, topics),
        last_clarify_options=last_clarify_options,
        last_outcome=last_outcome,
        total_chars=total_chars,
        session_id=str(session_id),
        user_id=user_id,
        preferred_name=preferred_name,
    )


def load_topic_turns(
    conn: Connection,
    *,
    user_id: int,
    session_id: UUID,
    procedure_code: str,
    limit_pairs: int = 2,
) -> list[MemoryTurn]:
    """Kéo lại tối đa ``limit_pairs`` cặp Q/A cũ của một thủ tục.

    Dùng khi người dùng quay lại topic trước đó; topic ledger đã có mã,
    nhưng cửa sổ recent không còn nội dung cũ.
    """
    code = procedure_code.strip()
    if not code:
        return []

    owned = conn.execute(
        text(
            """
            SELECT 1
              FROM chat_sessions
             WHERE id = :session_id
               AND user_id = :user_id
               AND deleted_at IS NULL
            """
        ),
        {"session_id": session_id, "user_id": user_id},
    ).first()
    if owned is None:
        return []

    keep = max(1, limit_pairs)
    rows = conn.execute(
        text(
            """
            WITH selected_assistants AS (
                SELECT id, role, content, metadata, created_at
                  FROM chat_messages
                 WHERE session_id = :session_id
                   AND role = 'assistant'
                   AND metadata -> 'procedure' ->> 'procedure_code' = :procedure_code
                   AND metadata ->> 'status' = 'answered'
                   AND (metadata -> 'memory_eligible') IS DISTINCT FROM 'false'::jsonb
                 ORDER BY created_at DESC, id DESC
                 LIMIT :limit_pairs
            ), recalled_messages AS (
                SELECT user_message.id::text AS id,
                       user_message.role,
                       user_message.content,
                       user_message.metadata,
                       user_message.created_at
                  FROM selected_assistants assistant
                  JOIN LATERAL (
                      SELECT id, role, content, metadata, created_at
                        FROM chat_messages
                       WHERE session_id = :session_id
                         AND role = 'user'
                         AND (created_at, id) < (assistant.created_at, assistant.id)
                       ORDER BY created_at DESC, id DESC
                       LIMIT 1
                  ) AS user_message ON TRUE
                UNION ALL
                SELECT id::text AS id, role, content, metadata, created_at
                  FROM selected_assistants
            )
            SELECT id, role, content, metadata, created_at
              FROM recalled_messages
             ORDER BY created_at ASC, id ASC
            """
        ),
        {
            "session_id": session_id,
            "procedure_code": code,
            "limit_pairs": keep,
        },
    ).mappings().all()

    return [
        _turn(message)
        for pair in _complete_pairs(rows)
        for message in pair
    ]
