from __future__ import annotations

import json

from backend.app.rag import graph_query, grounding
from backend.app.rag.grounding import SubjectGrounding
from backend.app.rag.resolve import Resolution
from backend.app.text_norm import document_numbers
from backend.app.workflow.question_frame import SubjectType
from backend.app.workflow.question_parser import (
    ParseResult,
    parse_frame,
    to_router_decision,
)


def _decision_frame() -> dict:
    return {
        "schema_version": "1.0",
        "scope": "tthc",
        "subject_mentions": [
            {"type": "decision", "text": "Quyết định 970/QĐ-BYT"}
        ],
        "requests": [
            {
                "text": "áp dụng cho thủ tục nào",
                "facet": "related_procedures",
                "operation": "list",
                "subject_ref": 0,
                "constraints": [],
                "scenario": "",
            }
        ],
        "ambiguity": {"present": False, "kind": "none", "reason": ""},
    }


def test_parser_accepts_decision_subject() -> None:
    frame = parse_frame(json.dumps(_decision_frame()))
    assert frame["subject_mentions"][0]["type"] is SubjectType.DECISION


def test_document_numbers_nhan_qd_prefix() -> None:
    assert document_numbers("Quyết định QĐ/0001-BTP áp dụng cho thủ tục nào?") == [
        "QD/0001 BTP"
    ]


def test_decision_related_procedures_duoc_route_graph() -> None:
    frame = parse_frame(json.dumps(_decision_frame()))
    grounded = [
        SubjectGrounding(
            index=0,
            status="resolved",
            type="decision",
            mention="Quyết định 970/QĐ-BYT",
            code="970/QD BYT",
            method="decision",
        )
    ]

    decision = to_router_decision(
        ParseResult(frame=frame), Resolution(question="x"), grounded
    )

    assert decision.branch == "graph"


def test_domain_group_khop_linh_vuc_duoc_doi_thanh_field(monkeypatch) -> None:
    monkeypatch.setattr(
        graph_query,
        "match_entities",
        lambda *_args, **_kwargs: (
            graph_query.EntityMatch("linh_vuc", "HO_TICH", "Hộ tịch"),
            [],
        ),
    )

    item = grounding._ground_entity(0, "Hộ tịch", "domain_group", object())

    assert item.status == "resolved"
    assert item.type == "field"
    assert item.code == "HO_TICH"
