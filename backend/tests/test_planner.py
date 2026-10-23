"""Phase 4 tests — deterministic retrieval planner.

Table-driven by ``(facet, operation, subject status)``. No network, no database: the planner
only reads the frame and the grounding results.
"""

from __future__ import annotations

import pytest
from backend.app.rag.grounding import SubjectGrounding
from backend.app.workflow import planner
from backend.app.workflow.planner import plan_retrieval
from backend.app.workflow.question_frame import (
    QUESTION_FRAME_SCHEMA_VERSION,
    AmbiguityInfo,
    AmbiguityKind,
    Facet,
    QuestionFrame,
    QuestionRequest,
    QuestionScope,
    RequestOperation,
    SubjectMention,
    SubjectType,
)


def _request(
    facet: Facet,
    operation: RequestOperation = RequestOperation.GET,
    *,
    subject_ref: int | None = 0,
    text: str = "cần gì",
) -> QuestionRequest:
    return QuestionRequest(
        text=text,
        facet=facet,
        operation=operation,
        subject_ref=subject_ref,
        constraints=[],
    )


def _frame(
    requests: list[QuestionRequest],
    *,
    mentions: list[tuple[SubjectType, str]] | None = None,
    scope: QuestionScope = QuestionScope.TTHC,
) -> QuestionFrame:
    return QuestionFrame(
        schema_version=QUESTION_FRAME_SCHEMA_VERSION,
        scope=scope,
        subject_mentions=[
            SubjectMention(type=kind, text=text)
            for kind, text in (mentions or [(SubjectType.PROCEDURE, "thủ tục 1.001699")])
        ],
        requests=requests,
        ambiguity=AmbiguityInfo(present=False, kind=AmbiguityKind.NONE, reason=""),
    )


def _resolved(index: int = 0, code: str = "1.001699", kind: str = "procedure"):
    return SubjectGrounding(
        index=index, status="resolved", type=kind, mention="x", code=code, method="exact_name"
    )


# ── tool mapping ───────────────────────────────────────────────────────────


def test_section_facet_with_code() -> None:
    plan = plan_retrieval(
        _frame([_request(Facet.REQUIRED_DOCUMENTS)]), [_resolved()]
    )
    assert len(plan.tasks) == 1
    task = plan.tasks[0]
    assert task.tool == planner.TOOL_SECTION
    assert task.procedure_codes == ("1.001699",)
    assert task.request_index == 0


def test_processing_time_and_steps_also_go_to_sections() -> None:
    plan = plan_retrieval(
        _frame(
            [
                _request(Facet.PROCESSING_TIME, text="bao lâu"),
                _request(Facet.STEPS, text="trình tự"),
            ]
        ),
        [_resolved()],
    )
    assert [task.tool for task in plan.tasks] == [planner.TOOL_SECTION, planner.TOOL_SECTION]
    assert [task.facet for task in plan.tasks] == ["processing_time", "steps"]


def test_graph_facet_with_code() -> None:
    plan = plan_retrieval(
        _frame([_request(Facet.IMPLEMENTING_AGENCY)]), [_resolved()]
    )
    assert plan.tasks[0].tool == planner.TOOL_GRAPH
    assert plan.tasks[0].procedure_codes == ("1.001699",)


def test_graph_reverse_without_subject() -> None:
    """“Cơ quan nào ban hành nhiều thủ tục nhất” — cần Graph nhưng không cần mã."""
    plan = plan_retrieval(
        _frame([_request(Facet.ISSUING_AGENCY, RequestOperation.LIST, subject_ref=None)]),
        [],
    )
    assert plan.tasks[0].tool == planner.TOOL_GRAPH
    assert plan.tasks[0].procedure_codes == ()


def test_general_info_with_code_uses_fact_lookup() -> None:
    plan = plan_retrieval(_frame([_request(Facet.GENERAL_INFO)]), [_resolved()])
    assert plan.tasks[0].tool == planner.TOOL_FACT


def test_content_without_subject_falls_back_to_hybrid() -> None:
    plan = plan_retrieval(
        _frame([_request(Facet.REQUIRED_DOCUMENTS, subject_ref=None)]), []
    )
    assert plan.tasks[0].tool == planner.TOOL_HYBRID
    assert plan.tasks[0].procedure_codes == ()


# ── unsupported cases ──────────────────────────────────────────────────────


def test_compare_and_rank_are_unsupported() -> None:
    for operation in (RequestOperation.COMPARE, RequestOperation.RANK):
        plan = plan_retrieval(_frame([_request(Facet.FEE, operation)]), [_resolved()])
        assert plan.tasks == []
        assert plan.unsupported[0]["reason"] == planner.REASON_UNSUPPORTED_OPERATION


