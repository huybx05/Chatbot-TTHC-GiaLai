"""Khoá bốn bộ chuyển bằng chứng (việc 13.2).

Điều quan trọng nhất cần khoá: **cả bốn nhánh trả về cùng một kiểu**. Nếu một bộ chuyển
quên ``kind`` hay ``source``, bước sinh câu trả lời ở việc 13.13 sẽ phải đoán — và đó đúng là
loại lỗi đã làm trang quản trị trắng ba lần khi ba nơi cùng dựng phản hồi.
"""

from __future__ import annotations

import pytest
from backend.app.rag import graph_query
from backend.app.rag.evidence import (
    Branch,
    EvidenceItem,
    EvidenceKind,
    Provenance,
    from_chunks,
    from_fact,
    from_graph,
)
from backend.app.rag.fact_lookup import ProcedureFact
from backend.app.rag.graph_query import GraphEvidence, GraphPart
from backend.app.rag.types import Candidate

#: Cột hiển thị của hình dạng AGENCY — lấy từ bảng quyết định, không chép tay.
COT_AGENCY = graph_query.COLUMNS["AGENCY"]

#: Trường **bắt buộc** phải có ở mọi mục bằng chứng. Hai trường xếp hạng
#: (``keyword_rank``, ``vector_rank``) là tuỳ chọn: chỉ nhánh lai mới có.
TRUONG_BAT_BUOC = set(EvidenceItem.__annotations__) - {"keyword_rank", "vector_rank"}


# ── Dữ liệu mẫu ──────────────────────────────────────────────────────────


def _fact(**ghi_de: object) -> ProcedureFact:
    goc: dict = {
        "ma_thu_tuc": "1.001699",
        "ten_thu_tuc": "Xác định mức độ khuyết tật và cấp Giấy xác nhận khuyết tật",
        "cap_thuc_hien": ("Cấp xã",),
        "co_quan_ban_hanh": "Bộ Y tế",
        "so_quyet_dinh": "1234/QĐ-BYT",
        "detail_url": "https://dichvucong.gov.vn/1.001699",
    }
    goc.update(ghi_de)
    return ProcedureFact(**goc)


def _chunk(**ghi_de: object) -> Candidate:
    goc: dict = {
        "chunk_id": "1.001699-FEE",
        "procedure_code": "1.001699",
        "procedure_name": "Xác định mức độ khuyết tật",
        "section_type": "FEE",
        "title": "Lệ phí",
        "content": "Không thu lệ phí",
        "detail_url": "https://dichvucong.gov.vn/1.001699",
        "score": 0.0123,
        "source": "hybrid",
        "by_keyword": True,
        "by_vector": False,
    }
    goc.update(ghi_de)
    return Candidate(**goc)


def test_fact_mot_muc_du_sau_truong() -> None:
    muc = from_fact(_fact())
    assert len(muc) == 1
    m = muc[0]
    assert m["kind"] == EvidenceKind.FACT.value
    assert m["source"] == Branch.FACT_LOOKUP.value
    assert m["provenance"] == Provenance.POSTGRES.value
    assert m["procedure_code"] == "1.001699"
    assert m["detail_url"] == "https://dichvucong.gov.vn/1.001699"
    assert m["section_type"] == "METADATA"
    assert "Mã thủ tục: 1.001699" in m["content"]
    assert "Cơ quan ban hành: Bộ Y tế" in m["content"]
    assert "Số quyết định: 1234/QĐ-BYT" in m["content"]
    assert m["part_index"] == 0


def test_fact_bo_dong_rong() -> None:
    """Cơ quan và số quyết định có thể rỗng — không được để lại dòng "Cơ quan ban hành: "."""
    muc = from_fact(_fact(co_quan_ban_hanh="", so_quyet_dinh="", cap_thuc_hien=()))
    noi_dung = muc[0]["content"]
    assert "Cơ quan ban hành" not in noi_dung
    assert "Số quyết định" not in noi_dung
    assert "Cấp thực hiện" not in noi_dung
    assert "Mã thủ tục: 1.001699" in noi_dung


