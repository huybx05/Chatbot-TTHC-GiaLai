"""Dựng context memory có giới hạn ký tự để đưa vào prompt.

Thứ tự cố ý:
1. Summary (thông tin cũ, đã nén)
2. Active procedure (neo thủ tục)
3. Recent turns (mạch gần)
4. Current question (cuối cùng)

Khi vượt budget, bỏ các cặp cũ nhất trước; giữ summary, anchor và câu hỏi hiện tại.
"""

from __future__ import annotations

from backend.app.config import settings
from backend.app.memory.types import MemoryTurn, SessionMemory


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _recent_block(turns: list[MemoryTurn]) -> str:
    lines = ["[RECENT TURNS]"]
    for turn in turns:
        label = "User" if turn.role == "user" else "Assistant"
        lines.append(f"{label}: {turn.content}")
    return "\n".join(lines)


def _render(
    memory: SessionMemory,
    *,
    summary: str,
    recent: list[MemoryTurn],
    current_question: str,
) -> str:
    blocks: list[str] = []
    if summary:
        blocks.append("[SESSION SUMMARY]\n" + summary)

    if memory.active_procedure is not None:
        blocks.append(
            "[ACTIVE PROCEDURE]\n"
            f"Mã: {memory.active_procedure.code}\n"
            f"Tên: {memory.active_procedure.name}"
        )

    if recent:
        blocks.append(_recent_block(recent))

    blocks.append("[CURRENT QUESTION]\n" + current_question)
    return "\n\n".join(blocks)


def render_memory(memory: SessionMemory, current_question: str) -> str:
    """Trả context memory đã cắt theo ``memory_max_chars``."""
    summary = _clip(memory.summary.strip(), settings.memory_summary_max_chars)
    recent = [*memory.recalled_turns, *memory.recent_turns]

    while True:
        text = _render(
            memory,
            summary=summary,
            recent=recent,
            current_question=current_question,
        )
        if len(text) <= settings.memory_max_chars:
            return text

        if recent:
            # Bỏ cặp cũ nhất; nếu dữ liệu lệch vai, bỏ một message.
            drop = 2 if recent[0].role == "user" and len(recent) > 1 else 1
            recent = recent[drop:]
            continue

        # Không còn recent để bỏ; cắt summary nếu vẫn vượt.
        if summary:
            excess = len(text) - settings.memory_max_chars
            summary = _clip(summary, max(0, len(summary) - excess - 1))
            continue

        # Câu hỏi hiện tại là phần bắt buộc cuối cùng.
        return text
