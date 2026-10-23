"""Khoá đồ thị luồng (việc 13.6).

Ba thứ được khoá:

① **Mọi bước đều có đường ra** — một bước không có cạnh ra là nhánh cụt, và triệu chứng
   của nó là "câu hỏi treo" chứ không phải lỗi, nên rất khó thấy.
② **Ba kết cục đặc biệt có đường đi thật**: trúng kho đệm, hỏi lại, và không nhánh nào.
③ **Câu đã có neo không nhúng** — đo lại đúng bất biến chi phí, lần này qua cả đồ thị.
"""

from __future__ import annotations

import asyncio

import pytest
from backend.app.rag import embeddings, fact_lookup, graph_query, hybrid, resolve
from backend.app.rag.evidence import Branch
from backend.app.rag.fact_lookup import ProcedureFact
from backend.app.rag.graph_query import GraphEvidence
from backend.app.rag.resolver import ProcedureResolution
from backend.app.rag.types import Candidate, RetrievalOutcome
from backend.app.workflow import graph
from backend.app.workflow.state import Outcome, new_state


def _chay(cau: str, *, state=None) -> dict:
    s = state if state is not None else new_state(cau)
    return asyncio.run(graph.WORKFLOW.ainvoke(s))


# ── Dựng đồ thị ─────────────────────────────────────────────────────────


def test_do_thi_co_du_cac_buoc() -> None:
    ten = set(graph.WORKFLOW.get_graph().nodes)
    for buoc in (
        graph.NEO,
        graph.DINH_DANH,
        graph.ROUTER,
        graph.HOI_LAI,
        graph.KET_THUC,
        *[b.value for b in graph.CAC_NHANH],
    ):
        assert buoc in ten, f"thiếu bước {buoc}"


def test_so_do_mermaid_sinh_duoc() -> None:
    so_do = graph.mermaid()
    assert so_do.strip()
    assert "graph TD" in so_do or "flowchart" in so_do


def _canh() -> list[tuple[str, str]]:
    """Các cạnh của sơ đồ, đọc từ Mermaid.

    Mermaid của LangGraph dùng **hai** loại mũi tên: ``-->`` cho cạnh cố định và ``-.->``
    cho cạnh có điều kiện. Chỉ đọc ``-->`` là bỏ sót toàn bộ cạnh rẽ nhánh — và bài kiểm sẽ
    báo sai rằng đồ thị không có đường ra.
    """
    canh: list[tuple[str, str]] = []
    for dong in graph.mermaid().splitlines():
        dong = dong.strip().rstrip(";")
        for mui_ten in ("-.->", "-->"):
            if mui_ten in dong:
                dau, cuoi = dong.split(mui_ten, 1)
                canh.append((dau.strip(), cuoi.strip()))
                break
    return canh


def test_moi_buoc_deu_co_duong_ra() -> None:
    """Bước không có cạnh ra = nhánh cụt = câu hỏi treo khi chạy thật."""
    co_duong_ra = {dau for dau, _cuoi in _canh()}
    for ten in graph.WORKFLOW.get_graph().nodes:
        if ten in {"__start__", "__end__"}:
            continue
        assert ten in co_duong_ra, f"bước {ten} không có đường ra"


def test_khong_buoc_nao_mo_coi() -> None:
    """Bước không xuất hiện ở đầu mút nào = không ai gọi tới."""
    co_mat = {ten for canh in _canh() for ten in canh}
    for ten in graph.WORKFLOW.get_graph().nodes:
        if ten == "__start__":
            continue
        assert ten in co_mat, f"bước {ten} bị mồ côi"


def test_moi_buoc_deu_toi_duoc_buoc_ket_thuc() -> None:
    """Mọi đường đi phải kết thúc ở ``ket_thuc`` — không có nhánh nào thoát ra ngoài."""
    canh = _canh()
    toi_ket_thuc = {dau for dau, cuoi in canh if cuoi == graph.KET_THUC}
    for nhanh in graph.CAC_NHANH:
        assert nhanh.value in toi_ket_thuc, f"nhánh {nhanh.value} không tới bước kết thúc"
    assert graph.HOI_LAI in toi_ket_thuc


# ── Ba đường rẽ đặc biệt ────────────────────────────────────────────────


