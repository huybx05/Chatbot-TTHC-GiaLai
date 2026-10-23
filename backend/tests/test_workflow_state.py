"""Khoá hợp đồng trạng thái workflow (việc 13.1).

Ba thứ được khoá ở đây:

① **Danh sách trường** — xoá một trường là mất thông tin mà không ai báo lỗi, nên danh
   sách được viết cứng trong bài kiểm. Thêm trường thì phải sửa bài kiểm, đó là chủ ý.
② **Danh sách giá trị của các enum** — chúng là hợp đồng với router, với bước leo thang và
   với cơ sở dữ liệu ghi vết.
③ **Khả năng ghi thành JSON** — trạng thái phải ghi vết và phát lại được; nếu ai đó nhét
   một đối tượng không chuyển được sang JSON vào trạng thái, bài kiểm này báo ngay.
"""

from __future__ import annotations

import json

import pytest
from backend.app.rag.evidence import EvidenceItem, EvidenceKind, Provenance
from backend.app.workflow.state import (
    STATE_FIELDS,
    AgentState,
    Branch,
    BranchSignal,
    Outcome,
    RouterSource,
    VerificationStatus,
    new_state,
)

#: Danh sách trường, viết cứng. Sửa trạng thái thì sửa cả đây.
TRUONG_MONG_DOI = {
    # câu hỏi
    "question",
    "normalized_question",
    "turn_index",
    # định danh
    "codes",
    "documents",
    "entity",
    "entity_ambiguous",
    "needs_antecedent",
    "parts",
    "question_frame",
    "groundings",
    "plan",
    "coverage",
    "discovery",
    "plan_class",
    "plan_class_reason",
    "request_plan_class",
    "subjects",
    "thieu",
    "skip_generate",
    "resolution",
    "vector_hash",
    # truy xuất
    "evidence",
    "branch",
    "branch_reason",
    "branch_signal",
    "gate",
    "clarify",
    "refusal",
    "answer",
    "answer_error",
    # sinh & kiểm
    "final_answer",
    "citations",
    "verification",
    # điều khiển
    "retry_count",
    "max_retry",
    "error",
    "fallback_from",
    "outcome",
    # số đo
    "timings",
    "tokens",
    "embedding_used",
    "router_source",
    "router_fallback_reason",
}


def test_danh_sach_truong_khong_doi() -> None:
    assert set(STATE_FIELDS) == TRUONG_MONG_DOI, (
        f"thiếu: {sorted(TRUONG_MONG_DOI - set(STATE_FIELDS))} · "
        f"thừa: {sorted(set(STATE_FIELDS) - TRUONG_MONG_DOI)}"
    )
    assert set(AgentState.__annotations__) == TRUONG_MONG_DOI


def test_trang_thai_moi_co_du_moi_truong() -> None:
    state = new_state("Thủ tục 1.115374 do cơ quan nào ban hành?")
    assert set(state) == TRUONG_MONG_DOI
    # Chỉ ``entity`` được phép là ``None`` — "không có thực thể nào trong câu" là thông tin
    # thật, khác với "quên điền".
    for khoa, gia_tri in state.items():
        if khoa == "entity":
            assert gia_tri is None
            continue
        assert gia_tri is not None, f"{khoa} phải có giá trị, kể cả rỗng"


def test_gia_tri_mac_dinh_an_toan() -> None:
    """Mặc định phải **an toàn**: chưa trả lời thì kết cục là lỗi, không phải "đã trả lời".

    Nếu mặc định là ``ANSWERED``, một bước quên đặt kết cục sẽ khiến hệ thống coi như đã
    trả lời xong — và người dùng nhận câu trả lời rỗng mà không ai biết.
    """
    state = new_state("câu hỏi thử")
    assert state["outcome"] == Outcome.ERROR.value
    assert state["branch"] == ""
    assert state["branch_signal"] == BranchSignal.OK.value
    assert state["verification"]["status"] == VerificationStatus.SKIPPED.value
    assert state["router_source"] == RouterSource.NONE.value
    assert state["max_retry"] == 2
    assert state["retry_count"] == 0
    assert state["turn_index"] == 1
    assert state["embedding_used"] is False
    assert state["vector_hash"] == ""
    assert state["entity"] is None
    assert state["question_frame"]["schema_version"] == "1.0"
    assert state["question_frame"]["scope"] == "unknown"
    assert state["evidence"] == []
    assert state["codes"] == []
    assert state["documents"] == []
    assert state["fallback_from"] == []
    assert state["citations"] == []
    assert state["error"] == ""


