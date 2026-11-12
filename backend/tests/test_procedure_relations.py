"""Quan hệ thủ tục: 'liên quan'/'liên thông' dùng một facet chung."""

from __future__ import annotations

import json

from backend.app.rag.graph_capabilities import FORWARD_CAPABILITY
from backend.app.rag.graph_query import COLUMNS
from backend.app.rag.graph_shapes import SHAPES, build_shape
from backend.app.rag.grounding import SubjectGrounding
from backend.app.rag.resolve import Resolution
from backend.app.workflow.planner import plan_retrieval
from backend.app.workflow.question_frame import Facet
from backend.app.workflow.question_parser import (
    ParseResult,
    parse_frame,
    to_router_decision,
)


def _frame(facet: str) -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "scope": "tthc",
            "subject_mentions": [{"type": "procedure", "text": "thủ tục 1.001193"}],
            "requests": [
                {
                    "text": "liên quan tới thủ tục nào",
                    "facet": facet,
                    "operation": "list",
                    "subject_ref": 0,
                    "constraints": [],
                }
            ],
            "ambiguity": {"present": False, "kind": "none", "reason": ""},
        },
        ensure_ascii=False,
    )


def test_facet_quan_he_thu_tuc_ton_tai() -> None:
    assert Facet.PROCEDURE_RELATIONS.value == "procedure_relations"


def test_parser_chap_nhan_facet_quan_he_thu_tuc() -> None:
    frame = parse_frame(_frame("procedure_relations"))

    assert frame["requests"][0]["facet"] is Facet.PROCEDURE_RELATIONS


def test_planner_chon_graph_cho_quan_he_thu_tuc() -> None:
    from backend.app.rag.grounding import SubjectGrounding

    frame = parse_frame(_frame("procedure_relations"))
    grounding = [
        SubjectGrounding(
            index=0,
            status="resolved",
            type="procedure",
            mention="1.001193",
            code="1.001193",
        )
    ]

    plan = plan_retrieval(frame, grounding)

    assert not plan.unsupported
    task = plan.tasks[0]
    assert task.intent == "PROCEDURE_RELATIONS"
    assert task.procedure_codes == ("1.001193",)


def test_capability_quan_he_thu_tuc() -> None:
    cap = FORWARD_CAPABILITY[Facet.PROCEDURE_RELATIONS.value]

    assert cap.intent == "PROCEDURE_RELATIONS"


def test_shape_quan_he_thu_tuc_di_hai_chieu() -> None:
    shape = SHAPES["PROCEDURE_RELATIONS"]
    cypher = build_shape(shape)

    assert "THANH_PHAN_CUA" in cypher
    assert "-[e1:THANH_PHAN_CUA]-" in cypher
    assert "startNode(e1).key" in cypher
    assert "x.key" in cypher


def test_columns_quan_he_thu_tuc() -> None:
    keys = {key for key, _label, _split in COLUMNS["PROCEDURE_RELATIONS"]}

    assert {"vai_tro", "ma", "ten", "detail_url"} <= keys


def test_related_procedures_cu_cung_duoc_route_sang_quan_he() -> None:
    frame = parse_frame(_frame("related_procedures"))
    grounding = [
        SubjectGrounding(
            index=0,
            status="resolved",
            type="procedure",
            mention="1.001193",
            code="1.001193",
        )
    ]

    plan = plan_retrieval(frame, grounding)

    assert not plan.unsupported
    assert plan.tasks[0].intent == "PROCEDURE_RELATIONS"


def test_router_chon_graph_cho_quan_he_thu_tuc() -> None:
    frame = parse_frame(_frame("procedure_relations"))
    result = ParseResult(frame=frame)
    resolution = Resolution(question="1.001193 liên quan tới thủ tục nào?", ma="1.001193")
    grounding = [
        SubjectGrounding(
            index=0,
            status="resolved",
            type="procedure",
            mention="1.001193",
            code="1.001193",
        )
    ]

    decision = to_router_decision(result, resolution, grounding)

    assert decision.branch == "graph"
    assert decision.signal == "ok"