@pytest.fixture
def gia_neo(monkeypatch: pytest.MonkeyPatch):
    """Thay bước định danh bằng kết quả dựng sẵn, và đếm số lần nhúng."""
    dem = {"nhung": 0, "lan_goi": 0}

    def _dat(**tham_so):
        codes = tham_so.get("codes", [])
        documents = tham_so.get("documents", [])
        entity = tham_so.get("entity")
        ambiguous = tham_so.get("ambiguous", False)
        ma = tham_so.get("ma", codes[0] if codes else "")
        ten_thu_tuc = tham_so.get("ten", "")

        async def fake_resolve(question, *, only_anchors=False, vector=None):
            dem["lan_goi"] += 1
            r = resolve.Resolution(question=question)
            r.codes = list(codes)
            r.documents = list(documents)
            r.entity = entity
            r.entity_ambiguous = ambiguous
            r.ma = ma
            if vector is not None:
                r.dau_vet_vector = resolve.remember_vector(vector)
                r.embedding_used = True
            if ma:
                r.procedure = ProcedureResolution(
                    code=ma, name=ten_thu_tuc or ma, method="vector", confidence=0.8
                )
                r.ten = r.procedure.name
            return r

        monkeypatch.setattr(resolve, "resolve", fake_resolve)
        return dem

    async def fake_embed(text: str) -> list[float]:
        dem["nhung"] += 1
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(embeddings, "embed", fake_embed)
    # Tắt router mô hình: các bài kiểm của đồ thị phải chạy **không cần mạng**. Việc nối mô
    # hình vào luồng có bài kiểm riêng ở ``test_router_wiring.py``.
    monkeypatch.setenv("ROUTER_USE_LLM", "0")
    resolve.reset_vector_cache()
    return _dat



def test_cau_da_co_ma_thi_khong_nhung(monkeypatch: pytest.MonkeyPatch, gia_neo) -> None:
    """Bất biến chi phí, kiểm qua cả đồ thị: câu có mã phải có 0 lần nhúng."""
    dem = gia_neo(codes=["1.001699"])

    async def fake_answer(cau, *, codes=None, limit=20, get_vector=None):
        return GraphEvidence(
            intent="AGENCY",
            title="Cơ quan liên quan",
            rows=[{"vai_tro": "Cơ quan ban hành", "gia_tri": "UBND tỉnh Gia Lai"}],
            columns=(("vai_tro", "Vai trò", False), ("gia_tri", "Cơ quan", True)),
        )

    monkeypatch.setattr(graph_query, "answer", fake_answer)
    ket_qua = _chay("Thủ tục 1.001699 do cơ quan nào ban hành?")
    assert dem["nhung"] == 0
    assert ket_qua["branch"] == Branch.GRAPH.value
    assert ket_qua["outcome"] == Outcome.ANSWERED.value
    assert ket_qua["embedding_used"] is False


def test_cau_thong_ke_cung_khong_nhung(monkeypatch: pytest.MonkeyPatch, gia_neo) -> None:
    dem = gia_neo()

    async def fake_answer(cau, *, codes=None, limit=20, get_vector=None):
        return GraphEvidence(
            intent="STATS_BY_FIELD",
            title="Lĩnh vực nhiều thủ tục nhất",
            rows=[{"linh_vuc": "Hộ tịch", "so_thu_tuc": "12"}],
            columns=(("linh_vuc", "Lĩnh vực", False), ("so_thu_tuc", "Số thủ tục", False)),
        )

    monkeypatch.setattr(graph_query, "answer", fake_answer)
    ket_qua = _chay("Lĩnh vực nào nhiều thủ tục nhất?")
    assert dem["nhung"] == 0
    assert ket_qua["branch"] == Branch.GRAPH.value


def test_khong_nhanh_nao_thi_di_hoi_lai(monkeypatch: pytest.MonkeyPatch, gia_neo) -> None:
    """Nhiều văn bản cùng khớp → router không chọn nhánh → hỏi lại."""
    gia_neo(documents=["a", "b", "c"])
    ket_qua = _chay("Luật Hộ tịch quy định thủ tục nào?")
    assert ket_qua["outcome"] == Outcome.CLARIFY.value
    assert ket_qua["branch"] == ""
    assert len(ket_qua["clarify"]["options"]) == 3


