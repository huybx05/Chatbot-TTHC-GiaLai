from __future__ import annotations

import asyncio

import pytest
from backend.app.rag import hybrid


def test_hybrid_tach_cau_goc_cho_bm25_va_cau_rewrite_cho_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    async def fake_keyword(question, **_kwargs):
        captured["keyword"] = question
        return []

    async def fake_vector(vector, **_kwargs):
        captured["vector"] = "called"
        return []

    monkeypatch.setattr(hybrid, "keyword_only", fake_keyword)
    monkeypatch.setattr(hybrid, "vector_only", fake_vector)

    asyncio.run(
        hybrid.hybrid(
            "Lệ phí thủ tục 1.001699 là bao nhiêu?",
            vector=[0.1, 0.2],
            keyword_question="Còn lệ phí thì sao?",
        )
    )

    assert captured["keyword"] == "Còn lệ phí thì sao?"
    assert captured["vector"] == "called"


def test_hybrid_mac_dinh_dung_cau_rewrite(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    async def fake_keyword(question, **_kwargs):
        captured["keyword"] = question
        return []

    async def fake_vector(_vector, **_kwargs):
        captured["vector"] = "called"
        return []

    monkeypatch.setattr(hybrid, "keyword_only", fake_keyword)
    monkeypatch.setattr(hybrid, "vector_only", fake_vector)

    asyncio.run(
        hybrid.hybrid(
            "Lệ phí thủ tục 1.001699 là bao nhiêu?",
            vector=[0.1, 0.2],
        )
    )

    assert captured["keyword"] == "Lệ phí thủ tục 1.001699 là bao nhiêu?"
    assert captured["vector"] == "called"
