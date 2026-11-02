from __future__ import annotations

from typing import Any

from backend.app.api import faq


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _FakeResult:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def execute(self, *_args: Any, **_kwargs: Any) -> _FakeResult:
        return _FakeResult(self._rows)

    def __enter__(self) -> _FakeConnection:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


class _FakeEngine:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def connect(self) -> _FakeConnection:
        return _FakeConnection(self._rows)


def test_suggest_loc_theo_thu_tuc_facet_va_uu_tien(monkeypatch) -> None:
    rows = [
        {
            "id": "1",
            "question": "Hồ sơ gồm gì?",
            "answer": "Có hồ sơ.",
            "intent": "required_documents",
        },
        {
            "id": "2",
            "question": "Lệ phí bao nhiêu?",
            "answer": "Có lệ phí.",
            "intent": "fee",
        },
        {
            "id": "3",
            "question": "Thời hạn bao lâu?",
            "answer": "Có thời hạn.",
            "intent": "processing_time",
        },
        {
            "id": "4",
            "question": "Nộp ở đâu?",
            "answer": "Nộp tại một cửa.",
            "intent": "submission_method",
        },
        {
            "id": "5",
            "question": "Nộp ở đâu?",
            "answer": "Trùng câu.",
            "intent": "submission_method",
        },
        {
            "id": "6",
            "question": "Câu trả lời rỗng?",
            "answer": "không biết",
            "intent": "result",
        },
    ]
    monkeypatch.setattr(faq, "engine", _FakeEngine(rows))

    result = faq.suggest_ready_faqs(
        "1.004873",
        facets=["required_documents"],
        exclude_question="Hồ sơ gồm gì?",
        limit=3,
    )

    assert [item["id"] for item in result] == ["2", "3", "4"]

    filtered = faq.suggest_ready_faqs(
        "1.004873",
        facets=["fee"],
        exclude_questions=[
            "Lệ phí bao nhiêu?",
            "Thời hạn bao lâu?",
        ],
        limit=3,
    )
    assert [item["id"] for item in filtered] == ["1", "4"]
