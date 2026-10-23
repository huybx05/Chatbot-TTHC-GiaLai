from __future__ import annotations

import asyncio

import pytest
from backend.app.workflow import graph, question_parser
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
from backend.app.workflow.state import new_state


def _parsed(facet: Facet) -> question_parser.ParseResult:
    return question_parser.ParseResult(
        frame=QuestionFrame(
            schema_version=QUESTION_FRAME_SCHEMA_VERSION,
            scope=QuestionScope.TTHC,
            subject_mentions=[SubjectMention(type=SubjectType.PROCEDURE, text="thủ tục 1.001699")],
            requests=[
                QuestionRequest(
                    text="cần giấy tờ gì",
                    facet=facet,
                    operation=RequestOperation.GET,
                    subject_ref=0,
                    constraints=[],
                )
            ],
            ambiguity=AmbiguityInfo(present=False, kind=AmbiguityKind.NONE, reason=""),
        ),
        ms=25,
        tokens_in=120,
        tokens_out=30,
        model="qwen-test",
    )


def test_node_router_dung_question_frame_tren_luong_chinh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(question_parser, "enabled", lambda: True)

    async def fake_parse(*_args, **_kwargs):
        return _parsed(Facet.REQUIRED_DOCUMENTS)

    monkeypatch.setattr(question_parser, "parse_question", fake_parse)
    state = new_state("Thủ tục 1.001699 cần giấy tờ gì?")
    state["codes"] = ["1.001699"]
    patch = asyncio.run(graph.node_router(state))

    assert patch["branch"] == "hybrid"
    assert patch["router_source"] == "llm"
    assert patch["question_frame"]["requests"][0]["facet"] == "required_documents"
    assert patch["parts"] == [{"text": "cần giấy tờ gì", "need": ("required_documents",)}]
    assert patch["tokens"] == {"input": 120, "output": 30}


def test_node_router_ghi_retrieval_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Planner chạy trong node_router và kết quả vào trace, chưa đổi nhánh đang chạy."""
    monkeypatch.setattr(question_parser, "enabled", lambda: True)

    async def fake_parse(*_args, **_kwargs):
        return _parsed(Facet.REQUIRED_DOCUMENTS)

    monkeypatch.setattr(question_parser, "parse_question", fake_parse)
    state = new_state("Thủ tục 1.001699 cần giấy tờ gì?")
    state["codes"] = ["1.001699"]
    patch = asyncio.run(graph.node_router(state))

    task = patch["plan"]["tasks"][0]
    assert task["request_index"] == 0
    assert task["tool"] == "section_lookup"
    assert task["facet"] == "required_documents"
    assert task["operation"] == "get"
    assert task["procedure_codes"] == ["1.001699"]
    assert patch["plan"]["unsupported"] == []


def test_parser_loi_roi_ve_rule_router(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(question_parser, "enabled", lambda: True)

    async def fake_parse(*_args, **_kwargs):
        raise question_parser.QuestionParserError("API lỗi")

    monkeypatch.setattr(question_parser, "parse_question", fake_parse)
    state = new_state("Thủ tục 1.001699 là gì?")
    state["codes"] = ["1.001699"]
    patch = asyncio.run(graph.node_router(state))

    assert patch["router_source"] == "rule"
    assert patch["router_fallback_reason"] == "API lỗi"
    assert patch["branch"] == "fact_lookup"

