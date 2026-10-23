"""Khoá lại hành vi "neo thực thể" và "hỏi lại" của nhánh Graph.

Test chạy **không cần Neo4j**: chỉ gọi các hàm thuần (khớp từ khoá, khớp thực thể,
chuẩn hoá nhãn). Phần truy vấn Cypher được kiểm riêng trên dữ liệu thật.
"""

from __future__ import annotations

import pytest
from backend.app.rag.graph_query import (
    INTENTS,
    EntityMatch,
    Vocabulary,
    _co_khop_tu_khoa,
    _khop_cum,
    _khop_tu_khoa,
    _match_entities,
    _nhan_gia_tri,
    _tokens,
    classify,
    intent_thieu_dinh_danh,
)


def _spec(intent: str):
    """Lấy spec theo tên — để test không phụ thuộc thứ tự trong bảng."""
    return next(s for s in INTENTS if s.intent == intent)


TU_DIEN = Vocabulary(
    run_id="test",
    cap=("Cấp bộ", "Cấp tỉnh", "Cấp xã"),
    linh_vuc=("Hộ tịch", "Đất đai", "Dược phẩm"),
    trang_thai=("ACTIVE",),
    domain_group=(
        ("11. TU_PHAP_BO_TRO", "Tư pháp và Bổ trợ tư pháp"),
        ("15. Y_TE_SUC_KHOE", "Y tế và Sức khỏe"),
    ),
    documents=(),
    co_quan=("Bộ Tư pháp", "Bộ Y tế", "UBND tỉnh Gia Lai"),
)


# ── Khớp cụm phải ĐỨNG LIỀN NHAU ─────────────────────────────────────────


def test_khop_cum_doi_lien_nhau() -> None:
    """Ba từ ở ba chỗ khác nhau không được coi là cụm "thủ tục nào"."""
    cau = _tokens("để làm thủ tục mua nhà, cơ quan nào có thẩm quyền")
    assert not _khop_cum(cau, "thu tuc nao")
    assert _khop_cum(cau, "co quan nao")


def test_each_of_nhan_ca_hai_cach_noi_nhieu_nhat() -> None:
    """``"nhiều thủ tục nhất"`` và ``"nhiều nhất"`` đều phải khớp STATS."""
    spec = _spec("STATS_BY_FIELD")
    assert _khop_tu_khoa(spec, _tokens("Lĩnh vực nào nhiều thủ tục nhất?"))
    assert _khop_tu_khoa(spec, _tokens("Lĩnh vực nào nhiều nhất?"))
    # Không nhắc lĩnh vực thì không khớp.
    assert not _khop_tu_khoa(spec, _tokens("Cơ quan nào nhiều nhất?"))


# ── Khớp thực thể đóng: 0 token ──────────────────────────────────────────


def test_match_entities_lay_chuoi_dai_nhat() -> None:
    """``UBND tỉnh Gia Lai`` thắng ``Bộ Y tế`` khi câu chỉ nêu một cơ quan."""
    duy_nhat, mo_ho = _match_entities("UBND tỉnh Gia Lai ban hành thủ tục nào", TU_DIEN)
    assert mo_ho == []
    assert duy_nhat is not None
    assert duy_nhat.kind == "co_quan"
    assert duy_nhat.value == "UBND tỉnh Gia Lai"


def test_match_entities_linh_vuc() -> None:
    duy_nhat, mo_ho = _match_entities("Lĩnh vực Hộ tịch có thủ tục nào", TU_DIEN)
    assert mo_ho == []
    assert duy_nhat is not None
    assert duy_nhat.kind == "linh_vuc"
    assert duy_nhat.value == "Hộ tịch"


def test_match_entities_nhan_slug_domain_group() -> None:
    """Nhóm phải khớp bằng **nhãn**, không phải slug."""
    duy_nhat, _ = _match_entities("Nhóm Tư pháp và Bổ trợ tư pháp gồm gì", TU_DIEN)
    assert duy_nhat is not None
    assert duy_nhat.kind == "domain_group"
    assert duy_nhat.value == "11. TU_PHAP_BO_TRO"


def test_match_entities_khong_co_thi_rong() -> None:
    assert _match_entities("Thủ tục 1.115374 cần hồ sơ gì", TU_DIEN) == (None, [])


# ── Chọn intent: cần mã vs cần thực thể ─────────────────────────────────


def test_uu_tien_ma_thu_tuc_hon_thuc_the() -> None:
    """Có mã thì câu hỏi về cấp của **thủ tục đó** phải vào CLASSIFY, không phải BY_LEVEL."""
    spec = classify(
        "Thủ tục 1.115374 được thực hiện ở cấp tỉnh không?",
        has_code=True,
        has_document=False,
        entity=EntityMatch("cap", "Cấp tỉnh", "Cấp tỉnh"),
    )
    assert spec is not None
    assert spec.intent == "CLASSIFY"


