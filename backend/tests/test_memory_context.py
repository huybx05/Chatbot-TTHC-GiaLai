from __future__ import annotations

from datetime import UTC, datetime

from backend.app.config import settings
from backend.app.memory.context import render_memory
from backend.app.memory.types import (
    MemoryTurn,
    ProcedureAnchor,
    SessionMemory,
    TopicRef,
)


def _memory(**overrides) -> SessionMemory:
    base = SessionMemory(
        summary="Người dùng đã hỏi về hồ sơ.",
        summary_through_message_id=None,
        recent_turns=[
            MemoryTurn(
                id="m1",
                role="user",
                content="Hồ sơ gồm gì?",
                procedure_code=None,
                outcome=None,
                options=[],
                created_at=datetime(2026, 10, 28, tzinfo=UTC),
            ),
            MemoryTurn(
                id="m2",
                role="assistant",
                content="Hồ sơ gồm đơn và giấy xác nhận.",
                procedure_code="1.001699",
                outcome="answered",
                options=[],
                created_at=datetime(2026, 10, 28, tzinfo=UTC),
            ),
        ],
        topics=[
            TopicRef(
                order=1,
                procedure_code="1.001699",
                procedure_name="Xác định mức độ khuyết tật",
                first_message_id="m2",
                last_message_id="m2",
            )
        ],
        active_procedure=ProcedureAnchor(
            code="1.001699",
            name="Xác định mức độ khuyết tật",
        ),
        last_clarify_options=[],
        last_outcome="answered",
        total_chars=100,
    )
    return SessionMemory(**{**base.__dict__, **overrides})


def test_render_memory_co_summary_anchor_va_cau_hoi_hien_tai() -> None:
    text = render_memory(_memory(), current_question="Còn lệ phí thì sao?")

    assert "[SESSION SUMMARY]" in text
    assert "[ACTIVE PROCEDURE]" in text
    assert "[RECENT TURNS]" in text
    assert "[CURRENT QUESTION]" in text
    assert text.index("[SESSION SUMMARY]") < text.index("[CURRENT QUESTION]")
    assert "Còn lệ phí thì sao?" in text


def test_render_memory_khong_vuot_budget() -> None:
    memory = _memory(summary="x" * 20_000)

    text = render_memory(memory, current_question="Câu hỏi hiện tại?")

    assert len(text) <= settings.memory_max_chars
    assert "Câu hỏi hiện tại?" in text


def test_render_memory_bo_recent_turns_cu_truoc() -> None:
    turns = []
    for index in range(20):
        turns.append(
            MemoryTurn(
                id=f"m{index}",
                role="user" if index % 2 == 0 else "assistant",
                content=f"nội dung {index} " + ("x" * 200),
                procedure_code=None,
                outcome=None,
                options=[],
                created_at=datetime(2026, 10, 28, tzinfo=UTC),
            )
        )

    text = render_memory(_memory(recent_turns=turns, summary=""), current_question="Mới?")

    assert len(text) <= settings.memory_max_chars
    assert "nội dung 19" in text
