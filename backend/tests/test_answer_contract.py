"""Phase 6 tests — pre-LLM answer context and one-pass generation."""

from __future__ import annotations

import asyncio

import pytest
from backend.app.workflow import answer, graph
from backend.app.workflow.answer import AnswerResult, build_request_block


def _evidence(
    facet: str = "required_documents",
    *,
    content: str = "Đơn đề nghị, bản sao giấy tờ",
) -> dict:
    return {
        "kind": "section",
        "title": "Hồ sơ",
        "content": content,
        "facet": facet,
        "request_index": 0,
    }


def _requests(*facets: str) -> list[dict]:
    return [
        {"text": f"ý {i}", "facet": facet, "operation": "get", "subject_ref": 0}
        for i, facet in enumerate(facets)
    ]


# ── request block ─────────────────────────────────────────────────────────


def test_request_block_lists_order_and_coverage() -> None:
    block = build_request_block(
        _requests("required_documents", "processing_time", "implementing_agency"),
        [
            {"request_index": 0, "status": "covered"},
            {"request_index": 1, "status": "empty"},
            {"request_index": 2, "status": "unsupported"},
        ],
    )
    assert block.splitlines()[0].startswith("CÁC Ý CẦN TRẢ LỜI")
    assert "1. thành phần hồ sơ — có dữ liệu" in block
    assert "2. thời hạn giải quyết — không có dữ liệu" in block
    assert "3. cơ quan thực hiện — hệ thống chưa hỗ trợ" in block


def test_request_block_empty_without_requests() -> None:
    assert build_request_block([], []) == ""


# ── one-pass generation in node_sinh ──────────────────────────────────────


def _state() -> dict:
    return {
        "question": "Thủ tục 1.001699 cần hồ sơ gì, bao lâu?",
        "outcome": "answered",
        "evidence": [_evidence()],
        "thieu": ["processing_time"],
        "coverage": [
            {"request_index": 0, "status": "covered", "facet": "required_documents"},
            {"request_index": 1, "status": "empty", "facet": "processing_time"},
        ],
        "question_frame": {"requests": _requests("required_documents", "processing_time")},
        "tokens": {"input": 100, "output": 20},
        "timings": {},
    }


def _result(text: str) -> AnswerResult:
    return AnswerResult(
        text=text, citations=(), ms=10, tokens_in=50, tokens_out=10, model="test"
    )


def test_node_sinh_returns_the_only_model_response(monkeypatch) -> None:
    goi = {"lan": 0}

    async def fake_sinh(*_args, **_kwargs):
        goi["lan"] += 1
        return _result("Hồ sơ gồm đơn đề nghị. Thời hạn: chưa có dữ liệu.")

    monkeypatch.setattr(answer, "sinh", fake_sinh)
    monkeypatch.setattr(answer, "dang_bat", lambda: True)

    patch = asyncio.run(graph.node_sinh(_state()))
    assert goi["lan"] == 1
    assert "đơn đề nghị" in patch["answer"]
    assert patch["verification"] == {"status": "passed", "issues": []}
    assert patch["tokens"]["input"] == 150


def test_chon_evidence_giu_du_case_va_dedupe() -> None:
    evidence = [
        {
            "kind": "section",
            "content": f"Nội dung {index}",
            "facet": "required_documents",
            "request_index": 0,
            "metadata": {"case_order": index % 2 + 1, "case_name": f"case {index % 2 + 1}"},
        }
        for index in range(20)
    ]
    evidence.append(dict(evidence[0]))
    chosen = answer._chon_evidence(
        evidence,
        requests=[{"facet": "required_documents"}],
        coverage=[{"request_index": 0, "status": "covered", "facet": "required_documents"}],
    )

    assert len(chosen) == 20


def test_validator_bat_so_khong_co_trong_evidence() -> None:
    issues = answer.verify_contract(
        "Thời hạn là 12 ngày.",
        [_evidence(content="Thời hạn: 9 ngày. Trường hợp khó khăn cộng thêm 10 ngày.")],
    )

    assert "unsupported_number:12" in issues


def test_validator_cho_phep_tong_hai_moc() -> None:
    issues = answer.verify_contract(
        "Tối đa 19 ngày.",
        [_evidence(content="Thời hạn: 9 ngày. Trường hợp khó khăn cộng thêm 10 ngày.")],
    )

    assert "unsupported_number:19" not in issues