# ── Bộ chuyển đoạn văn ───────────────────────────────────────────────────


def test_chunk_giu_hai_co_nguon() -> None:
    muc = from_chunks([_chunk(by_keyword=True, by_vector=True)])
    assert len(muc) == 1
    m = muc[0]
    assert m["kind"] == EvidenceKind.CHUNK.value
    assert m["provenance"] == Provenance.ES_QDRANT.value
    assert m["by_keyword"] is True
    assert m["by_vector"] is True
    assert m["score"] == pytest.approx(0.0123)
    assert m["section_type"] == "FEE"


def test_chunk_bo_muc_khong_co_ma_dinh_danh() -> None:
    """Đoạn không có ``chunk_id`` là đoạn rác — bỏ, không đẩy vào bằng chứng."""
    assert from_chunks([_chunk(chunk_id="")]) == []


def test_chunk_rong_tra_rong() -> None:
    assert from_chunks([]) == []


# ── Bộ chuyển đồ thị ─────────────────────────────────────────────────────


def test_graph_mot_phan_dung_nhan_cot_tieng_viet() -> None:
    ev = GraphEvidence(
        intent="AGENCY",
        title="Cơ quan liên quan",
        subject="Xác định mức độ khuyết tật",
        rows=[{"vai_tro": "Cơ quan ban hành", "gia_tri": "Bộ Y tế"}],
        columns=COT_AGENCY,
        template="AGENCY",
    )
    muc = from_graph(ev)
    assert len(muc) == 1
    m = muc[0]
    assert m["kind"] == EvidenceKind.GRAPH.value
    assert m["provenance"] == Provenance.NEO4J.value
    # Nhãn cột, KHÔNG phải tên khoá thô: ``vai_tro`` là mời mô hình viết ra ``vai_tro``.
    assert m["content"] == "Vai trò: Cơ quan ban hành · Cơ quan: Bộ Y tế"
    assert "vai_tro" not in m["content"]
    assert m["part_index"] == 0
    assert m["procedure_name"] == "Xác định mức độ khuyết tật"


def test_graph_nhieu_phan_giu_nhan_phan() -> None:
    """Câu nhiều ý: mỗi phần phải giữ số thứ tự và tiêu đề, nếu không sẽ bị gộp thành một đoạn."""
    ev = GraphEvidence(
        intent="MULTI",
        title="Nhiều thông tin cho cùng một thủ tục",
        parts=[
            GraphPart(
                intent="AGENCY",
                title="Cơ quan liên quan",
                rows=[{"vai_tro": "Cơ quan ban hành", "gia_tri": "Bộ Y tế"}],
                columns=COT_AGENCY,
            ),
            GraphPart(
                intent="CLASSIFY",
                title="Phân loại thủ tục",
                rows=[
                    {"loai": "Cấp thực hiện", "gia_tri": "Cấp xã"},
                    {"loai": "Lĩnh vực", "gia_tri": "Bảo trợ xã hội"},
                ],
                columns=(("loai", "Loại thông tin", False), ("gia_tri", "Giá trị", False)),
            ),
            GraphPart(
                intent="RESULT",
                title="Kết quả nhận được",
                rows=[{"ket_qua": "Giấy xác nhận khuyết tật (BYT)"}],
                columns=(("ket_qua", "Kết quả nhận được", False),),
            ),
        ],
    )
    muc = from_graph(ev)
    assert len(muc) == 4
    assert [m["part_index"] for m in muc] == [1, 2, 2, 3]
    assert [m["part_title"] for m in muc] == [
        "Cơ quan liên quan",
        "Phân loại thủ tục",
        "Phân loại thủ tục",
        "Kết quả nhận được",
    ]
    assert muc[0]["section_type"] == "AGENCY"
    assert muc[3]["content"] == "Kết quả nhận được: Giấy xác nhận khuyết tật (BYT)"


