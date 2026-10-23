from __future__ import annotations

import asyncio
import json

import pytest
from backend.app.rag import graph_query
from backend.app.rag.resolve import Resolution
from backend.app.workflow import question_parser as qp
from backend.app.workflow.question_frame import Facet, QuestionScope


def _frame(*, facet: str = "required_documents", scope: str = "tthc") -> dict:
    return {
        "schema_version": "1.0",
        "scope": scope,
        "subject_mentions": [{"type": "procedure", "text": "giấy xác nhận khuyết tật"}],
        "requests": [
            {
                "text": "cần giấy tờ gì",
                "facet": facet,
                "operation": "get",
                "subject_ref": 0,
                "constraints": [],
            }
        ],
        "ambiguity": {"present": False, "kind": "none", "reason": ""},
    }


def test_parse_frame_doc_dung_schema_dong() -> None:
    frame = qp.parse_frame(json.dumps(_frame(), ensure_ascii=False))
    assert frame["scope"] is QuestionScope.TTHC
    assert frame["requests"][0]["facet"] is Facet.REQUIRED_DOCUMENTS
    assert frame["requests"][0]["scenario"] == ""


def test_scenario_duoc_giu_nguyen_van() -> None:
    value = _frame()
    value["requests"][0]["scenario"] = (
        "cho thuê lại quyền sử dụng đất trong dự án xây dựng kinh doanh kết cấu hạ tầng"
    )
    frame = qp.parse_frame(json.dumps(value, ensure_ascii=False))
    assert frame["requests"][0]["scenario"].startswith("cho thuê lại")


def test_scenario_thieu_thi_rong() -> None:
    value = _frame()
    value["requests"][0].pop("scenario", None)
    frame = qp.parse_frame(json.dumps(value, ensure_ascii=False))
    assert frame["requests"][0]["scenario"] == ""


def test_scenario_qua_dai_cat_o_ranh_gioi_tu() -> None:
    tu = "a" * 10
    value = _frame()
    value["requests"][0]["scenario"] = " ".join([tu] * 60)
    frame = qp.parse_frame(json.dumps(value, ensure_ascii=False))
    scenario = frame["requests"][0]["scenario"]
    assert len(scenario) <= qp.MAX_SCENARIO_CHARS
    assert scenario.endswith(tu), "không được cắt giữa từ"


def test_scenario_khong_phai_chuoi_thi_loi() -> None:
    value = _frame()
    value["requests"][0]["scenario"] = 123
    with pytest.raises(qp.QuestionParserError):
        qp.parse_frame(json.dumps(value, ensure_ascii=False))


def test_request_khong_duoc_co_truong_la() -> None:
    value = _frame()
    value["requests"][0]["case_key"] = "xyz"
    with pytest.raises(qp.QuestionParserError):
        qp.parse_frame(json.dumps(value, ensure_ascii=False))


def test_prompt_co_luat_scenario() -> None:
    assert "scenario" in qp.SYSTEM_PROMPT
    assert "tình huống" in qp.SYSTEM_PROMPT


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(extra=True),
        lambda value: value["requests"][0].update(facet="not_a_facet"),
        lambda value: value["requests"][0].update(subject_ref=9),
    ],
)
def test_parse_frame_tu_choi_dau_ra_khong_hop_le(mutate) -> None:
    value = _frame()
    mutate(value)
    with pytest.raises(qp.QuestionParserError):
        qp.parse_frame(json.dumps(value, ensure_ascii=False))


def test_adapter_chon_nhanh_tu_frame_thay_vi_nhan_llm() -> None:
    graph = qp.ParseResult(qp.parse_frame(json.dumps(_frame(facet="implementing_agency"))))
    content = qp.ParseResult(qp.parse_frame(json.dumps(_frame(facet="processing_time"))))
    resolution = Resolution(question="x")

    assert qp.to_router_decision(graph, resolution).branch == "graph"
    assert qp.to_router_decision(content, resolution).branch == "hybrid"


def test_adapter_tu_choi_scope_ngoai_he_thong() -> None:
    parsed = qp.ParseResult(qp.parse_frame(json.dumps(_frame(scope="out_of_scope"))))
    decision = qp.to_router_decision(parsed, Resolution(question="x"))
    assert decision.branch == ""
    assert decision.signal == "empty"


def test_graph_dung_facet_da_hieu_thay_vi_bat_buoc_tu_khoa() -> None:
    specs = graph_query._specs_for_facets(
        ["implementing_agency", "administrative_level"],
        code="1.001699",
        entity=None,
    )
    assert [spec.intent for spec in specs] == ["AGENCY", "CLASSIFY"]


def test_parse_question_goi_model_va_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    qp.clear_cache()
    monkeypatch.setattr(qp.settings, "router_model_name", "qwen-test")
    monkeypatch.setattr(qp, "_client", lambda: object())

    calls = 0

    async def fake_call(_client, _messages):
        nonlocal calls
        calls += 1
        message = type("Message", (), {"content": json.dumps(_frame())})()
        choice = type("Choice", (), {"message": message})()
        usage = type("Usage", (), {"prompt_tokens": 100, "completion_tokens": 20})()
        return type("Response", (), {"choices": [choice], "usage": usage})()

    monkeypatch.setattr(qp, "_call_model", fake_call)
    first = asyncio.run(qp.parse_question("câu hỏi", Resolution(question="câu hỏi")))
    second = asyncio.run(qp.parse_question("câu hỏi", Resolution(question="câu hỏi")))

    assert calls == 1
    assert first.tokens_in == 100
    assert second.cached is True
    assert second.tokens_in == 0