def test_validator_bo_qua_ma_thu_tuc() -> None:
    issues = answer.verify_contract(
        "Thủ tục 1.014100 có thời hạn 10 ngày.",
        [_evidence(content="Thời hạn: 10 ngày.")],
    )

    assert not any(item.startswith("unsupported_number:") for item in issues)


def test_validator_bat_facet_covered_bi_bo_sot() -> None:
    issues = answer.verify_contract(
        "Hồ sơ gồm đơn đề nghị.",
        [_evidence()],
        requests=[
            {
                "text": "số quyết định",
                "facet": "decision_number",
                "operation": "get",
                "subject_ref": 0,
            }
        ],
        coverage=[{"request_index": 0, "status": "covered"}],
    )

    assert "missing_covered_facet:decision_number" in issues


# ── chọn evidence theo ý + nhóm context ──────────────────────────────────


def _evidence_for(request_index: int, text: str, facet: str = "required_documents") -> dict:
    return {
        "kind": "section",
        "title": "Mục",
        "content": text,
        "facet": facet,
        "request_index": request_index,
    }


def test_selection_keeps_evidence_for_later_request() -> None:
    requests = _requests("required_documents", "processing_time", "implementing_agency")
    evidence = [_evidence_for(0, f"hồ sơ {i}") for i in range(8)]
    evidence.append(_evidence_for(2, "Sở Tư pháp thực hiện", "implementing_agency"))
    chon = answer._chon_evidence(evidence, requests, [], toi_da=12)  # noqa: SLF001
    indexes = [index for index, _ in chon]
    assert indexes.count(0) >= 1
    assert 2 in indexes, "ý cuối vẫn phải có bằng chứng dù ý đầu có nhiều mục"


def test_context_groups_evidence_by_request() -> None:
    requests = _requests("required_documents", "processing_time")
    evidence = [
        _evidence_for(0, "nội dung hồ sơ"),
        _evidence_for(1, "mười bốn ngày", "processing_time"),
    ]
    coverage = [
        {"request_index": 0, "status": "covered"},
        {"request_index": 1, "status": "covered"},
    ]
    text, nhan = answer.build_context(evidence, requests=requests, coverage=coverage)
    assert "### Ý 1 — thành phần hồ sơ" in text
    assert "### Ý 2 — thời hạn giải quyết" in text
    assert text.index("nội dung hồ sơ") < text.index("### Ý 2")
    assert len(nhan) == 2


def test_statuses_are_not_all_missing_data() -> None:
    requests = _requests("required_documents", "processing_time", "fee")
    coverage = [
        {"request_index": 0, "status": "failed"},
        {"request_index": 1, "status": "unsupported"},
        {"request_index": 2, "status": "empty"},
    ]
    block = answer.build_request_block(requests, coverage)
    assert "nguồn dữ liệu tạm lỗi" in block
    assert "chưa hỗ trợ" in block
    assert "không có dữ liệu" in block

def test_citations_match_context_selection() -> None:
    requests = _requests("required_documents")
    evidence = [_evidence_for(0, "a"), _evidence_for(0, "b")]
    coverage = [{"request_index": 0, "status": "covered"}]
    text, nhan = answer.build_context(evidence, requests=requests, coverage=coverage)
    citations = answer.build_citations(evidence, requests=requests, coverage=coverage)
    assert len(citations) == len(nhan) == 2


def test_node_sinh_does_nothing_when_outcome_not_answered() -> None:
    state = _state()
    state["outcome"] = "abstained"
    assert asyncio.run(graph.node_sinh(state)) == {}


@pytest.mark.parametrize("text", ["", "   "])
def test_node_sinh_reports_empty_model_output(monkeypatch, text) -> None:
    async def fake_sinh(*_args, **_kwargs):
        raise answer.AnswerError("mô hình trả chuỗi rỗng")

    monkeypatch.setattr(answer, "sinh", fake_sinh)
    monkeypatch.setattr(answer, "dang_bat", lambda: True)
    patch = asyncio.run(graph.node_sinh(_state()))
    assert patch["answer_error"]
