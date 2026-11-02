from __future__ import annotations

import asyncio

from backend.app.workflow import answer as answer_module
from backend.app.workflow import graph
from backend.app.workflow.state import Outcome, new_state


def test_new_state_co_memory_rong() -> None:
    state = new_state("Thủ tục này cần gì?")

    assert state["memory"] == {}


def test_new_state_khong_lam_hong_json() -> None:
    state = new_state("Thủ tục này cần gì?")
    state["memory"] = {
        "active_procedure": {"code": "1.001699", "name": "Thủ tục A"},
        "recent_turns": [],
    }

    import json

    json.dumps(state)


def test_node_sinh_dung_original_question(monkeypatch) -> None:
    captured: list[str] = []

    async def fake_sinh(question, _evidence, **_kwargs):
        captured.append(question)
        return answer_module.AnswerResult(
            text="Câu trả lời.",
            citations=(),
            ms=1,
            tokens_in=1,
            tokens_out=1,
            model="test",
        )

    monkeypatch.setattr(answer_module, "dang_bat", lambda: True)
    monkeypatch.setattr(answer_module, "sinh", fake_sinh)

    state = new_state("câu đã rewrite (mã 1.001699)")
    state["original_question"] = "câu người dùng đã hỏi"
    state["retrieval_question"] = "câu đã rewrite (mã 1.001699)"
    state["outcome"] = Outcome.ANSWERED.value
    state["evidence"] = [{"kind": "chunk", "content": "bằng chứng"}]

    patch = asyncio.run(graph.node_sinh(state))

    assert captured == ["câu người dùng đã hỏi"]
    assert patch["answer"] == "Câu trả lời."
