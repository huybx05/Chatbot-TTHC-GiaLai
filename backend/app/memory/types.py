"""Kiểu dữ liệu cho bộ nhớ ngắn hạn theo phiên."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass(frozen=True)
class ProcedureAnchor:
    code: str
    name: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "name": self.name}


@dataclass(frozen=True)
class TopicRef:
    order: int
    procedure_code: str
    procedure_name: str
    first_message_id: str
    last_message_id: str


@dataclass(frozen=True)
class MemoryTurn:
    id: str
    role: Literal["user", "assistant"]
    content: str
    procedure_code: str | None
    outcome: str | None
    options: list[dict[str, Any]]
    created_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "procedure_code": self.procedure_code,
            "outcome": self.outcome,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class SessionMemory:
    summary: str
    summary_through_message_id: str | None
    recent_turns: list[MemoryTurn]
    topics: list[TopicRef]
    active_procedure: ProcedureAnchor | None
    last_clarify_options: list[dict[str, Any]]
    last_outcome: str
    total_chars: int
    #: Lượt cũ được kéo lại khi người dùng quay về một topic trước đó.
    recalled_turns: list[MemoryTurn] = field(default_factory=list)
    #: Định danh phiên/user để tầng graph có thể recall đúng phạm vi.
    session_id: str | None = None
    user_id: int | None = None
    #: Tên người dùng tự giới thiệu trong phiên; chỉ dùng để xưng hô.
    preferred_name: str | None = None

    def is_empty(self) -> bool:
        return not (
            self.summary
            or self.recent_turns
            or self.topics
            or self.recalled_turns
        )

    def to_dict(self) -> dict[str, Any]:
        """Bản rút gọn để đưa vào state/trace; không chứa toàn bộ lịch sử."""
        return {
            "summary": self.summary,
            "summary_through_message_id": self.summary_through_message_id,
            "recent_turns": [
                {
                    "id": turn.id,
                    "role": turn.role,
                    "content": turn.content,
                    "procedure_code": turn.procedure_code,
                    "outcome": turn.outcome,
                    "created_at": turn.created_at.isoformat(),
                }
                for turn in self.recent_turns
            ],
            "topics": [
                {
                    "order": topic.order,
                    "procedure_code": topic.procedure_code,
                    "procedure_name": topic.procedure_name,
                    "first_message_id": topic.first_message_id,
                    "last_message_id": topic.last_message_id,
                }
                for topic in self.topics
            ],
            "recalled_turns": [
                {
                    "id": turn.id,
                    "role": turn.role,
                    "content": turn.content,
                    "procedure_code": turn.procedure_code,
                    "outcome": turn.outcome,
                    "created_at": turn.created_at.isoformat(),
                }
                for turn in self.recalled_turns
            ],
            "active_procedure": (
                {"code": self.active_procedure.code, "name": self.active_procedure.name}
                if self.active_procedure
                else None
            ),
            "last_clarify_options": self.last_clarify_options,
            "last_outcome": self.last_outcome,
            "total_chars": self.total_chars,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "preferred_name": self.preferred_name,
        }
