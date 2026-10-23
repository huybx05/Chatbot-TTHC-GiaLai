"""Khoá bảng quyết định của router luật (việc 13.4).

Router là chỗ **quyết định cả lượt đi đâu**, nên mỗi dòng trong bảng phải có bài kiểm riêng.
Bài kiểm chạy **không cần mạng**: dựng thẳng kết quả định danh, không gọi cơ sở dữ liệu.
"""

from __future__ import annotations

import pytest
from backend.app.rag.evidence import Branch
from backend.app.rag.resolve import Resolution
from backend.app.rag.resolver import ProcedureResolution
from backend.app.workflow.router_rules import decide, decide_all
from backend.app.workflow.state import BranchSignal


def _res(
    question: str,
    *,
    codes: list[str] | None = None,
    documents: list[str] | None = None,
    entity: dict[str, str] | None = None,
    entity_ambiguous: bool = False,
    procedure: ProcedureResolution | None = None,
    ma: str = "",
) -> Resolution:
    """Dựng kết quả định danh **bằng tay** — không gọi PostgreSQL / Neo4j / Qdrant."""
    return Resolution(
        question=question,
        codes=codes or [],
        documents=documents or [],
        entity=entity,
        entity_ambiguous=entity_ambiguous,
        procedure=procedure or ProcedureResolution(),
        ma=ma,
    )


# ── Dòng 1: câu nội dung luôn đi tìm kiếm lai ───────────────────────────


@pytest.mark.parametrize(
    "cau",
    [
        "Thủ tục 1.115374 cần hồ sơ gì?",
        "Thủ tục 1.115374 phí bao nhiêu?",
        "Trình tự thực hiện thủ tục 1.115374",
        "Thời hạn giải quyết thủ tục 1.115374 là bao lâu?",
        "Điều kiện thực hiện thủ tục 1.115362",
    ],
)
def test_cau_noi_dung_di_tim_kiem_lai(cau: str) -> None:
    """Kể cả khi **có mã**: đồ thị từ chối câu nội dung, nên đưa vào đó là chắc chắn hỏng."""
    d = decide(_res(cau, codes=["1.115374"], ma="1.115374"))
    assert d.branch == Branch.HYBRID.value
    assert d.confident is True
    assert "nội dung" in d.reason


# ── Dòng 2–4: đã có mã thủ tục ──────────────────────────────────────────


def test_co_ma_va_hoi_quan_he_di_do_thi() -> None:
    d = decide(_res("Thủ tục 1.115374 do cơ quan nào ban hành?", codes=["1.115374"], ma="1.115374"))
    assert d.branch == Branch.GRAPH.value
    assert "mã nêu trực tiếp" in d.reason
    assert "Cơ quan liên quan" in d.reason


@pytest.mark.parametrize(
    "cau",
    [
        "Thủ tục 1.115374 là gì?",
        "Cho tôi thông tin về thủ tục 1.004873",
        "Số quyết định của thủ tục 1.001699 là gì?",
    ],
)
def test_co_ma_va_hoi_thong_tin_dinh_danh_di_tra_thuoc_tinh(cau: str) -> None:
    """``SUBGRAPH`` từng cướp ba câu này vì nó không có từ khoá — nay thì không."""
    d = decide(_res(cau, codes=["1.115374"], ma="1.115374"))
    assert d.branch == Branch.FACT_LOOKUP.value
    assert "định danh" in d.reason


def test_co_ma_nhung_khong_khop_gi_di_tim_kiem_lai() -> None:
    d = decide(_res("Thủ tục 1.115374 có khó làm không?", codes=["1.115374"], ma="1.115374"))
    assert d.branch == Branch.HYBRID.value


def test_ma_tim_theo_ten_duoc_ghi_ro_trong_ly_do() -> None:
    d = decide(
        _res(
            "giấy xác nhận khuyết tật do cơ quan nào ban hành",
            ma="1.001699",
            procedure=ProcedureResolution(code="1.001699", method="vector"),
        )
    )
    assert d.branch == Branch.GRAPH.value
    assert "mã tìm được theo tên" in d.reason


# ── Dòng 5–6: mơ hồ thì hỏi lại ─────────────────────────────────────────


def test_nhieu_van_ban_cung_khop_thi_hoi_lai() -> None:
    d = decide(_res("Luật Hộ tịch quy định thủ tục nào?", documents=["a", "b", "c"]))
    assert d.branch == ""
    assert d.signal == BranchSignal.CLARIFY.value
    assert "3 văn bản" in d.reason
    assert len(d.clarify["options"]) == 3
    assert d.clarify["question"]


def test_nhieu_thuc_the_cung_khop_thi_hoi_lai() -> None:
    d = decide(_res("Bộ Y tế và Bộ Tư pháp ban hành gì", entity_ambiguous=True))
    assert d.branch == ""
    assert d.signal == BranchSignal.CLARIFY.value
    assert "thực thể" in d.reason


def test_nhieu_thu_tuc_cung_khop_ten_thi_hoi_lai_kem_lua_chon() -> None:
    d = decide(
        _res(
            "đổi sổ đỏ bị rách cũ thì cơ quan nào ban hành",
            procedure=ProcedureResolution(
                ambiguous=True,
                alternatives=[
                    ("1.115350", "Cấp lại Giấy chứng nhận", 0.78),
                    ("1.115345", "Cấp đổi Giấy chứng nhận", 0.77),
                ],
            ),
        )
    )
    assert d.branch == ""
    assert d.signal == BranchSignal.CLARIFY.value
    assert [o["value"] for o in d.clarify["options"]] == ["1.115350", "1.115345"]


