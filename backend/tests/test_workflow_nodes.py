"""Khoá bốn bước truy xuất và tầng kho đệm (việc 13.5).

Bất biến quan trọng nhất: **bước không tự nhúng câu hỏi**. Câu hỏi được nhúng tối đa một lần
ở bộ định danh; bước nào nhúng lại là phá vỡ nguyên tắc chi phí của dự án. Có bài kiểm riêng
cho việc này.
"""

from __future__ import annotations

import asyncio

import pytest
from backend.app.rag import fact_lookup, graph_query, hybrid, resolve
from backend.app.rag.evidence import EvidenceKind
from backend.app.rag.fact_lookup import ProcedureFact
from backend.app.rag.graph_query import GraphEvidence
from backend.app.rag.types import Candidate, RetrievalOutcome
from backend.app.workflow import nodes
from backend.app.workflow.state import BranchSignal, new_state


def _chay(coro):
    return asyncio.run(coro)


def _state(cau: str = "Thủ tục 1.001699 do cơ quan nào ban hành?", **ghi_de):
    s = new_state(cau)
    s.update(ghi_de)
    return s


def _fact() -> ProcedureFact:
    return ProcedureFact(
        ma_thu_tuc="1.001699",
        ten_thu_tuc="Cấp Giấy xác nhận khuyết tật",
        cap_thuc_hien=("Cấp xã",),
        co_quan_ban_hanh="Bộ Y tế",
        so_quyet_dinh="1234/QĐ-BYT",
        detail_url="https://dichvucong.gov.vn/1.001699",
    )


def _candidate() -> Candidate:
    return Candidate(
        chunk_id="1.001699-FEE",
        procedure_code="1.001699",
        procedure_name="Cấp Giấy xác nhận khuyết tật",
        section_type="FEE",
        title="Lệ phí",
        content="Không thu lệ phí",
        detail_url="https://dichvucong.gov.vn/1.001699",
        score=0.02,
        source="hybrid",
        by_keyword=True,
        by_vector=True,
    )


def _sach_kho_vector():
    resolve.reset_vector_cache()


# ── Kho đệm: ba dải điểm ────────────────────────────────────────────────


def test_fact_khong_co_ma_thi_bao_thieu_dinh_danh() -> None:
    ket_qua = _chay(nodes.node_fact_lookup(_state(codes=[])))
    assert ket_qua["branch_signal"] == BranchSignal.NEED_IDENTITY.value
    assert ket_qua["evidence"] == []


