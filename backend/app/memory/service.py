"""Chọn nguồn memory cho một request chat.

- Có ``session_id`` + user: đọc từ PostgreSQL qua Memory Reader.
- Không có session: dùng history client gửi lên (guest), có giới hạn.
- Không có gì: memory rỗng.

Phase 3 chỉ nạp memory; resolver/rewrite dùng memory ở phase sau.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from backend.app.config import settings
from backend.app.db.postgres import engine
from backend.app.memory.reader import load_session_memory
from backend.app.memory.repository import update_preferred_name
from backend.app.memory.summarizer import maybe_summarize
from backend.app.memory.types import (
    MemoryTurn,
    ProcedureAnchor,
    SessionMemory,
    TopicRef,
)
from backend.app.rag.grounding import CODE_PATTERN

logger = logging.getLogger(__name__)


def empty_memory() -> SessionMemory:
    return SessionMemory(
        summary="",
        summary_through_message_id=None,
        recent_turns=[],
        topics=[],
        active_procedure=None,
        last_clarify_options=[],
        last_outcome="",
        total_chars=0,
    )


def memory_from_history(
    history: Iterable[Mapping[str, Any]],
) -> SessionMemory:
    """Dựng memory tạm cho guest từ history client; không có topic ledger."""
    turns: list[MemoryTurn] = []
    inferred_codes: list[str] = []
    provided_codes: list[str] = []
    for index, item in enumerate(list(history)[-settings.memory_recent_messages :]):
        role = str(item.get("role") or "")
        if role not in {"user", "assistant"}:
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        provided_code = str(item.get("procedure_code") or "").strip()
        if provided_code and provided_code not in provided_codes:
            provided_codes.append(provided_code)
        if role == "assistant":
            for match in CODE_PATTERN.findall(content):
                code = match.replace(",", ".")
                if code not in inferred_codes:
                    inferred_codes.append(code)
        turns.append(
            MemoryTurn(
                id=f"history-{index}",
                role=role,  # type: ignore[arg-type]
                content=content[: settings.memory_message_max_chars],
                procedure_code=None,
                outcome=None,
                options=[],
                created_at=datetime.now(UTC),
            )
        )

    # Client biết mã của lượt trước thì mã đó là nguồn tin cậy hơn mã suy ra từ
    # nội dung câu trả lời (câu trả lời có thể nhắc nhiều thủ tục).
    codes = provided_codes or inferred_codes
    topics = [
        TopicRef(
            order=index + 1,
            procedure_code=code,
            procedure_name=code,
            first_message_id="",
            last_message_id="",
        )
        for index, code in enumerate(codes)
    ]
    active = (
        ProcedureAnchor(code=codes[-1], name=codes[-1])
        if codes
        else None
    )
    return SessionMemory(
        summary="",
        summary_through_message_id=None,
        recent_turns=turns,
        topics=topics,
        active_procedure=active,
        last_clarify_options=[],
        last_outcome="",
        total_chars=sum(len(turn.content) for turn in turns),
    )


async def load_chat_memory(
    *,
    user_id: int | None,
    session_id: UUID | None,
    current_message_id: UUID | None,
    history: Iterable[Mapping[str, Any]] = (),
    allow_guest: bool = False,
) -> SessionMemory | None:
    """Trả memory theo session hoặc history guest.

    Với session: chỉ đọc memory hiện có. Tóm tắt chạy nền sau khi đã trả
    lời để không làm chậm lượt hỏi. Với guest: dựng memory tạm từ history client.

    ``None`` chỉ có nghĩa session không tồn tại/không thuộc user;
    endpoint chịu trách nhiệm đổi thành 401/404.
    """
    if not settings.memory_enabled:
        return empty_memory()

    if session_id is None:
        return memory_from_history(history) if history else empty_memory()

    if user_id is None and not allow_guest:
        return None

    with engine.connect() as conn:
        return load_session_memory(
            conn,
            user_id=user_id,
            session_id=session_id,
            current_message_id=current_message_id,
        )


async def save_preferred_name(session_id: UUID, preferred_name: str | None) -> None:
    """Lưu tên tự giới thiệu theo phiên; không đụng user profile."""
    await asyncio.to_thread(_save_preferred_name_sync, session_id, preferred_name)


def _save_preferred_name_sync(session_id: UUID, preferred_name: str | None) -> None:
    with engine.begin() as conn:
        update_preferred_name(conn, session_id, preferred_name)


async def summarize_session_memory(session_id: UUID) -> bool:
    """Tóm tắt nền sau khi assistant message của một session đã được lưu."""
    if not settings.memory_enabled:
        return False

    try:
        with engine.connect() as conn:
            return await maybe_summarize(conn, session_id=session_id)
    except Exception:  # noqa: BLE001
        logger.exception("Không tóm tắt được memory của session %s", session_id)
        return False