# ── Dòng 7: khớp quan hệ nhờ văn bản / thực thể / thống kê ──────────────


def test_van_ban_duy_nhat_khop_quan_he_di_do_thi() -> None:
    d = decide(
        _res("Nghị định 102/2024/NĐ-CP là căn cứ của thủ tục nào?", documents=["102/2024/ND CP"])
    )
    assert d.branch == Branch.GRAPH.value
    assert "không cần mã" in d.reason


@pytest.mark.parametrize(
    ("cau", "entity"),
    [
        (
            "Lĩnh vực Hộ tịch có thủ tục nào?",
            {"kind": "linh_vuc", "value": "Hộ tịch", "label": "Hộ tịch"},
        ),
        (
            "Những thủ tục nào thực hiện ở cấp xã?",
            {"kind": "cap", "value": "Cấp xã", "label": "Cấp xã"},
        ),
        (
            "Bộ Tư pháp ban hành những thủ tục nào?",
            {"kind": "co_quan", "value": "Bộ Tư pháp", "label": "Bộ Tư pháp"},
        ),
    ],
)
def test_neo_thuc_the_di_do_thi(cau: str, entity: dict[str, str]) -> None:
    """Thực thể đóng do bộ định danh điền; router chỉ đọc và quyết định."""
    d = decide(_res(cau, entity=entity))
    assert d.branch == Branch.GRAPH.value
    assert "không cần mã" in d.reason


@pytest.mark.parametrize(
    "cau",
    [
        "Lĩnh vực nào nhiều thủ tục nhất?",
        "Cơ quan nào ban hành nhiều thủ tục nhất?",
        "Văn bản nào làm căn cứ cho nhiều thủ tục nhất?",
    ],
)
def test_cau_thong_ke_di_do_thi(cau: str) -> None:
    """Câu thống kê không cần định danh gì, nhưng vẫn là việc của đồ thị."""
    d = decide(_res(cau))
    assert d.branch == Branch.GRAPH.value


# ── Dòng 10: không xác định được ────────────────────────────────────────


@pytest.mark.parametrize(
    "cau", ["thời tiết Gia Lai hôm nay thế nào", "giá vàng hôm nay bao nhiêu", "cách nấu phở bò"]
)
def test_khong_xac_dinh_duoc_thi_tim_kiem_lai_va_khong_chac(cau: str) -> None:
    d = decide(_res(cau))
    assert d.branch == Branch.HYBRID.value
    assert d.confident is False, "đây là chỗ duy nhất luật nhận 'không chắc'"


# ── Bất biến chung ──────────────────────────────────────────────────────


def _moi_kieu() -> list[Resolution]:
    return [
        _res("Thủ tục 1.115374 cần hồ sơ gì?", codes=["1.115374"], ma="1.115374"),
        _res("Thủ tục 1.115374 do cơ quan nào ban hành?", codes=["1.115374"], ma="1.115374"),
        _res("Thủ tục 1.115374 là gì?", codes=["1.115374"], ma="1.115374"),
        _res("Luật Hộ tịch quy định thủ tục nào?", documents=["a", "b"]),
        _res("Bộ Y tế và Bộ Tư pháp ban hành gì", entity_ambiguous=True),
        _res("Bộ Tư pháp ban hành những thủ tục nào?"),
        _res("thời tiết Gia Lai hôm nay thế nào"),
    ]


def test_moi_quyet_dinh_deu_co_ly_do_va_nhanh_hop_le() -> None:
    hop_le = {b.value for b in Branch} | {""}
    for r in _moi_kieu():
        d = decide(r)
        assert d.branch in hop_le, d.branch
        assert d.reason.strip(), "không có quyết định nào được phép im lặng"
        assert d.can_chay == bool(d.branch)


def test_hoi_lai_thi_khong_kem_nhanh() -> None:
    for r in _moi_kieu():
        d = decide(r)
        if d.signal == BranchSignal.CLARIFY.value:
            assert d.branch == ""
            assert d.clarify["question"], "hỏi lại mà không có câu hỏi là vô nghĩa"


# ── Danh sách nhánh để leo thang ────────────────────────────────────────


def test_decide_all_cau_noi_dung_chi_co_tim_kiem_lai() -> None:
    assert decide_all(_res("Thủ tục 1.115374 cần hồ sơ gì?", codes=["1.115374"])) == [
        Branch.HYBRID.value
    ]


def test_decide_all_co_ma_uu_tien_do_thi_roi_tra_thuoc_tinh() -> None:
    ds = decide_all(
        _res("Thủ tục 1.115374 do cơ quan nào ban hành?", codes=["1.115374"], ma="1.115374")
    )
    assert ds[0] == Branch.GRAPH.value
    assert Branch.FACT_LOOKUP.value in ds
    assert ds[-1] == Branch.HYBRID.value


def test_decide_all_khong_ma_chi_co_tim_kiem_lai() -> None:
    assert decide_all(_res("thời tiết Gia Lai hôm nay thế nào")) == [Branch.HYBRID.value]


def test_dai_tu_khong_tien_ngu_thi_hoi_lai() -> None:
    """Router phải hỏi lại, kể cả khi câu có vẻ là câu nội dung."""
    r = _res("Thủ tục này cần những giấy tờ nào?")
    r.needs_antecedent = True
    d = decide(r)
    assert d.branch == ""
    assert d.signal == BranchSignal.CLARIFY.value
    assert "đại từ" in d.reason