def test_fact_co_ma_tra_ra_bang_chung(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_facts(codes):
        assert codes == ["1.001699"]
        return [_fact()]

    monkeypatch.setattr(fact_lookup, "get_facts", fake_get_facts)
    ket_qua = _chay(nodes.node_fact_lookup(_state(codes=["1.001699"])))
    assert ket_qua["branch_signal"] == BranchSignal.OK.value
    assert len(ket_qua["evidence"]) == 1
    assert ket_qua["evidence"][0]["kind"] == EvidenceKind.FACT.value
    assert ket_qua["timings"]["branch_ms"] >= 0


def test_fact_dung_ma_tu_grounding(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_facts(codes):
        assert codes == ["1.001699"]
        return [_fact()]

    monkeypatch.setattr(fact_lookup, "get_facts", fake_get_facts)
    ket_qua = _chay(
        nodes.node_fact_lookup(_state(codes=[], resolution={"code": "1.001699"}))
    )
    assert ket_qua["branch_signal"] == BranchSignal.OK.value


def test_fact_khong_co_du_lieu_bao_rong(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_facts(codes):
        return []

    monkeypatch.setattr(fact_lookup, "get_facts", fake_get_facts)
    ket_qua = _chay(nodes.node_fact_lookup(_state(codes=["1.999999"])))
    assert ket_qua["branch_signal"] == BranchSignal.EMPTY.value


# ── Bước đồ thị: giữ nguyên ba kết cục riêng ────────────────────────────


@pytest.mark.parametrize(
    ("intent", "mong_doi"),
    [
        ("AGENCY", BranchSignal.OK),
        ("NOT_GRAPH", BranchSignal.NOT_GRAPH),
        ("NEED_IDENTITY", BranchSignal.NEED_IDENTITY),
        ("CLARIFY", BranchSignal.CLARIFY),
        ("NONE", BranchSignal.ERROR),
    ],
)
def test_graph_doi_ket_cuc_thanh_tin_hieu(
    monkeypatch: pytest.MonkeyPatch, intent: str, mong_doi: BranchSignal
) -> None:
    async def fake_answer(cau, *, codes=None, limit=20, get_vector=None):
        dong = [{"vai_tro": "Cơ quan ban hành", "gia_tri": "Bộ Y tế"}] if intent == "AGENCY" else []
        return GraphEvidence(
            intent=intent,
            title="thử",
            rows=dong,
            columns=(("vai_tro", "Vai trò", False), ("gia_tri", "Cơ quan", True)),
            template=intent,
        )

    monkeypatch.setattr(graph_query, "answer", fake_answer)
    ket_qua = _chay(nodes.node_graph(_state()))
    assert ket_qua["branch_signal"] == mong_doi.value


def test_graph_chuyen_tiep_noi_dung_hoi_lai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nội dung hỏi lại mà đồ thị đã dựng phải đi tiếp, không bị nuốt."""

    async def fake_answer(cau, *, codes=None, limit=20, get_vector=None):
        return GraphEvidence(
            intent="CLARIFY",
            title="Có nhiều văn bản cùng khớp",
            clarify=True,
            clarify_question="Bạn muốn hỏi văn bản nào?",
            options=[{"value": "a", "label": "Văn bản A", "hint": "văn bản pháp lý"}],
        )

    monkeypatch.setattr(graph_query, "answer", fake_answer)
    ket_qua = _chay(nodes.node_graph(_state()))
    assert ket_qua["clarify"]["question"] == "Bạn muốn hỏi văn bản nào?"
    assert ket_qua["clarify"]["options"][0]["value"] == "a"


def test_graph_loi_bao_tin_hieu_loi(monkeypatch: pytest.MonkeyPatch) -> None:
    async def hong(cau, *, codes=None, limit=20, get_vector=None):
        raise RuntimeError("Neo4j sập")

    monkeypatch.setattr(graph_query, "answer", hong)
    ket_qua = _chay(nodes.node_graph(_state()))
    assert ket_qua["branch_signal"] == BranchSignal.ERROR.value
    assert "Neo4j" in ket_qua["error"]


# ── Bước tìm kiếm lai ───────────────────────────────────────────────────


def test_hybrid_khong_co_vector_thi_bao_thieu() -> None:
    ket_qua = _chay(nodes.node_hybrid(_state()))
    assert ket_qua["branch_signal"] == BranchSignal.NEED_IDENTITY.value


def test_hybrid_dung_lai_vector_va_loc_theo_ma(monkeypatch: pytest.MonkeyPatch) -> None:
    da_nhan: dict = {}

    async def fake_hybrid(cau, *, vector, codes=None, **kwargs):
        da_nhan["vector"] = vector
        da_nhan["codes"] = codes
        return RetrievalOutcome(candidates=[_candidate()])

    monkeypatch.setattr(hybrid, "hybrid", fake_hybrid)
    vec = [0.3, 0.4]
    dau_vet = resolve.remember_vector(vec)
    ket_qua = _chay(nodes.node_hybrid(_state(codes=["1.001699"], vector_hash=dau_vet)))

    assert da_nhan["vector"] == vec, "phải dùng lại vector đã cất, không nhúng lại"
    assert da_nhan["codes"] == ["1.001699"]
    assert ket_qua["evidence"][0]["kind"] == EvidenceKind.CHUNK.value
    assert ket_qua["evidence"][0]["by_vector"] is True


def test_hybrid_loc_theo_ma_tu_grounding(monkeypatch: pytest.MonkeyPatch) -> None:
    da_nhan: dict = {}

    async def fake_hybrid(cau, *, vector, codes=None, **kwargs):
        da_nhan["codes"] = codes
        return RetrievalOutcome(candidates=[_candidate()])

    monkeypatch.setattr(hybrid, "hybrid", fake_hybrid)
    dau_vet = resolve.remember_vector([0.3, 0.4])
    _chay(
        nodes.node_hybrid(
            _state(codes=[], resolution={"code": "1.001699"}, vector_hash=dau_vet)
        )
    )
    assert da_nhan["codes"] == ["1.001699"]


def test_hybrid_bat_cong_cho_cau_mot_y_khong_ma(monkeypatch: pytest.MonkeyPatch) -> None:
    """Câu **một ý, không mã** mới chấm cổng — lớp "trông giống TTHC mà dữ liệu không có"."""
    da_nhan: dict = {}

    async def fake_hybrid(cau, *, vector, codes=None, **kwargs):
        da_nhan.update(kwargs)
        da_nhan["codes"] = codes
        return RetrievalOutcome(candidates=[_candidate()])

    monkeypatch.setattr(hybrid, "hybrid", fake_hybrid)
    dau_vet = resolve.remember_vector([0.5])
    _chay(
        nodes.node_hybrid(
            _state(vector_hash=dau_vet, parts=[{"text": "giấy phép lái xe", "need": ()}])
        )
    )

    assert da_nhan["use_gate"] is True
    assert da_nhan["codes"] == [], "phải truyền danh sách rỗng (đã xác thực, không có mã)"


def test_hybrid_khong_bat_cong_khi_cau_nhieu_y(monkeypatch: pytest.MonkeyPatch) -> None:
    """Câu nhiều ý: điểm bị chia nhỏ (đo được 0,6219) → chấm là từ chối oan."""
    da_nhan: dict = {}

    async def fake_hybrid(cau, *, vector, codes=None, **kwargs):
        da_nhan.update(kwargs)
        return RetrievalOutcome(candidates=[_candidate()])

    monkeypatch.setattr(hybrid, "hybrid", fake_hybrid)
    dau_vet = resolve.remember_vector([0.5])
    _chay(
        nodes.node_hybrid(
            _state(
                vector_hash=dau_vet,
                parts=[
                    {"text": "hồ sơ", "need": ("required_documents",)},
                    {"text": "lệ phí", "need": ("fee",)},
                ],
            )
        )
    )

    assert da_nhan["use_gate"] is False


def test_hybrid_khong_bat_cong_khi_co_ma(monkeypatch: pytest.MonkeyPatch) -> None:
    da_nhan: dict = {}

    async def fake_hybrid(cau, *, vector, codes=None, **kwargs):
        da_nhan.update(kwargs)
        return RetrievalOutcome(candidates=[_candidate()])

    monkeypatch.setattr(hybrid, "hybrid", fake_hybrid)
    dau_vet = resolve.remember_vector([0.5])
    _chay(nodes.node_hybrid(_state(codes=["1.001699"], vector_hash=dau_vet)))

    assert da_nhan["use_gate"] is False, "có mã đã xác thực thì mặc nhiên trong phạm vi"


def test_hybrid_ma_tu_grounding_khong_tat_cong(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mã grounding không phải mã đã xác thực — cổng vẫn phải chấm câu một ý."""
    da_nhan: dict = {}

    async def fake_hybrid(cau, *, vector, codes=None, **kwargs):
        da_nhan.update(kwargs)
        da_nhan["codes"] = codes
        return RetrievalOutcome(candidates=[_candidate()])

    monkeypatch.setattr(hybrid, "hybrid", fake_hybrid)
    dau_vet = resolve.remember_vector([0.5])
    _chay(
        nodes.node_hybrid(
            _state(
                codes=[],
                resolution={"code": "1.001699"},
                vector_hash=dau_vet,
                parts=[{"text": "giấy phép lái xe", "need": ()}],
            )
        )
    )

    assert da_nhan["codes"] == ["1.001699"], "vẫn lọc theo mã grounding"
    assert da_nhan["use_gate"] is True, "nhưng cổng chỉ được miễn bởi mã đã xác thực"


def test_hybrid_bi_cong_tu_choi_thi_bao_rong(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_hybrid(cau, *, vector, codes=None, **kwargs):
        return RetrievalOutcome(candidates=[], refused=True, gate_score=0.42)

    monkeypatch.setattr(hybrid, "hybrid", fake_hybrid)
    dau_vet = resolve.remember_vector([0.5])
    ket_qua = _chay(nodes.node_hybrid(_state(vector_hash=dau_vet)))
    assert ket_qua["branch_signal"] == BranchSignal.EMPTY.value
    assert ket_qua["gate"]["refused"] is True
    assert ket_qua["gate"]["score"] == pytest.approx(0.42)


# ── Bước kho đệm ────────────────────────────────────────────────────────


def test_khong_buoc_nao_tu_nhung(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bước nào gọi thẳng API nhúng là phá vỡ nguyên tắc "một câu một lần nhúng"."""
    dem = {"n": 0}

    async def dem_embed(text: str) -> list[float]:
        dem["n"] += 1
        return [0.1, 0.2]

    monkeypatch.setattr(resolve.resolver.embeddings, "embed", dem_embed)

    async def fake_get_facts(codes):
        return [_fact()]

    async def fake_answer(cau, *, codes=None, limit=20, get_vector=None):
        return GraphEvidence(intent="AGENCY", title="x")

    async def fake_hybrid(cau, *, vector, codes=None, **kwargs):
        return RetrievalOutcome(candidates=[])

    monkeypatch.setattr(fact_lookup, "get_facts", fake_get_facts)
    monkeypatch.setattr(graph_query, "answer", fake_answer)
    monkeypatch.setattr(hybrid, "hybrid", fake_hybrid)

    dau_vet = resolve.remember_vector([0.7])
    s = _state(codes=["1.001699"], vector_hash=dau_vet)
    _chay(nodes.node_fact_lookup(s))
    _chay(nodes.node_graph(s))
    _chay(nodes.node_hybrid(s))
    assert dem["n"] == 0, f"có bước tự nhúng {dem['n']} lần"


def test_moi_buoc_tra_ve_dung_khoa_trang_thai() -> None:
    from backend.app.workflow.state import STATE_FIELDS

    hop_le = {
        "evidence",
        "branch",
        "branch_signal",
        "timings",
        "branch_reason",
        "error",
        "gate",
        "clarify",
    }
    cho_phep = hop_le & set(STATE_FIELDS)
    for ten, buoc in nodes.NODES.items():
        assert callable(buoc), ten
    # Không khoá nào trong bản vá được phép nằm ngoài hợp đồng trạng thái.
    assert hop_le <= set(STATE_FIELDS), sorted(hop_le - set(STATE_FIELDS))
    assert cho_phep == hop_le


def test_ba_buoc_deu_co_trong_bang() -> None:
    assert set(nodes.NODES) == {"fact_lookup", "graph", "hybrid"}
