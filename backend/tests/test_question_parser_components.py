"""Parser contract cho facet thành phần / thủ tục cha.

Không gọi LLM: parse_frame là lớp kiểm tra JSON đầu ra của router. Các test này
khóa schema để khi prompt thay đổi, facet mới vẫn được chấp nhận và đi đúng
operation.
"""

from __future__ import annotations

import json

import pytest
from backend.app.rag.grounding import SubjectGrounding
from backend.app.rag.resolve import Resolution
from backend.app.workflow.question_frame import Facet
from backend.app.workflow.question_parser import (
    ParseResult,
    QuestionParserError,
    build_messages,
    parse_frame,
    to_router_decision,
)


def _frame(facet: str, operation: str = "list") -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "scope": "tthc",
            "subject_mentions": [{"type": "procedure", "text": "thủ tục được nêu"}],
            "requests": [
                {
                    "text": "ý hỏi",
                    "facet": facet,
                    "operation": operation,
                    "subject_ref": 0,
                    "constraints": [],
                }
            ],
            "ambiguity": {"present": False, "kind": "none", "reason": ""},
        },
        ensure_ascii=False,
    )


def test_parse_frame_chap_nhan_components() -> None:
    frame = parse_frame(_frame("components"))

    assert frame["requests"][0]["facet"] is Facet.COMPONENTS
    assert frame["requests"][0]["operation"].value == "list"


def test_parse_frame_chap_nhan_parent_interlinked() -> None:
    frame = parse_frame(_frame("parent_interlinked"))

    assert frame["requests"][0]["facet"] is Facet.PARENT_INTERLINKED


def test_parse_frame_van_tu_choi_facet_la() -> None:
    with pytest.raises(QuestionParserError):
        parse_frame(_frame("khong_ton_tai"))


def test_prompt_khai_bao_facet_moi_va_quy_tac_phan_biet() -> None:
    messages = build_messages("Thủ tục này gồm những thủ tục con nào?")
    system = messages[0]["content"]

    assert "components" in system
    assert "parent_interlinked" in system
    assert "related_procedures" in system
    assert "quan hệ cha-con/thành phần" in system


def test_router_chon_graph_cho_components() -> None:
    frame = parse_frame(_frame("components"))
    result = ParseResult(frame=frame)
    resolution = Resolution(question="Thủ tục 2.002621 gồm gì?", ma="2.002621")
    grounding = [
        SubjectGrounding(
            index=0,
            status="resolved",
            type="procedure",
            mention="2.002621",
            code="2.002621",
        )
    ]

    decision = to_router_decision(result, resolution, grounding)

    assert decision.branch == "graph"
    assert decision.signal == "ok"


def test_router_chon_graph_cho_parent_interlinked() -> None:
    frame = parse_frame(_frame("parent_interlinked"))
    result = ParseResult(frame=frame)
    resolution = Resolution(question="1.116788 thuộc thủ tục nào?", ma="1.116788")
    grounding = [
        SubjectGrounding(
            index=0,
            status="resolved",
            type="procedure",
            mention="1.116788",
            code="1.116788",
        )
    ]

    decision = to_router_decision(result, resolution, grounding)

    assert decision.branch == "graph"
    assert decision.signal == "ok"
