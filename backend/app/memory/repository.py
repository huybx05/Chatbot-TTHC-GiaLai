"""Truy vấn bảng bộ nhớ ngắn hạn theo phiên.

Phase 1 chỉ lo phần lưu trữ cơ bản:
- bảo đảm mỗi session có đúng một row;
- đọc summary/checkpoint/topics;
- cập nhật summary và topic ledger.

Việc dựng context, tóm tắt và resolve follow-up thuộc các phase sau.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection


def ensure_memory_row(conn: Connection, session_id: UUID) -> None:
    """Tạo row memory rỗng nếu session chưa có; gọi lặp lại vẫn an toàn."""
    conn.execute(
        text(
            """
            INSERT INTO chat_session_memory (session_id)
            VALUES (:session_id)
            ON CONFLICT (session_id) DO NOTHING
            """
        ),
        {"session_id": session_id},
    )


def load_memory_row(conn: Connection, session_id: UUID) -> dict[str, Any] | None:
    """Đọc memory của một session; ``None`` nếu chưa có row."""
    row = conn.execute(
        text(
            """
            SELECT
                session_id::text AS session_id,
                summary,
                summary_through_message_id::text AS summary_through_message_id,
                topics,
                preferred_name,
                created_at,
                updated_at
              FROM chat_session_memory
             WHERE session_id = :session_id
            """
        ),
        {"session_id": session_id},
    ).mappings().first()

    if row is None:
        return None

    data = dict(row)
    topics = data.get("topics")
    if isinstance(topics, str):
        topics = json.loads(topics)
    data["topics"] = topics or []
    return data


def update_summary(
    conn: Connection,
    session_id: UUID,
    *,
    summary: str,
    through_message_id: UUID | None,
) -> None:
    """Lưu summary và checkpoint message cuối đã tóm tắt."""
    conn.execute(
        text(
            """
            UPDATE chat_session_memory
               SET summary = :summary,
                   summary_through_message_id = :through_message_id,
                   updated_at = NOW()
             WHERE session_id = :session_id
            """
        ),
        {
            "session_id": session_id,
            "summary": summary,
            "through_message_id": through_message_id,
        },
    )


def update_topics(
    conn: Connection,
    session_id: UUID,
    topics: list[dict[str, Any]],
) -> None:
    """Thay topic ledger bằng danh sách mới; caller chịu trách nhiệm thứ tự."""
    conn.execute(
        text(
            """
            UPDATE chat_session_memory
               SET topics = CAST(:topics AS JSONB),
                   updated_at = NOW()
             WHERE session_id = :session_id
            """
        ),
        {
            "session_id": session_id,
            "topics": json.dumps(topics, ensure_ascii=False),
        },
    )


def update_preferred_name(
    conn: Connection,
    session_id: UUID,
    preferred_name: str | None,
) -> None:
    """Lưu tên người dùng tự giới thiệu; ``None`` để xoá."""
    ensure_memory_row(conn, session_id)
    conn.execute(
        text(
            """
            UPDATE chat_session_memory
               SET preferred_name = :preferred_name,
                   updated_at = NOW()
             WHERE session_id = :session_id
            """
        ),
        {"session_id": session_id, "preferred_name": preferred_name},
    )