def test_khong_ma_thi_dung_duoc_neo_thuc_the() -> None:
    """Không có mã nhưng có cơ quan → vẫn trả lời được (đây là điểm khác fact_lookup)."""
    spec = classify(
        "Bộ Tư pháp ban hành những thủ tục nào?",
        has_code=False,
        has_document=False,
        entity=EntityMatch("co_quan", "Bộ Tư pháp", "Bộ Tư pháp"),
    )
    assert spec is not None
    assert spec.intent == "PROCEDURES_BY_AGENCY"


def test_neo_linh_vuc_va_cap() -> None:
    linh_vuc = classify(
        "Lĩnh vực Đất đai có thủ tục nào?",
        has_code=False,
        has_document=False,
        entity=EntityMatch("linh_vuc", "Đất đai", "Đất đai"),
    )
    assert linh_vuc is not None
    assert linh_vuc.intent == "PROCEDURES_BY_FIELD"

    cap = classify(
        "Thủ tục nào thực hiện ở cấp xã?",
        has_code=False,
        has_document=False,
        entity=EntityMatch("cap", "Cấp xã", "Cấp xã"),
    )
    assert cap is not None
    assert cap.intent == "PROCEDURES_BY_LEVEL"


def test_thong_ke_khong_can_tham_so_nao() -> None:
    spec = classify(
        "Lĩnh vực nào nhiều thủ tục nhất?",
        has_code=False,
        has_document=False,
        entity=None,
    )
    assert spec is not None
    assert spec.intent == "STATS_BY_FIELD"


def test_thieu_dinh_danh_bao_dung_loai() -> None:
    """Câu hỏi cơ quan thiếu mã → phải báo AGENCY, không phải "không khớp loại nào"."""
    spec = intent_thieu_dinh_danh(
        "Cơ quan nào có thẩm quyền giải quyết thủ tục này?",
        has_code=False,
        has_document=False,
    )
    assert spec is not None
    assert spec.intent == "AGENCY"


def test_subgraph_phai_co_tu_khoa() -> None:
    """``SUBGRAPH`` **phải** có từ khoá riêng, không được khớp mọi câu.

    Đo được: khi hình dạng này không có từ khoá nào, câu *"Thủ tục 1.115374 là gì?"* (hỏi
    thông tin định danh) bị nhận thành "hỏi toàn cảnh quan hệ" và đi nhầm nhánh — 4/32 câu
    định tuyến sai vì đúng lý do này.
    """
    assert _co_khop_tu_khoa(_spec("SUBGRAPH"))
    assert _khop_tu_khoa(_spec("SUBGRAPH"), _tokens("cho tôi mọi quan hệ của thủ tục này"))
    assert not _khop_tu_khoa(_spec("SUBGRAPH"), _tokens("thủ tục 1.115374 là gì"))


# ── Chuẩn hoá nhãn hiển thị ─────────────────────────────────────────────


def test_gia_tri_dang_list_duoc_doi_thanh_nhan() -> None:
    """``collect(DISTINCT type(e))`` trả list — phải ra "Cơ quan ban hành", không ra repr."""
    ket_qua = _nhan_gia_tri(
        "PROCEDURES_BY_AGENCY", "vai_tro", ["BAN_HANH_BOI", "PHOI_HOP"], TU_DIEN
    )
    assert ket_qua == "Cơ quan ban hành, Cơ quan phối hợp"


def test_slug_domain_group_doi_thanh_nhan() -> None:
    """Slug ``'11. TU_PHAP_BO_TRO'`` không được lộ ra câu trả lời."""
    ket_qua = _nhan_gia_tri("PROCEDURES_BY_GROUP", "nhom", "11. TU_PHAP_BO_TRO", TU_DIEN)
    assert ket_qua == "Tư pháp và Bổ trợ tư pháp"


def test_slug_la_thi_lam_sach_tai_cho() -> None:
    """Slug không có trong từ điển vẫn phải đọc được, không lộ nguyên dạng."""
    ket_qua = _nhan_gia_tri("PROCEDURES_BY_GROUP", "nhom", "99. NONG_NGHIEP", TU_DIEN)
    assert ket_qua == "Nong nghiep" or "Nong nghiep" in ket_qua


@pytest.mark.parametrize(
    ("kind", "cau", "mong_doi"),
    [
        ("co_quan", "Bộ Y tế ban hành thủ tục nào", "PROCEDURES_BY_AGENCY"),
        ("linh_vuc", "Lĩnh vực Dược phẩm có gì", "PROCEDURES_BY_FIELD"),
        ("cap", "Cấp bộ có thủ tục nào", "PROCEDURES_BY_LEVEL"),
        ("domain_group", "Nhóm Y tế và Sức khỏe có gì", "PROCEDURES_BY_GROUP"),
    ],
)
def test_moi_loai_neo_deu_chon_dung_template(kind: str, cau: str, mong_doi: str) -> None:
    entity, mo_ho = _match_entities(cau, TU_DIEN)
    assert mo_ho == []
    assert entity is not None
    assert entity.kind == kind
    spec = classify(cau, has_code=False, has_document=False, entity=entity)
    assert spec is not None
    assert spec.intent == mong_doi
