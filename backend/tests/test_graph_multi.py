"""Khoá quy tắc "khi nào ghép nhiều ý".

Câu một ý mà khớp nhiều intent vì từ khoá chồng nhau thì **không** được ghép — nếu
không, người dùng nhận thêm mục họ không hỏi.
"""

from __future__ import annotations

import pytest
from backend.app.rag.graph_query import (
    MAX_PARTS,
    _clauses,
    classify,
    classify_all,
    count_asks,
)


@pytest.mark.parametrize(
    ("cau", "mong_doi"),
    [
        # ── Một ý ────────────────────────────────────────────────────────
        ("Thủ tục 1.115374 do cơ quan nào ban hành?", 1),
        # Ca từng hỏng: khớp HAI intent (SHARED + LEGAL_BASIS) nhưng chỉ MỘT ý.
        ("Thủ tục 1.115374 có thủ tục nào cùng căn cứ pháp lý?", 1),
        ("Thủ tục 1.115374 cần hồ sơ gì?", 1),
        ("Cho tôi mọi quan hệ của thủ tục 1.115374", 1),
        # "làm ở đâu" (nơi nộp) và "mất bao lâu" (thời hạn) là NỘI DUNG, không phải
        # quan hệ → chỉ còn một ý quan hệ.
        (
            "Tôi cần biết thủ tục 1.001699 do đâu ban hành, làm ở đâu và mất bao lâu?",
            1,
        ),
        # ── Nhiều ý ──────────────────────────────────────────────────────
        ("Thủ tục 1.014100 do cơ quan nào ban hành và căn cứ văn bản nào?", 2),
        # Ba ca từng trả 0–1 ý vì KHÔNG có từ hỏi, hoặc chỉ có dấu câu.
        (
            "Cho tôi biết cơ quan ban hành, cấp giải quyết và kết quả của thủ tục 1.001699",
            3,
        ),
        ("Thủ tục 1.001699: cơ quan ban hành? cấp giải quyết? kết quả?", 3),
        ("Nêu rõ thủ tục 1.001699 do cơ quan nào ban hành, cấp thực hiện và kết quả", 3),
        # Câu dài bốn ý. Phần dẫn chuyện cũng chứa tín hiệu nên đếm dư (5) — vô hại,
        # xem docstring ``count_asks``: đếm dư chỉ tốn một lượt phân loại.
        (
            "Thủ tục này do Bộ nào ban hành, cấp nào giải quyết, ai là người có thẩm "
            "quyền ký và làm xong thì nhận được kết quả gì?",
            4,
        ),
    ],
)
def test_dem_menh_de_hoi(cau: str, mong_doi: int) -> None:
    assert count_asks(cau) == mong_doi


def test_ma_thu_tuc_khong_bi_che_doi_boi_dau_cham() -> None:
    """``1.115374`` phải ở nguyên trong **một** mệnh đề, không bị cắt ở dấu chấm.

    Đo được: cắt theo ``[.;:,?!]`` chẻ ``"thu tuc 1"`` + ``"115374 do ai ban hanh"``,
    làm cụm từ khoá vắt qua chỗ cắt không mệnh đề nào khớp.
    """
    menh_de = _clauses("Thủ tục 1.115374 do ai ban hành")
    assert sum("1.115374" in c for c in menh_de) == 1, menh_de
    assert not any(c.strip() == "1" for c in menh_de)


def test_mot_y_khop_nhieu_intent_van_chi_mot_ket_qua() -> None:
    """``classify`` (một ý) trả đúng một spec; ``classify_all`` mới trả nhiều."""
    cau = "Thủ tục 1.115374 có thủ tục nào cùng căn cứ pháp lý?"
    mot = classify(cau, has_code=True, has_document=False)
    assert mot is not None
    nhieu = classify_all(cau, has_code=True, has_document=False)
    assert len(nhieu) > 1, "câu này khớp nhiều intent — đúng như dự đoán"
    assert mot.intent in {s.intent for s in nhieu}


def test_cau_hai_y_tra_ve_hai_intent() -> None:
    cau = "Thủ tục 1.014100 do cơ quan nào ban hành và căn cứ văn bản nào?"
    specs = classify_all(cau, has_code=True, has_document=False)
    ten = {s.intent for s in specs}
    assert "AGENCY" in ten
    assert "LEGAL_BASIS_OF_PROCEDURE" in ten


def test_classify_all_bo_subgraph_khi_da_co_cai_khac() -> None:
    """``SUBGRAPH`` không có từ khoá nên khớp mọi câu — phải bị loại khỏi ghép nhiều ý."""
    specs = classify_all(
        "Thủ tục 1.014100 do cơ quan nào ban hành và căn cứ văn bản nào?",
        has_code=True,
        has_document=False,
    )
    assert "SUBGRAPH" not in {s.intent for s in specs}


def test_classify_all_quay_ve_classify_khi_khong_khop() -> None:
    """Không khớp gì → vẫn trả ``SUBGRAPH`` như hành vi cũ, không trả rỗng."""
    specs = classify_all(
        "Cho tôi mọi quan hệ của thủ tục 1.115374", has_code=True, has_document=False
    )
    assert len(specs) == 1
    assert specs[0].intent == "SUBGRAPH"


def test_classify_all_bi_chan_so_phan() -> None:
    cau = (
        "Thủ tục 1.014100 do Bộ Tư pháp ban hành, cấp nào giải quyết, căn cứ văn bản "
        "nào, nhận được kết quả gì và dành cho đối tượng nào?"
    )
    specs = classify_all(cau, has_code=True, has_document=False)
    assert len(specs) <= MAX_PARTS


def test_cap_giai_quyet_duoc_nhan_la_hoi_ve_cap() -> None:
    """``"cấp giải quyết"`` là cách nói phổ biến nhưng không khớp ``"cấp nào"``.

    Đo được: *"… cơ quan ban hành, cấp giải quyết và kết quả"* chỉ ra 2 phần (thiếu hẳn
    phần cấp) trước khi thêm cụm này vào ``CLASSIFY``.
    """
    specs = classify_all(
        "Cho tôi biết cơ quan ban hành, cấp giải quyết và kết quả của thủ tục 1.001699",
        has_code=True,
        has_document=False,
    )
    ten = {s.intent for s in specs}
    assert {"AGENCY", "CLASSIFY", "RESULT"} <= ten, ten
