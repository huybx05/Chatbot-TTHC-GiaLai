"""Test bộ chunker Giai đoạn 5.

Dùng cả **bản ghi tổng hợp** (để kiểm luật) và **bản ghi thật** trong ``data/json_normalized``
(để kiểm trên dữ liệu cổng thật). Bản ghi thật được bỏ qua nếu chưa crawl.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from data_pipeline.processing.chunker import (
    CHAR_LIMIT,
    SENTINEL_TEXT,
    chunk_record,
    hash_chunk,
    make_chunk_id,
    render_fee,
    render_general_info,
    render_processing_time,
    render_text_section,
)

REPO = Path(__file__).parent.parent.parent
SOURCE = REPO / "data/json_normalized"


def sample_record() -> dict:
    """Bản ghi 29 trường tối thiểu, đủ để sinh chunk."""
    return {
        "ma_thu_tuc": "1.000001",
        "detail_url": "https://dichvucong.gov.vn/thu-tuc-hanh-chinh/abc",
        "formality_id": "abc",
        "ten_thu_tuc": "Thủ tục đăng ký khai sinh",
        "so_quyet_dinh": "100/QĐ-UBND",
        "cap_thuc_hien": "Cấp xã",
        "loai_thu_tuc": "TTHC được luật giao quy định chi tiết",
        "linh_vuc": "Hộ tịch",
        "doi_tuong_thuc_hien": "Công dân Việt Nam",
        "co_quan_co_tham_quyen": "Ủy ban nhân dân cấp xã",
        "dia_chi_tiep_nhan": "Bộ phận một cửa",
        "co_quan_duoc_uy_quyen": "",
        "co_quan_phoi_hop": "",
        "thu_tuc_lien_quan": "Không có thông tin",
        "trinh_tu_thuc_hien": "Bước 1\nNộp hồ sơ tại bộ phận một cửa.",
        "cach_thuc_thuc_hien": "Trực tuyến\t3 Ngày làm việc\tMiễn phí\tNộp qua cổng",
        "thanh_phan_ho_so": "Tên giấy tờ\tSố lượng\nTờ khai\t1 bản chính",
        "can_cu_phap_ly": "Luật Hộ tịch\t60/2014/QH13",
        "co_quan_thuc_hien": "Ủy ban nhân dân cấp xã",
        "yeu_cau_dieu_kien": "Không quy định",
        "ket_qua_xu_ly": "Giấy khai sinh",
        "co_quan_ban_hanh": "Bộ Tư pháp",
        "ngay_cap_nhat": "2026-01-01T00:00:00+00:00",
        "phi": {
            "loai": "MIEN_PHI",
            "so_tien": None,
            "van_ban": [],
            "mo_ta_goc": "",
            "muc_chi_tiet": [],
        },
        "thoi_han": {
            "loai": "SO",
            "moc": [{"gia_tri": 3, "don_vi": "WORKING_DAY"}],
            "nhieu_don_vi": False,
            "muc_chi_tiet": [
                {
                    "gia_tri": 3,
                    "don_vi": "WORKING_DAY",
                    "dieu_kien": "Nhận đủ hồ sơ hợp lệ",
                    "hinh_thuc": ["Trực tuyến"],
                }
            ],
        },
        "trang_thai": "ACTIVE",
        "domain_group": "11. TU_PHAP_BO_TRO",
        "content_hash": "abc123",
        "ngay_crawl": "2026-10-02T00:00:00+00:00",
    }


def _read_real(ma: str) -> dict:
    """Đọc bản ghi thật, bỏ qua test nếu chưa crawl."""
    p = next(SOURCE.rglob(f"{ma}.json"), None)
    if p is None:
        pytest.skip(f"chưa có {ma} trong data/json_normalized")
    return json.loads(p.read_text(encoding="utf-8"))


# ─────────────────────── CẤU TRÚC CHUNG ───────────────────────


def test_chunks_all_9_sections_for_full_record() -> None:
    chunks = chunk_record(sample_record())
    loai = {c["section_type"] for c in chunks}
    assert loai == {
        "GENERAL_INFO",
        "STEPS",
        "SUBMISSION_METHOD",
        "REQUIRED_DOCUMENTS",
        "LEGAL_BASIS",
        "RESULT",
        "REQUIREMENTS",
        "FEE",
        "PROCESSING_TIME",
    }


def test_no_procedure_code_makes_no_chunk() -> None:
    b = sample_record()
    b["ma_thu_tuc"] = ""
    assert chunk_record(b) == []


def test_chunk_id_format_and_ascending_order() -> None:
    """``{procedure_code}:{section_type}:{chunk_order}`` với chunk_order bắt đầu từ 1."""
    assert make_chunk_id("1.2", "STEPS", 1) == "1.2:STEPS:1"
    chunks = chunk_record(sample_record())
    for c in chunks:
        assert c["chunk_id"] == f"{c['procedure_code']}:{c['section_type']}:{c['chunk_order']}"
    # Trong mỗi section, chunk_order phải là 1..n không nhảy cóc
    theo: dict[str, list[int]] = {}
    for c in chunks:
        theo.setdefault(c["section_type"], []).append(c["chunk_order"])
    for s, ds in theo.items():
        assert ds == list(range(1, len(ds) + 1)), f"{s}: {ds}"


def test_chunk_id_unique_within_record() -> None:
    chunks = chunk_record(sample_record())
    ds = [c["chunk_id"] for c in chunks]
    assert len(ds) == len(set(ds))


def test_every_chunk_inherits_record_metadata() -> None:
    """Metadata kế thừa 100% — không phân loại lại từng chunk."""
    b = sample_record()
    for c in chunk_record(b):
        assert c["procedure_code"] == b["ma_thu_tuc"]
        assert c["domain_group"] == b["domain_group"]
        assert c["source_field"] == b["linh_vuc"]
        assert c["cap_thuc_hien"] == b["cap_thuc_hien"]
        assert c["detail_url"] == b["detail_url"]
        assert c["content_hash"] == b["content_hash"]
        assert c["ten_thu_tuc"] == b["ten_thu_tuc"]


def test_char_count_matches_text_length() -> None:
    for c in chunk_record(sample_record()):
        assert c["char_count"] == len(c["text"])


# ─────────────────────── HEADER ───────────────────────


def test_first_chunk_header_has_4_lines() -> None:
    chunk = next(c for c in chunk_record(sample_record()) if c["section_type"] == "GENERAL_INFO")
    dong = chunk["text"].split("\n")
    assert dong[0].startswith("Tên thủ tục: ")
    assert "Lĩnh vực: Hộ tịch · Cấp thực hiện: Cấp xã" in chunk["text"]
    assert "Nguồn: https://dichvucong.gov.vn/thu-tuc-hanh-chinh/abc" in chunk["text"]
    assert "\n---\n" in chunk["text"]


def test_header_keeps_procedure_name_verbatim() -> None:
    """Không viết hoa lại, không cắt ngắn, không thêm dấu câu."""
    b = sample_record()
    b["ten_thu_tuc"] = "thủ tục  ĐĂNG   ký khai sinh (bản có dấu ngoặc)"
    chunk = chunk_record(b)[0]
    assert b["ten_thu_tuc"] in chunk["text"]


def test_continuation_chunk_uses_compact_header() -> None:
    """Chunk thứ 2 trở đi dùng header gọn — không lặp `detail_url`."""
    b = sample_record()
    b["thanh_phan_ho_so"] = "\n".join(f"Giấy tờ số {i} " + "x" * 600 for i in range(12))
    chunks = [c for c in chunk_record(b) if c["section_type"] == "REQUIRED_DOCUMENTS"]
    assert len(chunks) > 1
    assert "Nguồn:" in chunks[0]["text"]
    for c in chunks[1:]:
        assert "Nguồn:" not in c["text"]
        assert "Thủ tục: 1.000001 ·" in c["text"]


# ─────────────────────── TRẦN KÝ TỰ ───────────────────────


def test_no_chunk_over_limit_for_huge_section() -> None:
    """Một dòng 20.000 ký tự vẫn phải bị cắt xuống dưới trần."""
    b = sample_record()
    b["trinh_tu_thuc_hien"] = "T" * 20000
    chunks = chunk_record(b)
    for c in chunks:
        assert c["char_count"] <= CHAR_LIMIT, f"{c['chunk_id']} = {c['char_count']}"


def test_limit_includes_header() -> None:
    """Trần áp cho `header + thân`, không chỉ thân — đây là bug đã gặp thật."""
    b = sample_record()
    b["ten_thu_tuc"] = "Tên rất dài " + "y" * 3000
    b["trinh_tu_thuc_hien"] = "\n".join("đoạn " + "z" * 900 for _ in range(30))
    for c in chunk_record(b):
        assert c["char_count"] <= CHAR_LIMIT


def test_soft_margin_keeps_last_unit() -> None:
    """Vượt trần chỉ vì MỘT đơn vị cuối thì gộp luôn, không tách chunk vụn.

    Bảng 4.400 + hàng cuối 300 = 4.700 nhưng vẫn phải là MỘT chunk (đã trừ header).
    """
    b = sample_record()
    b["linh_vuc"] = "X"  # header ngắn để dễ tính
    b["ten_thu_tuc"] = "T"
    b["cap_thuc_hien"] = "C"
    b["detail_url"] = "u"
    # 9 hàng × 480 + 1 hàng 200, tổng thân ~4.520 nhưng chỉ vượt do hàng cuối
    hang = ["h" * 480 for _ in range(9)] + ["k" * 60]
    b["thanh_phan_ho_so"] = "\n".join(hang)
    chunks = [c for c in chunk_record(b) if c["section_type"] == "REQUIRED_DOCUMENTS"]
    assert len(chunks) == 1, f"phải giữ 1 chunk, đang là {len(chunks)}"


def test_single_unit_over_limit_must_split() -> None:
    """Biên mềm KHÔNG áp cho một đơn vị đơn lẻ dài hơn trần."""
    b = sample_record()
    b["trinh_tu_thuc_hien"] = "c" * 12000
    chunks = [c for c in chunk_record(b) if c["section_type"] == "STEPS"]
    assert len(chunks) >= 3
    for c in chunks:
        assert c["char_count"] <= CHAR_LIMIT


# ─────────────────────── SENTINEL ───────────────────────


def test_sentinel_becomes_not_recorded_phrase() -> None:
    """KHÔNG để nguyên "Không có thông tin"; KHÔNG bỏ trường khỏi chunk."""
    b = sample_record()
    b["thu_tuc_lien_quan"] = "Không có thông tin"
    b["yeu_cau_dieu_kien"] = "Không quy định"
    b["ket_qua_xu_ly"] = "Không có."
    chunks = chunk_record(b)
    chung = "\n".join(c["text"] for c in chunks)
    assert SENTINEL_TEXT in chung
    assert "Không có thông tin" not in chung
    assert "Không quy định" not in chung
    # Trường vẫn phải có mặt trong GENERAL_INFO (kèm câu sentinel)
    tt = next(c for c in chunks if c["section_type"] == "GENERAL_INFO")
    assert "Thủ tục hành chính liên quan: " + SENTINEL_TEXT in tt["text"]


def test_sentinel_still_produces_requirements_and_result_chunks() -> None:
    """Sentinel KHÔNG được bỏ trường — nếu bỏ thì LLM trả lời "không có" là khẳng định sai."""
    b = sample_record()
    b["yeu_cau_dieu_kien"] = "Không quy định"
    b["ket_qua_xu_ly"] = "Không có thông tin"
    loai = {c["section_type"] for c in chunk_record(b)}
    assert "REQUIREMENTS" in loai
    assert "RESULT" in loai


def test_unknown_fee_makes_no_chunk() -> None:
    b = sample_record()
    b["phi"] = {
        "loai": "CHUA_XAC_DINH",
        "so_tien": None,
        "van_ban": [],
        "mo_ta_goc": "",
        "muc_chi_tiet": [],
    }
    assert "FEE" not in {c["section_type"] for c in chunk_record(b)}


def test_unknown_processing_time_makes_no_chunk() -> None:
    b = sample_record()
    b["thoi_han"] = {"loai": "CHUA_XAC_DINH", "moc": [], "nhieu_don_vi": False, "muc_chi_tiet": []}
    assert "PROCESSING_TIME" not in {c["section_type"] for c in chunk_record(b)}


def test_affirmative_sentence_not_turned_into_sentinel() -> None:
    """ "Không có yêu cầu, điều kiện" là KHẲNG ĐỊNH, không phải "chưa ghi nhận"."""
    b = sample_record()
    b["yeu_cau_dieu_kien"] = "Không có yêu cầu, điều kiện"
    chunk = next(c for c in chunk_record(b) if c["section_type"] == "REQUIREMENTS")
    assert "Không có yêu cầu, điều kiện" in chunk["text"]
    assert SENTINEL_TEXT not in chunk["text"]


# ─────────────────────── PHÍ ───────────────────────


def test_fee_renders_from_detail_items_not_single_amount() -> None:
    """Chỉ đọc `so_tien` thì mất hết điều kiện — phải có đủ mọi mức."""
    b = sample_record()
    b["phi"] = {
        "loai": "SO_TIEN",
        "so_tien": 500000,
        "van_ban": [],
        "mo_ta_goc": "",
        "muc_chi_tiet": [
            {"so_tien": 500000, "dieu_kien": "Cấp lần đầu"},
            {"so_tien": 21500000, "dieu_kien": "Chuyển nhượng doanh nghiệp"},
        ],
    }
    than = render_fee(b)[0]
    assert "500.000 đồng — Cấp lần đầu" in than
    assert "21.500.000 đồng — Chuyển nhượng doanh nghiệp" in than


def test_fee_item_without_condition_has_no_dangling_dash() -> None:
    """`dieu_kien` rỗng là HỢP LỆ khi có số tiền — 35/1909 bản ghi ở ca này."""
    b = sample_record()
    b["phi"] = {
        "loai": "SO_TIEN",
        "so_tien": 20000,
        "van_ban": [],
        "mo_ta_goc": "",
        "muc_chi_tiet": [{"so_tien": 20000, "dieu_kien": ""}],
    }
    than = render_fee(b)[0]
    assert "20.000 đồng" in than
    assert "— \n" not in than + "\n"
    assert not than.rstrip().endswith("—")
    assert "mức phí phổ biến" in than


def test_fee_null_amount_condition_is_only_info() -> None:
    b = sample_record()
    b["phi"] = {
        "loai": "THEO_QUY_DINH_CHUNG",
        "so_tien": None,
        "van_ban": [],
        "mo_ta_goc": "",
        "muc_chi_tiet": [
            {"so_tien": None, "dieu_kien": "Theo quy định của Bộ tài chính"},
        ],
    }
    than = render_fee(b)[0]
    assert "- Theo quy định của Bộ tài chính" in than


def test_free_fee_states_free_explicitly() -> None:
    than = render_fee(sample_record())[0]
    assert "Miễn phí" in than
    assert "miễn phí" in than


def test_fee_by_document_states_document_code() -> None:
    b = sample_record()
    b["phi"] = {
        "loai": "THEO_VAN_BAN",
        "so_tien": None,
        "van_ban": ["10/2024/TT-BTC"],
        "mo_ta_goc": "Thực hiện theo Thông tư số 10/2024/TT-BTC",
        "muc_chi_tiet": [],
    }
    than = render_fee(b)[0]
    assert "10/2024/TT-BTC" in than


def test_fee_keeps_all_levels_for_real_record() -> None:
    """Nghiệm thu: `1.014257` phải có đủ 10 mức, `1.004376` đủ 8 mức."""
    for ma, mong_doi in (("1.014257", 10), ("1.004376", 8)):
        b = _read_real(ma)
        assert len(b["phi"]["muc_chi_tiet"]) == mong_doi
        chunks = [c for c in chunk_record(b) if c["section_type"] == "FEE"]
        assert len(chunks) >= 1
        so_muc = sum(len([x for x in c["text"].split("\n") if x.startswith("- ")]) for c in chunks)
        assert so_muc == mong_doi, f"{ma}: chỉ còn {so_muc}/{mong_doi} mức"


# ─────────────────────── THỜI HẠN ───────────────────────


def test_processing_time_renders_detail_items_with_method() -> None:
    than = render_processing_time(sample_record())[0]
    assert "3 Ngày làm việc" in than
    assert "(nộp Trực tuyến)" in than
    assert "Nhận đủ hồ sơ hợp lệ" in than


def test_processing_time_units_translated_to_vietnamese() -> None:
    b = sample_record()
    b["thoi_han"]["muc_chi_tiet"] = [
        {"gia_tri": 1, "don_vi": "HOUR", "dieu_kien": "Nhận qua bưu chính", "hinh_thuc": []},
        {"gia_tri": 20, "don_vi": "DAY", "dieu_kien": "Trường hợp khác", "hinh_thuc": []},
        {"gia_tri": 2, "don_vi": "MONTH", "dieu_kien": "Trường hợp đặc biệt", "hinh_thuc": []},
    ]
    than = render_processing_time(b)[0]
    assert "1 Giờ" in than
    assert "20 Ngày" in than
    assert "2 Tháng" in than
    assert "HOUR" not in than


def test_processing_time_multiple_units_warns_not_cumulative() -> None:
    b = sample_record()
    b["thoi_han"]["nhieu_don_vi"] = True
    than = render_processing_time(b)[0]
    assert "không cộng dồn" in than


def test_processing_time_keeps_all_6_milestones_for_real_record() -> None:
    """Nghiệm thu: `3.000242` phải có đủ 6 mốc kèm hình thức nộp."""
    b = _read_real("3.000242")
    chunks = [c for c in chunk_record(b) if c["section_type"] == "PROCESSING_TIME"]
    milestone_count = sum(
        len([x for x in c["text"].split("\n") if x.startswith("- ")]) for c in chunks
    )
    assert milestone_count == len(b["thoi_han"]["muc_chi_tiet"]) == 6


def test_processing_time_distinguishes_milestones_with_same_days() -> None:
    """`2.000115` có nhiều mốc cùng 3 Ngày làm việc nhưng điều kiện khác nhau."""
    b = _read_real("2.000115")
    chunks = [c for c in chunk_record(b) if c["section_type"] == "PROCESSING_TIME"]
    chung = "\n".join(c["text"] for c in chunks)
    three_day_count = chung.count("- 3 Ngày làm việc")
    assert three_day_count >= 4, "đọc `moc` phẳng thì các mốc này nhìn giống hệt nhau"
    # Mỗi mốc 3 ngày phải kèm một điều kiện KHÁC nhau
    for c in chunks:
        for dong in c["text"].split("\n"):
            if dong.startswith("- 3 Ngày làm việc"):
                assert " — " in dong or "(nộp" in dong


# ─────────────────────── BẢNG ───────────────────────


def test_table_joins_cells_within_row() -> None:
    """Mỗi HÀNG thành một dòng, các ô nối bằng ` · ` — không tách ô thành dòng riêng."""
    b = sample_record()
    b["can_cu_phap_ly"] = "Luật Hộ tịch\t60/2014/QH13\nLuật Cư trú\t81/2006/QH11"
    chunk = next(c for c in chunk_record(b) if c["section_type"] == "LEGAL_BASIS")
    assert "Luật Hộ tịch · 60/2014/QH13" in chunk["text"]
    assert "Luật Cư trú · 81/2006/QH11" in chunk["text"]
    # Không còn dòng nào CHỈ chứa mã văn bản
    for dong in chunk["text"].split("\n"):
        assert dong.strip() != "60/2014/QH13"


def test_table_header_row_is_dropped() -> None:
    b = sample_record()
    b["can_cu_phap_ly"] = "Tên văn bản pháp lý\tMã văn bản\nLuật Hộ tịch\t60/2014/QH13"
    chunk = next(c for c in chunk_record(b) if c["section_type"] == "LEGAL_BASIS")
    assert "Tên văn bản pháp lý" not in chunk["text"]


def test_table_keeps_content_without_losing_cells() -> None:
    b = sample_record()
    b["thanh_phan_ho_so"] = "Tờ khai\t\t1 bản chính"
    chunk = next(c for c in chunk_record(b) if c["section_type"] == "REQUIRED_DOCUMENTS")
    assert "Tờ khai · 1 bản chính" in chunk["text"]


# ─────────────────────── KẾT QUẢ ───────────────────────


def test_short_result_gets_context_prefix() -> None:
    """`RESULT` chỉ 14 ký tự thì vector rất yếu — phải có câu dẫn."""
    chunk = next(c for c in chunk_record(sample_record()) if c["section_type"] == "RESULT")
    assert "Kết quả người dân nhận được khi hoàn thành thủ tục: Giấy khai sinh." in chunk["text"]


def test_result_verbatim_still_in_chunk() -> None:
    b = sample_record()
    b["ket_qua_xu_ly"] = "Giấy xác nhận tình trạng hôn nhân"
    chunk = next(c for c in chunk_record(b) if c["section_type"] == "RESULT")
    assert b["ket_qua_xu_ly"] in chunk["text"]


# ─────────────────────── BƯỚC ───────────────────────


def test_boundary_priority_prefers_step_labels() -> None:
    """Có `Bước N` thì cắt ở ranh giới bước, không cắt giữa bước."""
    b = sample_record()
    b["trinh_tu_thuc_hien"] = "\n".join(f"Bước {i}\n" + "nội dung " * 200 for i in range(1, 9))
    chunks = [c for c in chunk_record(b) if c["section_type"] == "STEPS"]
    assert len(chunks) > 1
    for c in chunks:
        assert c["char_count"] <= CHAR_LIMIT


def test_boundary_priority_prefers_numbered_items() -> None:
    b = sample_record()
    b["trinh_tu_thuc_hien"] = "\n".join(f"{i}. " + "x" * 700 for i in range(1, 12))
    chunks = [c for c in chunk_record(b) if c["section_type"] == "STEPS"]
    for c in chunks:
        assert c["char_count"] <= CHAR_LIMIT
    # Mỗi chunk (trừ chunk đầu) phải mở đầu thân bằng một mục đánh số
    for c in chunks:
        than = c["text"].split("---\n")[-1]
        assert than.lstrip()[0].isdigit()


# ─────────────────────── TẤT ĐỊNH ───────────────────────


def test_running_twice_gives_identical_result() -> None:
    """`chunk_id` ổn định — cùng nội dung thì cùng ID giữa các lần chạy."""
    b = sample_record()
    a1 = chunk_record(b)
    a2 = chunk_record(b)
    assert [c["chunk_id"] for c in a1] == [c["chunk_id"] for c in a2]
    assert [hash_chunk(c) for c in a1] == [hash_chunk(c) for c in a2]


def test_chunk_hash_changes_with_content() -> None:
    b1 = sample_record()
    b2 = sample_record()
    b2["ket_qua_xu_ly"] = "Giấy khai sinh bản sao"
    c1 = next(c for c in chunk_record(b1) if c["section_type"] == "RESULT")
    c2 = next(c for c in chunk_record(b2) if c["section_type"] == "RESULT")
    assert hash_chunk(c1) != hash_chunk(c2)


# ─────────────────────── GENERAL_INFO ───────────────────────


def test_general_info_contains_identity_fields() -> None:
    than = render_general_info(sample_record())[0]
    for nhan in ("Mã thủ tục:", "Tên thủ tục:", "Số quyết định:", "Cấp thực hiện:", "Lĩnh vực:"):
        assert nhan in than


def test_general_info_always_exists_even_when_fields_empty() -> None:
    b = sample_record()
    for k in (
        "so_quyet_dinh",
        "cap_thuc_hien",
        "loai_thu_tuc",
        "linh_vuc",
        "doi_tuong_thuc_hien",
        "co_quan_co_tham_quyen",
        "dia_chi_tiep_nhan",
        "co_quan_thuc_hoan",
        "co_quan_ban_hanh",
        "trang_thai",
        "ngay_cap_nhat",
        "ten_thu_tuc",
    ):
        if k in b:
            b[k] = ""
    b["ma_thu_tuc"] = "1.000001"  # mã vẫn phải có, không thì không sinh chunk
    chunks = chunk_record(b)
    assert "GENERAL_INFO" in {c["section_type"] for c in chunks}


def test_empty_section_makes_no_empty_chunk() -> None:
    b = sample_record()
    b["yeu_cau_dieu_kien"] = ""
    b["ket_qua_xu_ly"] = ""
    loai = {c["section_type"] for c in chunk_record(b)}
    assert "REQUIREMENTS" not in loai
    assert "RESULT" not in loai


def test_render_text_section_returns_empty_for_blank_value() -> None:
    for value in ("", "   ", None):
        b = sample_record()
        b["ket_qua_xu_ly"] = value
        assert render_text_section(b, "ket_qua_xu_ly", "RESULT") == []