def test_graph_rong_tra_rong() -> None:
    """Đồ thị từ chối / hỏi lại / thiếu định danh đều không có dòng → bằng chứng rỗng.

    Rỗng ở đây là **thông tin**, không phải lỗi: bước leo thang đọc tín hiệu nhánh chứ
    không đọc độ dài danh sách bằng chứng.
    """
    assert from_graph(GraphEvidence(intent="NOT_GRAPH", title="Câu hỏi về nội dung")) == []
    assert from_graph(GraphEvidence(intent="CLARIFY", title="Cần làm rõ")) == []


# ── Bộ chuyển câu hỏi thường gặp ─────────────────────────────────────────


def _ca_ba_nhanh() -> list[tuple[str, list[EvidenceItem]]]:
    ev = GraphEvidence(
        intent="AGENCY",
        title="Cơ quan liên quan",
        rows=[{"vai_tro": "Cơ quan ban hành", "gia_tri": "Bộ Y tế"}],
        columns=graph_query.COLUMNS["AGENCY"],
        template="AGENCY",
    )
    return [
        ("fact", from_fact(_fact())),
        ("chunk", from_chunks([_chunk()])),
        ("graph", from_graph(ev)),
    ]


def test_ba_nhanh_tra_cung_mot_kieu() -> None:
    for ten, ds in _ca_ba_nhanh():
        assert ds, f"{ten}: không sinh được mục nào để kiểm"
        for m in ds:
            thieu = TRUONG_BAT_BUOC - set(m)
            assert not thieu, f"{ten}: thiếu trường {sorted(thieu)}"


def test_moi_truong_deu_nam_trong_hop_dong() -> None:
    """Không bộ chuyển nào được tự thêm trường lạ ngoài hợp đồng."""
    hop_dong = set(EvidenceItem.__annotations__)
    for ten, ds in _ca_ba_nhanh():
        for m in ds:
            la = set(m) - hop_dong
            assert not la, f"{ten}: trường ngoài hợp đồng {sorted(la)}"


def test_kind_khop_voi_source() -> None:
    """``kind`` và ``source`` phải nhất quán — lệch nhau là bước sinh đọc sai loại."""
    cap_khop = {
        Branch.FACT_LOOKUP.value: EvidenceKind.FACT.value,
        Branch.HYBRID.value: EvidenceKind.CHUNK.value,
        Branch.GRAPH.value: EvidenceKind.GRAPH.value,
        }
    for _ten, ds in _ca_ba_nhanh():
        for m in ds:
            assert m["kind"] == cap_khop[m["source"]]


def test_doan_van_giu_thu_hang_hai_nhanh() -> None:
    """Thứ hạng từng nhánh phải đi qua bộ chuyển, nếu không giao diện không hiện được.

    Cần thứ hạng vì với 541 đoạn, hai nhánh gần như cùng tìm ra mọi đoạn — "cả hai cùng có"
    không phân biệt được đoạn nào do nhánh nào kéo lên.
    """
    tu_khoa = _chunk(chunk_id="c1", score=0.9, keyword_rank=3, vector_rank=None)
    ca_hai = _chunk(chunk_id="c2", score=0.8, keyword_rank=1, vector_rank=12)

    muc = from_chunks([tu_khoa, ca_hai])

    assert muc[0]["keyword_rank"] == 3
    assert muc[0]["vector_rank"] is None
    assert (muc[1]["keyword_rank"], muc[1]["vector_rank"]) == (1, 12)


def test_fact_mang_theo_duong_dan() -> None:
    """Đường dẫn phải nằm trong nội dung bằng chứng.

    Mọi nhánh đều đi qua bộ chuyển này, nên đây là chỗ duy nhất bảo đảm câu trả lời **luôn** có
    link để đối chiếu — kể cả nhánh thuộc tính, nơi trước đây không có URL nào.
    """
    muc = from_fact(_fact(detail_url="https://example.test/tthc/1.001699"))
    assert "Xem chi tiết: https://example.test/tthc/1.001699" in muc[0]["content"]


def test_fact_khong_co_duong_dan_thi_khong_them_dong_rong() -> None:
    muc = from_fact(_fact(detail_url=""))
    assert "Xem chi tiết" not in muc[0]["content"]