def test_related_procedures_unsupported() -> None:
    plan = plan_retrieval(_frame([_request(Facet.RELATED_PROCEDURES)]), [_resolved()])
    assert plan.unsupported[0]["reason"] == planner.REASON_UNSUPPORTED_FACET


def test_unknown_facet_unsupported() -> None:
    plan = plan_retrieval(_frame([_request(Facet.UNKNOWN)]), [_resolved()])
    assert plan.unsupported[0]["reason"] == planner.REASON_UNSUPPORTED_FACET


def test_count_on_section_facet_unsupported() -> None:
    plan = plan_retrieval(
        _frame([_request(Facet.FEE, RequestOperation.COUNT)]), [_resolved()]
    )
    assert plan.unsupported[0]["reason"] == planner.REASON_UNSUPPORTED_COUNT


def test_subject_status_blocks_planning() -> None:
    cases = {
        "ambiguous": planner.REASON_AMBIGUOUS_SUBJECT,
        "context_required": planner.REASON_CONTEXT_REQUIRED,
        "not_found": planner.REASON_UNRESOLVED_SUBJECT,
    }
    for status, reason in cases.items():
        item = SubjectGrounding(index=0, status=status, type="procedure", mention="x")
        plan = plan_retrieval(_frame([_request(Facet.FEE)]), [item])
        assert plan.tasks == [], status
        assert plan.unsupported[0]["reason"] == reason


def test_missing_subject_reference() -> None:
    plan = plan_retrieval(_frame([_request(Facet.FEE, subject_ref=3)]), [])
    assert plan.unsupported[0]["reason"] == planner.REASON_MISSING_SUBJECT


# ── multi-intent, merging, ordering ────────────────────────────────────────


def test_three_intents_become_three_tasks_in_order() -> None:
    frame = _frame(
        [
            _request(Facet.REQUIRED_DOCUMENTS, text="cần hồ sơ gì"),
            _request(Facet.PROCESSING_TIME, text="bao lâu"),
            _request(Facet.IMPLEMENTING_AGENCY, text="đơn vị nào xử lý"),
        ]
    )
    plan = plan_retrieval(frame, [_resolved()])
    assert [task.request_index for task in plan.tasks] == [0, 1, 2]
    assert [task.tool for task in plan.tasks] == [
        planner.TOOL_SECTION,
        planner.TOOL_SECTION,
        planner.TOOL_GRAPH,
    ]


def test_duplicate_requests_are_merged() -> None:
    frame = _frame(
        [
            _request(Facet.REQUIRED_DOCUMENTS, text="cần giấy tờ gì"),
            _request(Facet.REQUIRED_DOCUMENTS, text="cần giấy tờ gì"),
        ]
    )
    plan = plan_retrieval(frame, [_resolved()])
    assert len(plan.tasks) == 1
    assert plan.tasks[0].request_index == 0
    assert plan.tasks[0].merged_from == [1]


def test_out_of_scope_returns_empty_plan() -> None:
    frame = _frame([_request(Facet.FEE)], scope=QuestionScope.OUT_OF_SCOPE)
    plan = plan_retrieval(frame, [_resolved()])
    assert plan.empty
    assert plan.unsupported == []


def test_plan_to_dict_shape() -> None:
    plan = plan_retrieval(_frame([_request(Facet.FEE)]), [_resolved()])
    data = plan.to_dict()
    assert data["tasks"][0]["tool"] == "section_lookup"
    assert data["tasks"][0]["procedure_codes"] == ["1.001699"]
    assert data["unsupported"] == []


# ── capability matrix (bảng đóng: facet × operation × subject) ─────────────

