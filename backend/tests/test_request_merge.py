from __future__ import annotations

from backend.app.workflow.question_frame import (
    QUESTION_FRAME_SCHEMA_VERSION,
    AmbiguityInfo,
    AmbiguityKind,
    Facet,
    QuestionFrame,
    QuestionScope,
    RequestOperation,
)
from backend.app.workflow.question_parser import _merge_duplicate_requests


def _frame() -> QuestionFrame:
    return QuestionFrame(
        schema_version=QUESTION_FRAME_SCHEMA_VERSION,
        scope=QuestionScope.TTHC,
        subject_mentions=[],
        requests=[
            {
                "text": "Hồ sơ gồm những giấy tờ gì?",
                "facet": Facet.REQUIRED_DOCUMENTS,
                "operation": RequestOperation.GET,
                "subject_ref": 0,
                "constraints": [],
                "scenario": "",
            },
            {
                "text": "Lưu ý ra sao?",
                "facet": Facet.REQUIRED_DOCUMENTS,
                "operation": RequestOperation.GET,
                "subject_ref": 0,
                "constraints": [],
                "scenario": "",
            },
        ],
        ambiguity=AmbiguityInfo(present=False, kind=AmbiguityKind.NONE, reason=""),
    )


def test_gop_request_cung_facet_va_giu_text() -> None:
    frame = _merge_duplicate_requests(_frame())
    assert len(frame["requests"]) == 1
    assert "Lưu ý" in frame["requests"][0]["text"]