def test_cau_hoi_duoc_giu_nguyen_van() -> None:
    """Không tự bỏ dấu ở đây: việc chuẩn hoá thuộc tầng chuẩn hoá.

    Giữ nguyên văn giúp phát hiện chỗ nào quên chuẩn hoá, và giữ được câu gốc để hiển thị
    lại cho người dùng.
    """
    cau = "  Thủ tục 1.115374 ở Cấp Xã  "
    state = new_state(cau)
    assert state["question"] == cau
    assert state["normalized_question"] == ""


def test_turn_index_dat_duoc() -> None:
    assert new_state("x", turn_index=5)["turn_index"] == 5


@pytest.mark.parametrize(
    ("enum", "mong_doi"),
    [
        (Branch, {"fact_lookup", "graph", "hybrid"}),
        (
            Outcome,
            {"answered", "clarify", "need_identity", "abstained", "error"},
        ),
        (
            BranchSignal,
            {"ok", "not_graph", "need_identity", "clarify", "empty", "error"},
        ),
        (RouterSource, {"", "llm", "rule"}),
        (VerificationStatus, {"skipped", "passed", "blocked"}),
        (EvidenceKind, {"fact", "graph", "chunk", "section", "candidate"}),
        (Provenance, {"postgres", "neo4j", "es+qdrant"}),
    ],
)
def test_enum_la_danh_sach_dong(enum: type, mong_doi: set[str]) -> None:
    """Enum là hợp đồng: thêm giá trị mới phải sửa bài kiểm, và như vậy là có chủ ý."""
    assert {thanh_vien.value for thanh_vien in enum} == mong_doi


def test_trang_thai_ghi_duoc_ra_json() -> None:
    """Trạng thái phải ghi vết và phát lại được.

    Thử cả trường hợp đã điền: mã thủ tục, thực thể, bằng chứng, hỏi lại, kiểm chứng. Nếu
    ai đó đưa một đối tượng không chuyển được sang JSON vào trạng thái, bài kiểm này báo.
    """
    state = new_state("Thủ tục 1.115374 do cơ quan nào ban hành?")
    state["codes"] = ["1.115374"]
    state["normalized_question"] = "thu tuc 1.115374 do co quan nao ban hanh"
    state["entity"] = {"kind": "co_quan", "value": "Bộ Y tế", "label": "Bộ Y tế"}
    state["resolution"]["code"] = "1.001699"
    state["resolution"]["method"] = "vector"
    state["resolution"]["alternatives"] = [
        {"code": "1.001699", "name": "Cấp Giấy xác nhận khuyết tật", "score": 0.85}
    ]
    state["evidence"] = [
        EvidenceItem(
            kind=EvidenceKind.GRAPH.value,
            procedure_code="1.001699",
            procedure_name="Cấp Giấy xác nhận khuyết tật",
            detail_url="https://example.test/1.001699",
            section_type="GRAPH",
            title="Cơ quan ban hành",
            content="Bộ Y tế",
            score=0.0,
            source=Branch.GRAPH.value,
            by_keyword=False,
            by_vector=False,
            provenance=Provenance.NEO4J.value,
            part_index=1,
            part_title="Cơ quan liên quan",
        )
    ]
    state["branch"] = Branch.GRAPH.value
    state["branch_signal"] = BranchSignal.CLARIFY.value
    state["clarify"] = {
        "question": "Bạn muốn hỏi thủ tục nào?",
        "options": [{"value": "1.001699", "label": "Cấp Giấy…", "hint": "mã 1.001699"}],
    }
    state["verification"] = {
        "status": VerificationStatus.BLOCKED.value,
        "issues": ["số tiền 500.000 không có trong bằng chứng"],
    }
    state["outcome"] = Outcome.CLARIFY.value

    tho = json.dumps(state, ensure_ascii=False)
    lai = json.loads(tho)
    assert lai["branch"] == "graph"
    assert lai["branch_signal"] == "clarify"
    assert lai["resolution"]["code"] == "1.001699"
    assert lai["evidence"][0]["provenance"] == "neo4j"
    assert lai["evidence"][0]["part_index"] == 1
    assert lai["verification"]["status"] == "blocked"
    assert lai["outcome"] == "clarify"


def test_enum_chuyen_thang_sang_json_duoc() -> None:
    """``StrEnum`` là ``str`` nên ghi thẳng vào JSON không cần hàm chuyển đổi."""
    assert json.dumps({"b": Branch.HYBRID.value}) == '{"b": "hybrid"}'
    assert json.dumps({"o": Outcome.ANSWERED.value}) == '{"o": "answered"}'
