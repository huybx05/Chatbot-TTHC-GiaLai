"""Test endpoint đánh giá offline."""

from __future__ import annotations

from backend.app.api.chat import ChatResponse
from backend.app.config import settings
from backend.app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_evaluation_run_returns_result(monkeypatch) -> None:
    monkeypatch.setattr(settings, "evaluation_api_token", "")

    async def fake_chat(payload, request, user, background_tasks):
        assert payload.question == "Lệ phí bao nhiêu?"
        assert payload.history == []
        assert request.state.evaluation_mode is True
        return ChatResponse(
            answer="Lệ phí là 50.000 đồng.",
            citations=[],
            status="answered",
            coverage=["fee"],
            faq_id="faq-1",
        )

    monkeypatch.setattr(
        "backend.app.api.evaluation.chat",
        fake_chat,
    )

    response = client.post(
        "/api/v1/evaluation/run",
        json={"case_id": "DEV-001", "question": "Lệ phí bao nhiêu?"},
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["case_id"] == "DEV-001"
    assert data["status"] == "answered"
    assert data["answer"] == "Lệ phí là 50.000 đồng."
    assert data["coverage"] == ["fee"]
    assert data["faq_id"] == "faq-1"
    assert data["trace_id"]


def test_evaluation_run_validates_question() -> None:
    response = client.post(
        "/api/v1/evaluation/run",
        json={"case_id": "DEV-001", "question": ""},
    )

    assert response.status_code == 422
