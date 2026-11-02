from __future__ import annotations

from backend.app.rag import graph_query
from backend.app.rag.grounding import SubjectGrounding
from backend.app.workflow.planner import plan_retrieval
from backend.app.workflow.question_frame import (
    QUESTION_FRAME_SCHEMA_VERSION,
    AmbiguityInfo,
    AmbiguityKind,
    Facet,
    QuestionFrame,
    QuestionScope,
    RequestOperation,
    SubjectType,
)
from data_pipeline.indexing.neo4j import split_decision_numbers


def _frame() -> QuestionFrame:
    return QuestionFrame(
        schema_version=QUESTION_FRAME_SCHEMA_VERSION,
        scope=QuestionScope.TTHC,
        subject_mentions=[
            {"type": SubjectType.DOCUMENT, "text": "Quyết định số 570/QĐ-BTP"}
        ],
        requests=[
            {
                "text": "làm căn cứ cho những thủ tục nào",
                "facet": Facet.RELATED_PROCEDURES,
                "operation": RequestOperation.LIST,
                "subject_ref": 0,
                "constraints": [],
            }
        ],
        ambiguity=AmbiguityInfo(present=False, kind=AmbiguityKind.NONE, reason=""),
    )


def test_split_decision_numbers() -> None:
    assert split_decision_numbers("570/QĐ-BTP") == [("570/QD BTP", "570/QĐ-BTP")]
    assert split_decision_numbers("Không có thông tin") == []


def test_match_decision() -> None:
    vocab = graph_query.Vocabulary(
        run_id="test",
        decisions=(("570/QD BTP", "Quyết định số 570/QĐ-BTP"),),
    )
    result = graph_query.match_decisions("Quyết định số 570/QĐ-BTP", vocab)
    assert result.unique is not None
    assert result.unique.key == "570/QD BTP"
    assert result.unique.kind == "decision"


def test_planner_routes_decision_by_subject_not_keywords() -> None:
    plan = plan_retrieval(
        _frame(),
        [
            SubjectGrounding(
                index=0,
                status="resolved",
                type="document",
                mention="Quyết định số 570/QĐ-BTP",
                code="570/QD BTP",
                name="Quyết định số 570/QĐ-BTP",
                method="decision",
            )
        ],
    )
    assert not plan.unsupported
    assert plan.tasks[0].tool == "graph"
    assert plan.tasks[0].intent == "PROCEDURES_BY_DECISION"
    assert plan.tasks[0].subject_key == "570/QD BTP"
    assert plan.tasks[0].subject_kind == "decision"
