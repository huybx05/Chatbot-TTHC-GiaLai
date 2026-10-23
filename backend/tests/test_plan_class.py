"""Giai đoạn 2 — nhãn nguồn lực suy bằng mã nguồn.

Không gọi mô hình. Mỗi ca dưới đây là một tình huống đã gặp trong bộ 60 câu.
"""

from __future__ import annotations

import pytest
from backend.app.workflow.plan_class import PlanClass, classify_request, classify_turn


class _Grounding:
    def __init__(self, index: int, status: str, note: str = "") -> None:
        self.index = index
        self.status = status
        self.note = note


def _request(
    *,
    facet: str = "required_documents",
    operation: str = "get",
    subject_ref: int | None = 0,
) -> dict:
    return {
        "text": "ý hỏi",
        "facet": facet,
        "operation": operation,
        "subject_ref": subject_ref,
        "constraints": [],
        "scenario": "",
    }


def _frame(requests: list[dict], *, scope: str = "tthc") -> dict:
    return {
        "schema_version": "1.0",
        "scope": scope,
        "subject_mentions": [{"type": "procedure", "text": "thủ tục"}],
        "requests": requests,
        "ambiguity": {"present": False, "kind": "none", "reason": ""},
    }


# ── từng ý ───────────────────────────────────────────────────────────────


def test_resolved_subject_is_direct() -> None:
    plan_class, _ = classify_request(_request(), [_Grounding(0, "resolved")])
    assert plan_class is PlanClass.DIRECT


def test_ambiguous_subject_is_clarify() -> None:
    plan_class, _ = classify_request(_request(), [_Grounding(0, "ambiguous")])
    assert plan_class is PlanClass.CLARIFY


def test_context_required_is_clarify() -> None:
    plan_class, _ = classify_request(_request(), [_Grounding(0, "context_required")])
    assert plan_class is PlanClass.CLARIFY


def test_not_found_is_clarify() -> None:
    plan_class, _ = classify_request(_request(), [_Grounding(0, "not_found")])
    assert plan_class is PlanClass.CLARIFY


def test_no_subject_is_discovery() -> None:
    plan_class, _ = classify_request(_request(subject_ref=None), [])
    assert plan_class is PlanClass.DISCOVERY


def test_compare_is_unsupported() -> None:
    plan_class, reason = classify_request(
        _request(operation="compare"), [_Grounding(0, "resolved")]
    )
    assert plan_class is PlanClass.UNSUPPORTED
    assert "compare" in reason


def test_related_procedures_is_unsupported() -> None:
    plan_class, _ = classify_request(
        _request(facet="related_procedures"), [_Grounding(0, "resolved")]
    )
    assert plan_class is PlanClass.UNSUPPORTED


def test_legal_condition_without_subject_is_unsupported() -> None:
    """A7: hỏi điều kiện pháp lý, chưa neo được thủ tục → không hỗ trợ, không hỏi lại."""
    plan_class, reason = classify_request(
        _request(facet="requirements", operation="check", subject_ref=0),
        [_Grounding(0, "not_found")],
    )
    assert plan_class is PlanClass.UNSUPPORTED
    assert "điều kiện pháp lý" in reason


def test_legal_condition_with_resolved_subject_is_direct() -> None:
    plan_class, _ = classify_request(
        _request(facet="requirements", operation="check"),
        [_Grounding(0, "resolved")],
    )
    assert plan_class is PlanClass.DIRECT


# ── cả lượt ──────────────────────────────────────────────────────────────


def test_two_resolved_requests_are_composed() -> None:
    frame = _frame([_request(), _request(facet="processing_time")])
    result = classify_turn(frame, [_Grounding(0, "resolved")])
    assert result.plan_class is PlanClass.COMPOSED
    assert [item.plan_class for item in result.requests] == [
        PlanClass.DIRECT,
        PlanClass.DIRECT,
    ]


def test_unsupported_wins_over_clarify() -> None:
    frame = _frame(
        [
            _request(facet="requirements", subject_ref=0),
            _request(operation="compare", subject_ref=None),
        ]
    )
    result = classify_turn(frame, [_Grounding(0, "ambiguous")])
    assert result.plan_class is PlanClass.UNSUPPORTED


def test_clarify_wins_over_composed() -> None:
    frame = _frame([_request(), _request(facet="processing_time")])
    result = classify_turn(frame, [_Grounding(0, "ambiguous")])
    assert result.plan_class is PlanClass.CLARIFY


def test_single_discovery_turn() -> None:
    frame = _frame([_request(subject_ref=None)])
    assert classify_turn(frame, []).plan_class is PlanClass.DISCOVERY


def test_out_of_scope_short_circuits() -> None:
    frame = _frame([_request()], scope="out_of_scope")
    assert classify_turn(frame, []).plan_class is PlanClass.OUT_OF_SCOPE


def test_smalltalk_is_out_of_scope() -> None:
    frame = _frame([], scope="smalltalk")
    assert classify_turn(frame, []).plan_class is PlanClass.OUT_OF_SCOPE


def test_empty_frame_is_out_of_scope() -> None:
    assert classify_turn(_frame([]), []).plan_class is PlanClass.OUT_OF_SCOPE


@pytest.mark.parametrize(
    ("scope", "facet", "operation", "status", "expected"),
    [
        ("tthc", "required_documents", "get", "resolved", PlanClass.DIRECT),
        ("tthc", "required_documents", "get", "ambiguous", PlanClass.CLARIFY),
        ("out_of_scope", "required_documents", "get", "resolved", PlanClass.OUT_OF_SCOPE),
    ],
)
def test_bang_nhan(scope, facet, operation, status, expected) -> None:
    frame = _frame(
        [_request(facet=facet, operation=operation)],
        scope=scope,
    )
    groundings = [_Grounding(0, status)] if status else []
    assert classify_turn(frame, groundings).plan_class is expected


def test_trace_dict_has_request_detail() -> None:
    result = classify_turn(
        _frame([_request(), _request(facet="processing_time")]),
        [_Grounding(0, "resolved")],
    )
    data = result.to_dict()
    assert data["plan_class"] == "composed"
    assert [item["request_index"] for item in data["requests"]] == [0, 1]
