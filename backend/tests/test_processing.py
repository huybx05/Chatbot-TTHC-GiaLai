"""Test chuẩn hóa và kiểm định dữ liệu (Giai đoạn 4).

Không đọc ``data/json/`` thật — dùng bản ghi dựng tại chỗ để test chạy nhanh và độc lập
với dữ liệu đang thay đổi.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from data_pipeline.crawler.transform import compute_content_hash
from data_pipeline.processing.normalizer import (
    fields_needing_normalization,
    is_sentinel,
    normalize_record,
    normalize_text,
    normalize_unicode,
    normalize_whitespace,
)
from data_pipeline.processing.validator import (
    FIELD_SCHEMA,
    REQUIRED_FIELDS,
    field_coverage,
    validate_cross_file,
    validate_record,
)


def sample_record() -> dict:
    """Bản ghi 29 trường hợp lệ, dùng làm gốc cho các test."""
    return {
        "ma_thu_tuc": "1.000001",
        "detail_url": "https://dichvucong.gov.vn/thu-tuc-hanh-chinh/abc",
        "formality_id": "019d2bf7-9660-707e-97b1-ef8876f54d3b",
        "ten_thu_tuc": "Thủ tục thử nghiệm",
        "so_quyet_dinh": "123/QĐ-BTP",
        "cap_thuc_hien": "Cấp tỉnh",
        "loai_thu_tuc": "TTHC được luật giao quy định chi tiết",
        "linh_vuc": "Hộ tịch",
        "doi_tuong_thuc_hien": "Công dân Việt Nam",
        "co_quan_co_tham_quyen": "",
        "dia_chi_tiep_nhan": "",
        "co_quan_duoc_uy_quyen": "",
        "co_quan_phoi_hop": "",
        "thu_tuc_lien_quan": "Không có thông tin",
        "trinh_tu_thuc_hien": "* Bước 1\nNộp hồ sơ",
        "cach_thuc_thuc_hien": "Hình thức nộp\tThời gian\nTrực tuyến\t5 Ngày làm việc",
        "thanh_phan_ho_so": "Tên giấy tờ\tSố lượng\nTờ khai\t1 bản chính",
        "can_cu_phap_ly": "Tên văn bản pháp lý\tMã văn bản\nLuật Hộ tịch\t60/2014/QH13",
        "co_quan_thuc_hien": "Ủy ban nhân dân cấp xã",
        "yeu_cau_dieu_kien": "Không quy định",
        "ket_qua_xu_ly": "Giấy khai sinh",
        "co_quan_ban_hanh": "Bộ Tư pháp",
        "ngay_cap_nhat": "2026-09-30T00:00:00+00:00",
        "phi": {
            "loai": "MIEN_PHI",
            "so_tien": None,
            "van_ban": [],
            "mo_ta_goc": "Miễn phí",
            "muc_chi_tiet": [],
        },
        "thoi_han": {
            "loai": "SO",
            "moc": [{"gia_tri": 5, "don_vi": "WORKING_DAY"}],
            "nhieu_don_vi": False,
            "muc_chi_tiet": [
                {
                    "gia_tri": 5,
                    "don_vi": "WORKING_DAY",
                    "dieu_kien": "Trong thời hạn 05 ngày làm việc kể từ ngày nhận hồ sơ",
                    "hinh_thuc": ["Trực tuyến"],
                }
            ],
        },
        "trang_thai": "ACTIVE",
        "domain_group": "11. TU_PHAP_BO_TRO",
        "content_hash": "",
        "ngay_crawl": "2026-09-30T00:00:00+00:00",
    }

    # ───────────────────────── CHUẨN HÓA ─────────────────────────


def test_normalize_unicode_returns_nfc() -> None:
    nfd = unicodedata.normalize("NFD", "Đăng ký cư trú")
    assert normalize_unicode(nfd) == unicodedata.normalize("NFC", "Đăng ký cư trú")


def test_normalize_whitespace_strips_edges() -> None:
    assert normalize_whitespace("  Đăng ký  ") == "Đăng ký"


def test_normalize_whitespace_collapses_double_space() -> None:
    assert normalize_whitespace("Đăng  ký   cư trú") == "Đăng ký cư trú"


def test_normalize_whitespace_keeps_single_tab() -> None:
    """Tab là dấu phân cách cột của bảng — KHÔNG được gộp mất."""
    goc = "Hình thức nộp\tThời gian\nTrực tuyến\t5 Ngày"
    assert normalize_whitespace(goc) == goc


def test_normalize_whitespace_keeps_adjacent_tabs() -> None:
    """HAI tab liền nhau là một Ô RỖNG trong bảng.

    Gộp `\\t\\t` thành `\\t` sẽ DỊCH CỘT và làm sai dữ liệu. Đã gặp thật ở thủ tục
    `1.013314`: cột "Mẫu đơn" rỗng, biểu diễn bằng `\\t\\t`. Test này chốt để không tái phát.
    """
    assert normalize_whitespace("A\t\tB") == "A\t\tB"
    assert normalize_whitespace("A\t\t\tB") == "A\t\t\tB"


def test_normalize_whitespace_strips_space_around_tab() -> None:
    """Space thừa quanh tab thì bỏ, nhưng cụm tab giữ nguyên."""
    assert normalize_whitespace("A \t B") == "A\tB"
    assert normalize_whitespace("A  \t\t B") == "A\t\tB"


def test_normalize_whitespace_collapses_blank_lines() -> None:
    assert normalize_whitespace("A\n\n\n\nB") == "A\n\nB"


def test_normalize_text_prose_field_collapses_tab_to_space() -> None:
    """Trường văn xuôi không có bảng, nên tab lẫn trong câu là rác."""
    ra = normalize_text("Nộp\thồ sơ", field_name="trinh_tu_thuc_hien")
    assert "\t" not in ra
    assert ra == "Nộp hồ sơ"


def test_normalize_text_none_becomes_empty() -> None:
    assert normalize_text(None) == ""


def test_normalize_record_keeps_numbers() -> None:
    """Chuẩn hóa không được biến số thành chuỗi."""
    b = sample_record()
    b["phi"]["so_tien"] = 300000
    ra = normalize_record(b)
    assert ra["phi"]["so_tien"] == 300000
    assert isinstance(ra["phi"]["so_tien"], int)


def test_normalize_record_keeps_processing_time_milestones() -> None:
    ra = normalize_record(sample_record())
    assert ra["thoi_han"]["moc"] == [{"gia_tri": 5, "don_vi": "WORKING_DAY"}]


def test_normalize_record_keeps_all_29_fields() -> None:
    ra = normalize_record(sample_record())
    assert tuple(ra) == FIELD_SCHEMA


def test_fields_needing_normalization_empty_for_clean_record() -> None:
    assert fields_needing_normalization(sample_record()) == []


def test_fields_needing_normalization_reports_only_bad_field() -> None:
    b = sample_record()
    b["ten_thu_tuc"] = "  Thủ tục   thử nghiệm  "
    assert "ten_thu_tuc" in fields_needing_normalization(b)

    # ───────────────────────── KIỂM ĐỊNH ─────────────────────────


def test_schema_co_29_truong() -> None:
    assert len(FIELD_SCHEMA) == 29


def test_record_mau_dat() -> None:
    b = sample_record()
    b["content_hash"] = compute_content_hash(b)
    kq = validate_record(b)
    assert kq.passed, f"không được có lỗi: {kq.errors}"
    assert kq.status == "READY"


def test_thieu_formality_id_van_dat() -> None:
    """`formality_id` là tùy chọn — 4 TTHC liên thông không có UUID."""
    b = sample_record()
    b["formality_id"] = ""
    b["content_hash"] = compute_content_hash(b)
    kq = validate_record(b)
    assert kq.passed, f"không được chặn: {kq.errors}"


def test_thieu_detail_url_thi_loi() -> None:
    b = sample_record()
    b["detail_url"] = ""
    kq = validate_record(b)
    assert not kq.passed
    assert any("detail_url" in x for x in kq.errors)


def test_sai_thu_tu_truong_bi_phat_hien() -> None:
    b = sample_record()
    # Đảo hai trường đầu
    muc = list(b.items())
    muc[0], muc[1] = muc[1], muc[0]
    b = dict(muc)
    kq = validate_record(b)
    assert not kq.passed
    assert any("THỨ TỰ" in x for x in kq.errors)


def test_thua_truong_bi_phat_hien() -> None:
    b = sample_record()
    b["truong_la"] = "gì đó"
    kq = validate_record(b)
    assert not kq.passed
    assert any("trường lạ" in x for x in kq.errors)


def test_phi_loai_la_bi_phat_hien() -> None:
    b = sample_record()
    b["phi"]["loai"] = "KHONG_TON_TAI"
    kq = validate_record(b)
    assert not kq.passed
    assert any("phi.loai" in x for x in kq.errors)


def test_phi_so_tien_rong_bi_phat_hien() -> None:
    """`so_tien` rỗng chuỗi là lỗi — phải là int hoặc null."""
    b = sample_record()
    b["phi"]["so_tien"] = ""
    kq = validate_record(b)
    assert not kq.passed
    assert any("so_tien" in x for x in kq.errors)


def test_phi_thieu_muc_chi_tiet_bi_phat_hien() -> None:
    """`muc_chi_tiet` là trường bắt buộc — dữ liệu crawl cũ thiếu khóa này."""
    b = sample_record()
    del b["phi"]["muc_chi_tiet"]
    kq = validate_record(b)
    assert not kq.passed
    assert any("muc_chi_tiet" in x for x in kq.errors)


def test_fee_detail_wrong_keys_detected() -> None:
    b = sample_record()
    b["phi"]["muc_chi_tiet"] = [{"so_tien": 1000, "dieu_kien": "abc", "thua": 1}]
    kq = validate_record(b)
    assert not kq.passed
    assert any("so_tien, dieu_kien" in x for x in kq.errors)


def test_phi_muc_chi_tiet_so_tien_khong_duong_bi_phat_hien() -> None:
    b = sample_record()
    b["phi"]["muc_chi_tiet"] = [{"so_tien": 0, "dieu_kien": "abc"}]
    kq = validate_record(b)
    assert not kq.passed
    assert any("số dương" in x for x in kq.errors)


def test_fee_detail_null_amount_accepted() -> None:
    """`so_tien = null` hợp lệ khi cổng ghi "theo quy định…" mà không nêu số tiền.

    Thủ tục ``2.000115``: 18 mục phí đều ``value = 0`` kèm mô tả
    *"Theo quy định của Bộ tài chính"* — phải giữ được, `so_tien` là null.
    """
    b = sample_record()
    b["phi"] = {
        "loai": "THEO_QUY_DINH_CHUNG",
        "so_tien": None,
        "van_ban": [],
        "mo_ta_goc": "Theo quy định của Bộ tài chính",
        "muc_chi_tiet": [
            {"so_tien": None, "dieu_kien": "Theo quy định của Bộ tài chính"},
            {"so_tien": 250000, "dieu_kien": "Cơ sở sản xuất nhỏ lẻ"},
        ],
    }
    b["content_hash"] = compute_content_hash(b)
    kq = validate_record(b)
    assert kq.passed, f"không được chặn: {kq.errors}"


def test_fee_detail_empty_condition_with_amount_is_valid() -> None:
    """Cổng đăng ký phí mà KHÔNG kèm điều kiện — hợp lệ, không phải lỗi.

    30/1909 bản ghi ở đúng ca này: ``1.006468`` (20.000đ, Hải quan),
    ``2.000635`` (8.000đ, Hộ tịch), ``1.013836`` (500.000đ, Công chứng)…
    Không có điều kiện nào để mô tả, chứ không phải thiếu dữ liệu.
    """
    b = sample_record()
    b["phi"] = {
        "loai": "SO_TIEN",
        "so_tien": 250000,
        "van_ban": [],
        "mo_ta_goc": "",
        "muc_chi_tiet": [{"so_tien": 250000, "dieu_kien": ""}],
    }
    b["content_hash"] = compute_content_hash(b)
    kq = validate_record(b)
    assert kq.passed, f"không được chặn: {kq.errors}"


def test_fee_detail_no_amount_and_empty_condition_is_error() -> None:
    """Không có số tiền THÌ điều kiện là thông tin duy nhất — rỗng là vô nghĩa."""
    b = sample_record()
    b["phi"]["muc_chi_tiet"] = [{"so_tien": None, "dieu_kien": "   "}]
    kq = validate_record(b)
    assert not kq.passed
    assert any("phải có điều kiện" in x for x in kq.errors)


def test_fee_detail_affects_content_hash() -> None:
    """Sửa `muc_chi_tiet` phải làm `content_hash` đổi — nếu không incremental load bỏ sót."""
    b = sample_record()
    b["phi"]["muc_chi_tiet"] = [{"so_tien": 250000, "dieu_kien": "Cơ sở nhỏ lẻ"}]
    h1 = compute_content_hash(b)
    b["phi"]["muc_chi_tiet"] = [{"so_tien": 500000, "dieu_kien": "Cơ sở khác"}]
    assert compute_content_hash(b) != h1


def test_processing_time_loai_la_bi_phat_hien() -> None:
    b = sample_record()
    b["thoi_han"]["loai"] = "SAI"
    kq = validate_record(b)
    assert not kq.passed
    assert any("thoi_han.loai" in x for x in kq.errors)


def test_processing_time_thieu_muc_chi_tiet_bi_phat_hien() -> None:
    """`muc_chi_tiet` là trường bắt buộc — dữ liệu crawl cũ thiếu khóa này."""
    b = sample_record()
    del b["thoi_han"]["muc_chi_tiet"]
    kq = validate_record(b)
    assert not kq.passed
    assert any("muc_chi_tiet" in x for x in kq.errors)


def test_processing_time_detail_wrong_keys_detected() -> None:
    b = sample_record()
    b["thoi_han"]["muc_chi_tiet"] = [{"gia_tri": 5, "don_vi": "DAY", "thua": 1}]
    kq = validate_record(b)
    assert not kq.passed
    assert any("gia_tri, don_vi, dieu_kien, hinh_thuc" in x for x in kq.errors)


def test_processing_time_detail_unknown_unit_detected() -> None:
    b = sample_record()
    b["thoi_han"]["muc_chi_tiet"] = [
        {"gia_tri": 5, "don_vi": "SAI", "dieu_kien": "abc", "hinh_thuc": []}
    ]
    kq = validate_record(b)
    assert not kq.passed
    assert any("don_vi lạ" in x for x in kq.errors)


def test_processing_time_loai_so_ma_chi_tiet_rong_bi_phat_hien() -> None:
    b = sample_record()
    b["thoi_han"]["muc_chi_tiet"] = []
    kq = validate_record(b)
    assert not kq.passed
    assert any("muc_chi_tiet rỗng" in x for x in kq.errors)


def test_processing_time_detail_affects_content_hash() -> None:
    """Sửa `muc_chi_tiet` phải làm `content_hash` đổi."""
    b = sample_record()
    h1 = compute_content_hash(b)
    b["thoi_han"]["muc_chi_tiet"] = [
        {"gia_tri": 99, "don_vi": "DAY", "dieu_kien": "trường hợp X", "hinh_thuc": []}
    ]
    assert compute_content_hash(b) != h1


def test_content_hash_lech_bi_phat_hien() -> None:
    b = sample_record()
    b["content_hash"] = "a" * 64
    kq = validate_record(b)
    assert not kq.passed
    assert any("content_hash" in x for x in kq.errors)


def test_ma_sai_dinh_dang_bi_phat_hien() -> None:
    b = sample_record()
    b["ma_thu_tuc"] = "khong-phai-ma"
    kq = validate_record(b)
    assert not kq.passed
    assert any("định dạng" in x for x in kq.errors)


def test_canh_bao_khong_chan_record() -> None:
    """Cổng không công bố phí là CẢNH BÁO, không phải lỗi."""
    b = sample_record()
    b["phi"] = {
        "loai": "CHUA_XAC_DINH",
        "so_tien": None,
        "van_ban": [],
        "mo_ta_goc": "",
        "muc_chi_tiet": [],
    }
    b["content_hash"] = compute_content_hash(b)
    kq = validate_record(b)
    assert kq.passed
    assert any("không công bố phí" in x for x in kq.warnings)


def test_truong_bat_buoc_khong_gom_formality_id() -> None:
    assert "formality_id" not in REQUIRED_FIELDS
    assert set(REQUIRED_FIELDS) == {"ma_thu_tuc", "ten_thu_tuc", "detail_url", "domain_group"}

    # ─────────────────────── KIỂM ĐỊNH LIÊN FILE ───────────────────────


def _ghi(tmp_path: Path, ma: str, nhom: str, record: dict) -> Path:
    thu_muc = tmp_path / nhom / "linh_vuc"
    thu_muc.mkdir(parents=True, exist_ok=True)
    p = thu_muc / f"{ma}.json"
    p.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return p


def test_lien_file_phat_hien_trung_ma(tmp_path: Path) -> None:
    b1 = sample_record()
    b1["content_hash"] = compute_content_hash(b1)
    b2 = dict(b1)
    b2["ten_thu_tuc"] = "Tên khác"

    p1 = _ghi(tmp_path, "1.000001", "11. TU_PHAP_BO_TRO", b1)
    p2 = _ghi(tmp_path, "1.000001", "11. TU_PHAP_BO_TRO", b2)

    loi, _ = validate_cross_file([(p1, b1), (p2, b2)])
    assert any("xuất hiện 2 lần" in x for x in loi)


def test_lien_file_phat_hien_hash_dung_chung(tmp_path: Path) -> None:
    b1 = sample_record()
    b1["content_hash"] = compute_content_hash(b1)
    b2 = dict(b1)
    b2["ma_thu_tuc"] = "1.000002"

    p1 = _ghi(tmp_path, "1.000001", "11. TU_PHAP_BO_TRO", b1)
    p2 = _ghi(tmp_path, "1.000002", "11. TU_PHAP_BO_TRO", b2)

    loi, _ = validate_cross_file([(p1, b1), (p2, b2)])
    assert any("dùng chung bởi" in x for x in loi)


def test_lien_file_phat_hien_thu_muc_lech(tmp_path: Path) -> None:
    b = sample_record()
    b["content_hash"] = compute_content_hash(b)
    # Ghi vào thư mục SAI so với domain_group bên trong file
    p = _ghi(tmp_path, "1.000001", "99. SAI_NHOM", b)

    loi, _ = validate_cross_file([(p, b)])
    assert any("không khớp domain_group" in x for x in loi)


def test_thong_ke_coverage_dem_dung(tmp_path: Path) -> None:
    b1 = sample_record()
    b2 = sample_record()
    b2["ma_thu_tuc"] = "1.000002"
    b2["co_quan_ban_hanh"] = ""

    p1 = _ghi(tmp_path, "1.000001", "11. TU_PHAP_BO_TRO", b1)
    p2 = _ghi(tmp_path, "1.000002", "11. TU_PHAP_BO_TRO", b2)

    coverage = field_coverage([(p1, b1), (p2, b2)])
    assert coverage["co_quan_ban_hanh"]["real"] == 1
    assert coverage["co_quan_ban_hanh"]["empty"] == 1
    assert coverage["ma_thu_tuc"]["real"] == 2

    # ─────────────────────── GIÁ TRỊ SENTINEL ───────────────────────


def test_is_sentinel_nhan_dung_cac_bien_the() -> None:
    """Cổng ghi lẫn hoa/thường, dấu câu và khoảng trắng — tất cả đều là sentinel.

    9 biến thể này **có thật** trong 1909 bản ghi. So khớp trên dạng đã chuẩn hóa nên một
    dấu chấm thừa không làm sót.
    """
    for sample in (
        "Không có thông tin",
        "Không quy định",
        "Không quy định.",
        "không quy định",
        "Không có",
        "không có",
        "Không.",
        "không có.",
        "Không có.",
        "Không",
        "không",
        "KHÔNG QUY ĐỊNH",
    ):
        assert is_sentinel(sample), f"phải nhận là sentinel: {sample!r}"


def test_is_sentinel_bo_qua_khoang_trang_thua() -> None:
    assert is_sentinel("  Không  ")
    assert is_sentinel("\tKhông có thông tin\n")


def test_is_sentinel_khong_nham_cau_khang_dinh_la_chua_ghi_nhan() -> None:
    """Câu KHẲNG ĐỊNH không được coi là "chưa ghi nhận" — hai nghĩa ngược nhau.

    Cổng có 43 giá trị dạng này trong ``yeu_cau_dieu_kien`` và ``result_xu_ly``. Nếu gộp
    vào sentinel thì chunk nói "cổng chưa ghi nhận" trong khi cổng đã KHẲNG ĐỊNH — sai
    hướng hoàn toàn. Vì vậy dùng tập ĐÓNG, không dùng tiền tố ``"không có"``.
    """
    for sample in (
        "Không có yêu cầu, điều kiện",
        "Không có yêu cầu, điều kiện!",
        "Không có kết quả",
        "Không có văn bản trả lời",
        "Không quy định kết quả",
        "Không quy định kết quả giải quyết TTHC",
        "không yêu cầu",
    ):
        assert not is_sentinel(sample), f"KHÔNG được nhận là sentinel: {sample!r}"


def test_is_sentinel_khong_nham_noi_dung_that() -> None:
    """Nội dung nghiệp vụ thật KHÔNG được nhận nhầm là sentinel."""
    for sample in (
        "",
        "Không quy định về độ tuổi",  # câu thật, không phải sentinel
        "Không có thông tin chi tiết về lệ phí",
        "Không thuộc trường hợp miễn phí",
        "Miễn phí",
        "Giấy khai sinh",
        None,
        0,
    ):
        assert not is_sentinel(sample), f"KHÔNG được nhận là sentinel: {sample!r}"


def test_is_sentinel_nhan_mang_toan_sentinel() -> None:
    """Mảng toàn sentinel cũng là "chưa ghi nhận"."""
    assert is_sentinel(["Không"])
    assert is_sentinel(["Không", "không"])
    # Mảng lẫn nội dung thật thì KHÔNG phải sentinel
    assert not is_sentinel(["Không", "Sở Tư pháp"])
    assert not is_sentinel([])


def test_thong_ke_coverage_tach_sentinel_rieng(tmp_path: Path) -> None:
    """Sentinel phải vào cột `sentinel`, KHÔNG tính là `that`.

    Đây là điểm sửa chính: `thu_tuc_lien_quan` có "độ phủ 100%" nhưng thực tế chỉ vài bản
    ghi có dữ liệu; phần còn lại là `"Không có thông tin"`.
    """
    has_real = sample_record()
    has_real["thu_tuc_lien_quan"] = "Thủ tục đăng ký khai sinh, Đăng ký thường trú"

    has_sentinel = sample_record()
    has_sentinel["ma_thu_tuc"] = "1.000002"
    has_sentinel["thu_tuc_lien_quan"] = "Không có thông tin"

    blank = sample_record()
    blank["ma_thu_tuc"] = "1.000003"
    blank["thu_tuc_lien_quan"] = ""

    p1 = _ghi(tmp_path, "1.000001", "11. TU_PHAP_BO_TRO", has_real)
    p2 = _ghi(tmp_path, "1.000002", "11. TU_PHAP_BO_TRO", has_sentinel)
    p3 = _ghi(tmp_path, "1.000003", "11. TU_PHAP_BO_TRO", blank)

    d = field_coverage([(p1, has_real), (p2, has_sentinel), (p3, blank)])["thu_tuc_lien_quan"]
    assert d["real"] == 1
    assert d["sentinel"] == 1
    assert d["empty"] == 1
    # `co` là "trường không rỗng" — gộp that + sentinel, giữ để tương thích
    assert d["present"] == 2