MATRIX_CASES = [
    # facet, operation, subject, tool, intent, types, reason
    ("required_documents", "get", "resolved", "section_lookup", "", (), ""),
    ("processing_time", "get", "resolved", "section_lookup", "", (), ""),
    ("fee", "get", "none", "hybrid", "", (), ""),
    ("general_info", "get", "resolved", "fact_lookup", "", (), ""),
    ("general_info", "list", "none", "", "", (), "UNSUPPORTED_OPERATION"),
    ("issuing_agency", "get", "resolved", "graph", "AGENCY", ("BAN_HANH_BOI",), ""),
    ("implementing_agency", "get", "resolved", "graph", "AGENCY", ("CO_THAM_QUYEN",), ""),
    ("coordinating_agency", "get", "resolved", "graph", "AGENCY", ("PHOI_HOP",), ""),
    ("authorized_agency", "get", "resolved", "graph", "AGENCY", ("DUOC_UY_QUYEN",), ""),
    ("administrative_level", "get", "resolved", "graph", "CLASSIFY", ("CAP_THUC_HIEN",), ""),
    ("field", "get", "resolved", "graph", "CLASSIFY", ("LINH_VUC",), ""),
    ("domain_group", "get", "resolved", "graph", "CLASSIFY", ("DOMAIN_GROUP",), ""),
    ("status", "get", "resolved", "graph", "CLASSIFY", ("TRANG_THAI",), ""),
    ("target_audience", "get", "resolved", "graph", "AUDIENCE", (), ""),
    ("legal_basis", "get", "resolved", "graph", "LEGAL_BASIS_OF_PROCEDURE", (), ""),
    ("issuing_agency", "list", "none", "graph", "PROCEDURES_BY_AGENCY", (), ""),
    ("administrative_level", "list", "none", "graph", "PROCEDURES_BY_LEVEL", (), ""),
    ("field", "list", "none", "graph", "PROCEDURES_BY_FIELD", (), ""),
    ("domain_group", "list", "none", "graph", "PROCEDURES_BY_GROUP", (), ""),
    ("target_audience", "list", "none", "", "", (), "UNSUPPORTED_FACET"),
    ("status", "get", "none", "", "", (), "UNSUPPORTED_FACET"),
    ("related_procedures", "get", "resolved", "", "", (), "UNSUPPORTED_FACET"),
    ("unknown", "get", "resolved", "", "", (), "UNSUPPORTED_FACET"),
    ("fee", "count", "resolved", "", "", (), "UNSUPPORTED_COUNT"),
    ("fee", "rank", "resolved", "", "", (), "UNSUPPORTED_OPERATION"),
]


@pytest.mark.parametrize(
    "facet,op,subject,tool,intent,types,reason", MATRIX_CASES
)
def test_capability_matrix(facet, op, subject, tool, intent, types, reason) -> None:
    groundings = [_resolved()] if subject == "resolved" else []
    frame = _frame(
        [
            _request(
                Facet(facet),
                RequestOperation(op),
                subject_ref=0 if subject == "resolved" else None,
            )
        ]
    )
    plan = plan_retrieval(frame, groundings)
    if reason:
        assert plan.tasks == [], (facet, op)
        assert plan.unsupported[0]["reason"] == reason
        return
    assert plan.unsupported == []
    task = plan.tasks[0]
    assert (task.tool, task.intent, task.expected_types) == (tool, intent, types)


# ── constraints ────────────────────────────────────────────────────────────


def _with_constraint(kind: str, text: str) -> QuestionRequest:
    request = _request(Facet.FIELD, RequestOperation.LIST, subject_ref=None)
    request["constraints"] = [{"type": kind, "text": text}]
    return request


def test_reverse_graph_keeps_supported_constraint() -> None:
    frame = _frame([_with_constraint("field", "Y tế")])
    plan = plan_retrieval(frame, [])
    assert plan.unsupported == []
    assert plan.tasks[0].constraints == ({"type": "field", "text": "Y tế"},)


def test_reverse_graph_rejects_unknown_constraint() -> None:
    frame = _frame([_with_constraint("location", "Gia Lai")])
    plan = plan_retrieval(frame, [])
    assert plan.tasks == []
    assert plan.unsupported[0]["reason"] == planner.REASON_UNSUPPORTED_CONSTRAINT


def test_forward_graph_rejects_constraint() -> None:
    request = _request(Facet.IMPLEMENTING_AGENCY)
    request["constraints"] = [{"type": "agency", "text": "Sở Tư pháp"}]
    plan = plan_retrieval(_frame([request]), [_resolved()])
    assert plan.tasks == []
    assert plan.unsupported[0]["reason"] == planner.REASON_UNSUPPORTED_CONSTRAINT


def test_section_rejects_constraint() -> None:
    request = _request(Facet.REQUIRED_DOCUMENTS)
    request["constraints"] = [{"type": "agency", "text": "Sở Tư pháp"}]
    plan = plan_retrieval(_frame([request]), [_resolved()])
    assert plan.tasks == []
    assert plan.unsupported[0]["reason"] == planner.REASON_UNSUPPORTED_CONSTRAINT


def test_same_need_different_wording_is_merged() -> None:
    frame = _frame(
        [
            _request(Facet.REQUIRED_DOCUMENTS, text="cần giấy tờ gì"),
            _request(Facet.REQUIRED_DOCUMENTS, text="hồ sơ gồm những gì"),
        ]
    )
    plan = plan_retrieval(frame, [_resolved()])
    assert len(plan.tasks) == 1
    assert plan.tasks[0].merged_from == [1]


def test_different_constraints_are_not_merged() -> None:
    frame = _frame(
        [
            _with_constraint("field", "Y tế"),
            _with_constraint("field", "Đất đai"),
        ]
    )
    plan = plan_retrieval(frame, [])
    assert len(plan.tasks) == 2
