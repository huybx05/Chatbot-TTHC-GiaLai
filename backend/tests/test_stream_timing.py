from __future__ import annotations

import asyncio

import pytest
from backend.app.api import chat as chat_api
from backend.app.workflow import answer as answer_module


def test_phat_stream_ghi_lai_generate_ms(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_stream(*_args, **_kwargs):
        yield "Câu trả lời."

    monkeypatch.setattr(answer_module, "sinh_stream", fake_stream)
    monkeypatch.setattr(answer_module, "verify_contract", lambda *_args, **_kwargs: [])

    ket_qua = {
        "outcome": "answered",
        "answer": "",
        "evidence": [{"kind": "chunk", "content": "bằng chứng"}],
        "question_frame": {"requests": []},
        "coverage": [],
        "thieu": [],
        "timings": {},
    }

    async def collect() -> None:
        async for _ in chat_api._phat_stream("câu hỏi", ket_qua):
            pass

    asyncio.run(collect())

    assert ket_qua["answer"] == "Câu trả lời."
    assert "generate_ms" in ket_qua["timings"]
    assert ket_qua["timings"]["generate_ms"] >= 0
