from __future__ import annotations

import pytest
from backend.app.api import chat as chat_api
from backend.app.main import app
from backend.app.memory.rewriter import RewriteResult
from backend.app.memory.types import ProcedureAnchor
from backend.app.rag import retrieval
from fastapi.testclient import TestClient


@pytest.fixture
def client() -> TestClient:
    chat_api._luot_goi.clear()
    chat_api.xoa_cache()
    with TestClient(app) as test_client:
        yield test_client
    chat_api._luot_goi.clear()
    chat_api.xoa_cache()


def test_chat_dung_rewritten_cho_retrieval_va_giu_original(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    async def fake_rewrite(_question, _memory):
        return RewriteResult(
            original_question="Còn lệ phí thì sao?",
            retrieval_question="Lệ phí thủ tục 1.001699 là bao nhiêu?",
            used=True,
            is_followup=True,
            anchor=ProcedureAnchor(code="1.001699", name="Thủ tục A"),
            confidence=0.95,
            reason="",
        )

    async def fake_retrieve(question: str, **kwargs):
        captured["question"] = question
        captured["original_question"] = kwargs.get("original_question")
        captured["memory_anchor"] = kwargs.get("memory_anchor")
        return {
            "outcome": "answered",
            "answer": "Câu trả lời.",
            "citations": [],
        }

    monkeypatch.setattr(chat_api, "rewrite_question_with_memory", fake_rewrite)
    monkeypatch.setattr(retrieval, "retrieve", fake_retrieve)

    response = client.post(
        "/chat",
        json={"question": "Còn lệ phí thì sao?"},
    )

    assert response.status_code == 200, response.text
    assert captured["question"] == "Lệ phí thủ tục 1.001699 là bao nhiêu?"
    assert captured["original_question"] == "Còn lệ phí thì sao?"
    assert captured["memory_anchor"] == {
        "code": "1.001699",
        "name": "Thủ tục A",
    }


def test_chat_fallback_khi_rewrite_khong_dung(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    async def fake_rewrite(_question, _memory):
        return RewriteResult(
            original_question="Còn lệ phí thì sao?",
            retrieval_question="Còn lệ phí thì sao?",
            used=False,
            is_followup=False,
            anchor=None,
            confidence=0.0,
            reason="low_confidence",
        )

    async def fake_retrieve(question: str, **kwargs):
        captured["question"] = question
        captured["original_question"] = kwargs.get("original_question")
        return {
            "outcome": "answered",
            "answer": "Câu trả lời.",
            "citations": [],
        }

    monkeypatch.setattr(chat_api, "rewrite_question_with_memory", fake_rewrite)
    monkeypatch.setattr(retrieval, "retrieve", fake_retrieve)

    response = client.post(
        "/chat",
        json={"question": "Còn lệ phí thì sao?"},
    )

    assert response.status_code == 200, response.text
    assert captured["question"] == "Còn lệ phí thì sao?"
    assert captured["original_question"] == "Còn lệ phí thì sao?"


def test_stream_luon_gui_rewrite_fallback_vao_trace_retrieval(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    async def fake_rewrite(_question, _memory):
        return RewriteResult(
            original_question="Còn lệ phí thì sao?",
            retrieval_question="Còn lệ phí thì sao?",
            used=False,
            is_followup=False,
            anchor=None,
            confidence=0.0,
            reason="low_confidence",
        )

    async def fake_retrieve(question: str, **kwargs):
        captured["question"] = question
        captured.update(kwargs)
        return {
            "outcome": "clarify",
            "answer": "Bạn muốn hỏi thủ tục nào?",
            "citations": [],
            "clarify": {"question": "Bạn muốn hỏi thủ tục nào?", "options": []},
        }

    monkeypatch.setattr(chat_api, "rewrite_question_with_memory", fake_rewrite)
    monkeypatch.setattr(retrieval, "retrieve", fake_retrieve)

    response = client.post("/chat/stream", json={"question": "Còn lệ phí thì sao?"})

    assert response.status_code == 200, response.text
    assert captured["question"] == "Còn lệ phí thì sao?"
    assert captured["original_question"] == "Còn lệ phí thì sao?"
    assert captured["rewrite"]["reason"] == "low_confidence"