def test_nhanh_tra_rong_thi_tu_choi(monkeypatch: pytest.MonkeyPatch, gia_neo) -> None:
    """Bằng chứng rỗng không được coi là đã trả lời."""
    gia_neo(codes=["1.001699"])

    async def fake_answer(cau, *, codes=None, limit=20, get_vector=None):
        return GraphEvidence(intent="AGENCY", title="Cơ quan liên quan")

    monkeypatch.setattr(graph_query, "answer", fake_answer)
    ket_qua = _chay("Thủ tục 1.001699 do cơ quan nào ban hành?")
    assert ket_qua["branch_signal"] == "empty"
    assert ket_qua["outcome"] == Outcome.ABSTAINED.value


def test_loi_nguon_van_khong_sap(monkeypatch: pytest.MonkeyPatch, gia_neo) -> None:
    gia_neo(codes=["1.001699"])

    async def hong(cau, *, codes=None, limit=20, get_vector=None):
        raise RuntimeError("Neo4j sập")

    monkeypatch.setattr(graph_query, "answer", hong)
    ket_qua = _chay("Thủ tục 1.001699 do cơ quan nào ban hành?")
    assert ket_qua["outcome"] == Outcome.ERROR.value
    assert "Neo4j" in ket_qua["error"]


def test_nhanh_tra_thuoc_tinh(monkeypatch: pytest.MonkeyPatch, gia_neo) -> None:
    gia_neo(codes=["1.001699"])

    async def fake_get_facts(codes):
        return [
            ProcedureFact(
                ma_thu_tuc=codes[0],
                ten_thu_tuc="Cấp Giấy xác nhận khuyết tật",
                cap_thuc_hien=("Cấp xã",),
                co_quan_ban_hanh="Bộ Y tế",
                so_quyet_dinh="1234/QĐ-BYT",
                detail_url="https://dichvucong.gov.vn/1.001699",
            )
        ]

    monkeypatch.setattr(fact_lookup, "get_facts", fake_get_facts)
    ket_qua = _chay("Thủ tục 1.001699 là gì?")
    assert ket_qua["branch"] == Branch.FACT_LOOKUP.value
    assert ket_qua["evidence"][0]["kind"] == "fact"


def test_nhanh_tim_kiem_lai(monkeypatch: pytest.MonkeyPatch, gia_neo) -> None:
    dem = gia_neo(codes=["1.001699"])

    async def fake_hybrid(cau, *, vector, codes=None, **kwargs):
        return RetrievalOutcome(
            candidates=[
                Candidate(
                    chunk_id="c1",
                    procedure_code="1.001699",
                    procedure_name="Cấp Giấy xác nhận khuyết tật",
                    section_type="FEE",
                    title="Lệ phí",
                    content="Không thu lệ phí",
                    detail_url="",
                    score=0.03,
                    source="hybrid",
                    by_keyword=True,
                    by_vector=True,
                )
            ]
        )

    monkeypatch.setattr(hybrid, "hybrid", fake_hybrid)
    ket_qua = _chay("Thủ tục 1.001699 cần hồ sơ gì?")
    assert dem["nhung"] == 1, "câu nội dung có mã **phải** nhúng để tìm đoạn văn"
    assert ket_qua["branch"] == Branch.HYBRID.value
    assert ket_qua["evidence"][0]["kind"] == "chunk"


# ── Kết cục: bảng đổi tín hiệu → kết cục ────────────────────────────────


@pytest.mark.parametrize(
    ("tin_hieu", "mong_doi"),
    [
        ("ok", Outcome.ANSWERED),
        ("empty", Outcome.ABSTAINED),
        ("not_graph", Outcome.ABSTAINED),
        ("need_identity", Outcome.CLARIFY),
        ("clarify", Outcome.CLARIFY),
        ("error", Outcome.ERROR),
    ],
)
def test_bang_doi_tin_hieu_thanh_ket_cuc(tin_hieu: str, mong_doi: Outcome) -> None:
    assert graph.KET_CUC[graph.BranchSignal(tin_hieu)] == mong_doi


def test_ket_cuc_khong_bao_gio_mac_dinh_la_da_tra_loi() -> None:
    """Bước kết thúc phải đổi được tín hiệu lạ về lỗi, không về "đã trả lời"."""
    assert graph.KET_CUC[graph.BranchSignal.ERROR] == Outcome.ERROR
    assert Outcome.ABSTAINED in graph.KET_CUC.values()
