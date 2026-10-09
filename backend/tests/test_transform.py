"""Test các hàm logic thuần của crawler. Không gọi mạng."""

from __future__ import annotations

import json
from pathlib import Path

from data_pipeline.crawler.catalog import CatalogEntry
from data_pipeline.crawler.run import pick_formality_id, slug_tieng_viet
from data_pipeline.crawler.transform import (
    _administrative_level,
    _description_key,
    _duration_of,
    _epoch_ms_to_iso,
    _fee_description,
    _steps_text,
    build_fee,
    build_processing_time,
    compute_content_hash,
    transform,
)
from data_pipeline.crawler.validator import STATUS_NEED_REVIEW, STATUS_READY, validate_crawl

# Bộ trường cam kết trong hợp đồng dữ liệu (mục 4.1b của PROJECT_GUIDE_V4_1.md).
REQUIRED_FIELDS = {
    # Định danh
    "ma_thu_tuc",
    "detail_url",
    "formality_id",
    "ten_thu_tuc",
    # Phân loại
    "so_quyet_dinh",
    "cap_thuc_hien",
    "loai_thu_tuc",
    "linh_vuc",
    "doi_tuong_thuc_hien",
    "co_quan_co_tham_quyen",
    "dia_chi_tiep_nhan",
    "co_quan_duoc_uy_quyen",
    "co_quan_phoi_hop",
    "thu_tuc_lien_quan",
    # Nội dung
    "trinh_tu_thuc_hien",
    "cach_thuc_thuc_hien",
    "thanh_phan_ho_so",
    "can_cu_phap_ly",
    "co_quan_thuc_hien",
    "yeu_cau_dieu_kien",
    "ket_qua_xu_ly",
    # Bổ sung Mức 1
    "co_quan_ban_hanh",
    "ngay_cap_nhat",
    "content_hash",
    "ngay_crawl",
    # Bổ sung Mức 2
    "phi",
    "thoi_han",
    # Đã có
    "trang_thai",
    "domain_group",
}

# ───────────────────────── pick_formality_id ─────────────────────────


def test_pick_formality_id_khong_tim_thay() -> None:
    chosen, note = pick_formality_id([])
    assert chosen is None
    assert "không tìm thấy" in note


def test_pick_formality_id_mot_ban_thi_khong_co_ghi_chu() -> None:
    """Một bản duy nhất ⇒ không có gì phải xem lại."""
    chosen, note = pick_formality_id([{"id": "abc", "state": "ACTIVE", "updatedAt": 1}])
    assert chosen is not None
    assert chosen["id"] == "abc"
    assert note == ""


def test_pick_formality_id_uu_tien_active() -> None:
    """Bản ACTIVE được ưu tiên dù updatedAt cũ hơn."""
    chosen, _ = pick_formality_id(
        [
            {"id": "cu", "state": "ACTIVE", "updatedAt": 100},
            {"id": "moi-nhung-ngung", "state": "DELETED", "updatedAt": 999},
        ]
    )
    assert chosen is not None
    assert chosen["id"] == "cu"


def test_pick_formality_id_lay_ban_moi_nhat_va_ghi_chu() -> None:
    """Nhiều bản ACTIVE ⇒ lấy updatedAt mới nhất VÀ ghi chú để người dùng xác nhận."""
    chosen, note = pick_formality_id(
        [
            {"id": "cu", "state": "ACTIVE", "updatedAt": 100},
            {"id": "moi", "state": "ACTIVE", "updatedAt": 999},
        ]
    )
    assert chosen is not None
    assert chosen["id"] == "moi"
    assert "2 bản cùng mã" in note


def test_pick_formality_id_khong_con_doi_chieu_co_quan() -> None:
    """Hướng B: KHÔNG còn cờ đỏ 'cơ quan ban hành không khớp danh mục'.

    Cột `Cơ quan ban hành` của Excel trộn cấp Bộ với đơn vị soạn thảo, nên đối chiếu
    theo cột đó sinh cờ đỏ giả. Nguồn chân lý là `co_quan_ban_hanh` lấy từ API.
    """
    chosen, note = pick_formality_id(
        [{"id": "x", "state": "ACTIVE", "updatedAt": 1, "departmentPromulgate": "Bộ Công thương"}]
    )
    assert chosen is not None
    assert "cơ quan ban hành" not in note


ENTRY = CatalogEntry(
    procedure_code="1.115346",
    procedure_name="Đăng ký, cấp Giấy chứng nhận quyền sử dụng đất",
    issuing_agency="UBND tỉnh Gia Lai",
    source_field="Đất đai",
    administrative_level="Cấp tỉnh",
    procedure_type="TTHC được luật giao quy định chi tiết",
    domain_group="10. TAI_NGUYEN_MOI_TRUONG",
)


# ───────────────────────── slug_tieng_viet ─────────────────────────


def test_slug_bo_dau_va_ngan_bang_gach_duoi() -> None:
    assert slug_tieng_viet("Đăng ký, quản lý cư trú") == "Dang_ky_quan_ly_cu_tru"


def test_slug_giu_chu_d_mot_dong() -> None:
    assert slug_tieng_viet("Đất đai") == "Dat_dai"


def test_slug_xu_ly_ten_rong() -> None:
    assert slug_tieng_viet("") == "KHONG_XAC_DINH"
    assert slug_tieng_viet("   ") == "KHONG_XAC_DINH"


def test_slug_bo_ky_tu_nguy_hiem() -> None:
    """Ký tự cấm trên Windows không được lọt vào tên thư mục."""
    result = slug_tieng_viet('Lĩnh vực: "A/B" <C>')
    assert not any(ky_tu in result for ky_tu in '<>:"/\\|?*')

    # ───────────────────────── _phi_description ─────────────────────────


def test_phi_co_so_tien_dinh_dang() -> None:
    assert _fee_description([{"gia_tri": 160000, "description": ""}]) == "160.000 đồng"


def test_fee_zero_value_with_description_is_not_free() -> None:
    """Bẫy chính: value=0 nhưng mô tả viện dẫn văn bản, không phải miễn phí."""
    result = _fee_description(
        [{"value": 0, "description": "Thực hiện theo quy định tại Thông tư số 10/2024/TT-BTC"}]
    )
    assert result == "Thực hiện theo quy định tại Thông tư số 10/2024/TT-BTC"


def test_fee_free_keeps_raw_description() -> None:
    """File mẫu ghi `Miễn phí\\n(mô tả thêm)` khi cổng báo miễn phí."""
    result = _fee_description([{"gia_tri": 0, "description": "Thủ tục này miễn phí"}])
    assert result == "Miễn phí\n(Thủ tục này miễn phí)"


def test_fee_no_charge_keeps_raw_description() -> None:
    """Mô tả luôn được giữ nguyên để người đọc đối chiếu được với nguồn."""
    assert _fee_description([{"gia_tri": 0, "description": "Không thu phí"}]) == (
        "Miễn phí\n(Không thu phí)"
    )


def test_cot_phi_trong_bang_ghi_free_case_khi_value_0() -> None:
    """Cột phí trong bảng phải khớp với ``phi.loai`` — cùng quy tắc, không mâu thuẫn."""
    assert _fee_description([{"gia_tri": 0, "description": ""}]) == "Miễn phí"


def test_phi_khong_co_muc_nao_thi_blank() -> None:
    """Kiểm chứng trên cổng: thủ tục 3.000242 không có mục phí, cổng ghi "không có thông tin"."""
    assert _fee_description([]) == ""

    # ───────────────────────── _thoi_gian_cua ─────────────────────────


def test_thoi_gian_lay_tu_truong_so() -> None:
    assert _duration_of({"processingTime": 16.5, "processingTimeUnit": "WORKING_DAY"}) == (
        "16.5 Ngày làm việc"
    )


def test_thoi_gian_so_nguyen_khong_hien_phan_thap_phan() -> None:
    assert _duration_of({"processingTime": 2, "processingTimeUnit": "WORKING_DAY"}) == (
        "2 Ngày làm việc"
    )


def test_duration_extracted_from_description_when_unit_unusable() -> None:
    """Trường hợp thật của 1.116634: processingTime=0, unit=OTHER, mốc nằm trong mô tả."""
    result = _duration_of(
        {
            "processingTime": 0,
            "processingTimeUnit": "OTHER",
            "description": "Thời hạn giải quyết là 90 ngày kể từ ngày nhận hồ sơ.",
        }
    )
    assert result == "90 ngày"


def test_thoi_gian_khong_xac_dinh_duoc_tra_ve_rong() -> None:
    assert _duration_of({"processingTime": 0, "processingTimeUnit": "OTHER"}) == ""
    assert _duration_of({}) == ""

    # ───────────────────────── _cap_thuc_hien ─────────────────────────


def test_administrative_level_joins_with_comma() -> None:
    """File mẫu ghi `"Cấp tỉnh, Cấp xã"` — thứ tự bộ trước, xã sau."""
    result = _administrative_level({"isProvince": True, "isWard": True})
    assert result == "Cấp tỉnh, Cấp xã"


def test_administrative_level_single() -> None:
    assert _administrative_level({"isWard": True}) == "Cấp xã"


def test_administrative_level_none_set() -> None:
    assert _administrative_level({}) == ""

    # ───────────────────────── _trinh_tu_text ─────────────────────────


def test_steps_joins_step_descriptions() -> None:
    result = _steps_text(
        [{"name": "", "description": "Bước 1: nộp hồ sơ"}, {"description": "Bước 2: nhận kết quả"}]
    )
    assert result == "Bước 1: nộp hồ sơ\n\nBước 2: nhận kết quả"


def test_steps_empty() -> None:
    assert _steps_text(None) == ""
    assert _steps_text([{"description": ""}]) == ""

    # ───────────────────────── validate ─────────────────────────


def _valid_record() -> dict:
    """Bản ghi giống output thật của thủ tục 1.013314."""
    return {
        "ma_thu_tuc": "1.013314",
        "ten_thu_tuc": "Xác nhận về điều kiện diện tích bình quân nhà ở",
        "detail_url": "https://dichvucong.gov.vn/thu-tuc-hanh-chinh/019d2bf7-9660",
        "formality_id": "019d2bf7-9660-707e-97b1-ef8876f54d3b",
        "trinh_tu_thuc_hien": "Bước 1: nộp hồ sơ",
        "cach_thuc_thuc_hien": "Hình thức nộp\tThời gian",
        "thanh_phan_ho_so": "",
        "trang_thai": "UPDATED",
    }


def test_validate_record_day_du_la_ready() -> None:
    result = validate_crawl(_valid_record())
    assert result.status == STATUS_READY
    assert result.issues == []


def test_validate_ho_so_rong_khong_bi_coi_la_loi() -> None:
    """Phần lớn thủ tục trên cổng để trống thành phần hồ sơ — không phải lỗi."""
    record = _valid_record()
    record["thanh_phan_ho_so"] = ""
    assert validate_crawl(record).status == STATUS_READY


def test_validate_thieu_trinh_tu_bi_need_review() -> None:
    record = _valid_record()
    record["trinh_tu_thuc_hien"] = ""
    result = validate_crawl(record)
    assert result.status == STATUS_NEED_REVIEW
    assert any("trình tự thực hiện" in issue for issue in result.issues)


def test_validate_missing_formality_id_is_still_ready() -> None:
    """`formality_id` là TÙY CHỌN — thiếu nó không chặn bản ghi.

    4 TTHC liên thông không có UUID (cổng dùng ID số cho nhóm này, endpoint chi tiết
    bị WAF chặn). Trường này chỉ dùng ở khâu crawl, không dùng để truy xuất; khóa đồng
    bộ giữa các CSDL là `ma_thu_tuc` và `chunk_id`.
    """
    record = _valid_record()
    record["formality_id"] = ""
    result = validate_crawl(record)
    assert result.status == STATUS_READY, f"không được chặn: {result.issues}"
    assert not any("formality_id" in issue for issue in result.issues)


def test_validate_missing_detail_url_needs_review() -> None:
    """`detail_url` thì VẪN bắt buộc — nó là nguồn trích dẫn.

    Khác với `formality_id`, thiếu `detail_url` là mất citation thật.
    """
    record = _valid_record()
    record["detail_url"] = ""
    result = validate_crawl(record)
    assert result.status == STATUS_NEED_REVIEW
    assert any("detail_url" in issue for issue in result.issues)


def test_validate_trang_thai_updated_van_la_ready() -> None:
    """Cổng dùng UPDATED cho thủ tục đã cập nhật nhưng vẫn hiệu lực."""
    record = _valid_record()
    record["trang_thai"] = "UPDATED"
    assert validate_crawl(record).status == STATUS_READY


def test_validate_trang_thai_ngung_hieu_luc_bi_need_review() -> None:
    record = _valid_record()
    record["trang_thai"] = "INACTIVE"
    result = validate_crawl(record)
    assert result.status == STATUS_NEED_REVIEW
    assert any("không còn hiệu lực" in issue for issue in result.issues)

    # ───────────────────────── hợp đồng dữ liệu ─────────────────────────

    # File response API thô dùng làm mẫu đối chiếu, lưu trong repo.


RAW_MAU = Path("data/raw/api/01. AN_NINH_TRAT_TU_CU_TRU/Dang_ky_quan_ly_cu_tru/1.013314.json")


def test_transform_returns_exactly_29_fields() -> None:
    """Chốt hợp đồng dữ liệu: thêm/bớt trường là test này phải đổ.

    Bộ trường là cam kết với tầng sau (chunking, indexing), nên không được lệch âm thầm.
    """
    if not RAW_MAU.exists():
        return  # chưa crawl thì bỏ qua, không làm đỏ bộ test

    raw = json.loads(RAW_MAU.read_text(encoding="utf-8"))
    result = transform(ENTRY, raw, crawled_at="2026-01-01T00:00:00+00:00")

    assert len(result) == 29, f"Số trường lệch: {len(result)}"
    assert set(result) == REQUIRED_FIELDS
    assert "raw_text" not in result


def test_transform_truong_text_khong_tra_ve_none() -> None:
    """Trường text thiếu phải là chuỗi rỗng, không phải None — tầng sau khỏi kiểm tra."""
    if not RAW_MAU.exists():
        return

    raw = json.loads(RAW_MAU.read_text(encoding="utf-8"))
    result = transform(ENTRY, raw, crawled_at="2026-01-01T00:00:00+00:00")

    for ten, sample in result.items():
        assert sample is not None, f"trường {ten} trả về None"
        if ten not in ("phi", "thoi_han"):
            assert isinstance(sample, str), f"trường {ten} không phải chuỗi"


def test_transform_lay_duoc_co_quan_ban_hanh() -> None:
    """Trường bổ sung Mức 1 — thiếu nó thì mất 19 cơ quan ban hành."""
    if not RAW_MAU.exists():
        return

    raw = json.loads(RAW_MAU.read_text(encoding="utf-8"))
    result = transform(ENTRY, raw, crawled_at="2026-01-01T00:00:00+00:00")

    assert result["co_quan_ban_hanh"] == "Bộ Công an"


def test_transform_ngay_cap_nhat_dang_iso() -> None:
    if not RAW_MAU.exists():
        return

    raw = json.loads(RAW_MAU.read_text(encoding="utf-8"))
    result = transform(ENTRY, raw, crawled_at="2026-01-01T00:00:00+00:00")

    # API trả epoch ms; phải đổi sang ISO 8601 UTC để so sánh được bằng SQL.
    assert result["ngay_cap_nhat"].startswith("20")
    assert "T" in result["ngay_cap_nhat"]
    assert result["ngay_crawl"] == "2026-01-01T00:00:00+00:00"


def test_epoch_ms_to_iso() -> None:
    assert _epoch_ms_to_iso(0) == ""
    assert _epoch_ms_to_iso(None) == ""
    assert _epoch_ms_to_iso("khong-phai-so") == ""
    assert _epoch_ms_to_iso(1777300588381).startswith("2026-")


def test_content_hash_ignores_version_fields() -> None:
    """Đổi ngay_crawl KHÔNG được đổi hash, nếu không incremental load vô nghĩa."""
    goc = {"ma_thu_tuc": "1.1", "ten_thu_tuc": "A", "ngay_crawl": "2026-01-01T00:00:00+00:00"}
    sau = {"ma_thu_tuc": "1.1", "ten_thu_tuc": "A", "ngay_crawl": "2026-09-30T00:00:00+00:00"}

    assert compute_content_hash(goc) == compute_content_hash(sau)


def test_content_hash_changes_with_content() -> None:
    truoc = {"ma_thu_tuc": "1.1", "ten_thu_tuc": "A"}
    sau = {"ma_thu_tuc": "1.1", "ten_thu_tuc": "B"}

    assert compute_content_hash(truoc) != compute_content_hash(sau)


def test_transform_khong_bam_chinh_minh() -> None:
    """content_hash phải băm nội dung, không băm chính trường content_hash."""
    if not RAW_MAU.exists():
        return

    raw = json.loads(RAW_MAU.read_text(encoding="utf-8"))
    lan_1 = transform(ENTRY, raw, crawled_at="2026-01-01T00:00:00+00:00")
    lan_2 = transform(ENTRY, raw, crawled_at="2026-09-30T00:00:00+00:00")

    assert lan_1["content_hash"] == lan_2["content_hash"]

    # ───────────────────────── phi / processing_time (bổ sung Mức 2) ─────────────────────────


def test_phi_co_so_tien_dung_kieu_so() -> None:
    """so_tien phải là số, không phải chuỗi — để SQL so sánh được."""
    phi = build_fee([{"fees": [{"gia_tri": 160000, "description": ""}]}])
    assert phi["loai"] == "SO_TIEN"
    assert phi["so_tien"] == 160000
    assert isinstance(phi["so_tien"], int)


def test_fee_keeps_raw_description() -> None:
    """Bẫy chính: value=0 nhưng mô tả viện dẫn văn bản, không phải miễn phí."""
    phi = build_fee(
        [{"fees": [{"gia_tri": 0, "description": "Thực hiện theo Thông tư số 10/2024/TT-BTC"}]}]
    )
    assert phi["loai"] == "THEO_VAN_BAN"
    assert phi["so_tien"] is None
    assert phi["van_ban"][0]["so_hieu"] == "10/2024/TT-BTC"
    assert phi["mo_ta_goc"]  # giữ nguyên văn để đối chiếu ngược


def test_fee_zero_value_empty_description_is_free() -> None:
    """Kiểm chứng trên cổng: 1.013314 có fees=[{value:0, mô tả rỗng}], cổng ghi "miễn phí"."""
    phi = build_fee([{"fees": [{"gia_tri": 0, "description": ""}]}])
    assert phi["loai"] == "MIEN_PHI"
    assert phi["so_tien"] is None


def test_phi_khong_co_muc_nao_la_chua_xac_dinh() -> None:
    """Kiểm chứng trên cổng: 3.000242 có fees=[] ở mọi cách thức, cổng ghi "không có thông tin"."""
    # Mô phỏng thật: nhiều cách thức, KHÔNG cách thức nào có mục phí.
    phuong_thuc = [
        {"submissionMethod": "ONLINE", "fees": [], "description": "Nhận kết quả qua bưu chính."},
        {"submissionMethod": "POSTAL", "fees": []},
        {"submissionMethod": "DIRECT", "fees": []},
    ]
    phi = build_fee(phuong_thuc)
    assert phi["loai"] == "CHUA_XAC_DINH"
    assert phi["so_tien"] is None


def test_phan_biet_free_case_voi_khong_co_thong_tin() -> None:
    """Đây là điểm dễ sai nhất: hai thủ tục cùng không có số tiền nhưng khác kết luận.

    Khác biệt nằm ở SỐ PHẦN TỬ của fees, không phải giá trị value.
    """
    free_case = build_fee([{"fees": [{"gia_tri": 0, "description": ""}]}])
    khong_biet = build_fee([{"fees": []}])

    assert free_case["loai"] == "MIEN_PHI"
    assert khong_biet["loai"] == "CHUA_XAC_DINH"
    assert free_case["so_tien"] is None
    assert khong_biet["so_tien"] is None


def test_fee_always_has_5_keys() -> None:
    """Tầng sau không phải kiểm tra trường thiếu."""
    for case in ([], [{"description": "abc"}], [{"fees": []}], [{"fees": [{"gia_tri": 0}]}]):
        phi = build_fee(case)
        assert set(phi) == {"loai", "so_tien", "van_ban", "mo_ta_goc", "muc_chi_tiet"}

        # ─────────────── muc_chi_tiet: cặp (số tiền, điều kiện) ───────────────


def test_muc_chi_tiet_giu_cap_so_tien_va_dieu_kien() -> None:
    """Cặp (số tiền, điều kiện) phải giữ liên kết — đây là điểm sửa chính.

    Thủ tục thật ``1.004376`` có 8 mức phí cho 8 trường hợp. Nếu chỉ lưu một số tiền thì
    không trả lời được "trường hợp của tôi đóng bao nhiêu?".
    """
    phi = build_fee(
        [
            {
                "fees": [
                    {"gia_tri": 34500000, "description": "Quốc tế chiều đi, cấp lần đầu"},
                    {"gia_tri": 8500000, "description": "Phạm vi liên tỉnh, chuyển nhượng"},
                ]
            }
        ]
    )
    assert phi["muc_chi_tiet"] == [
        {"so_tien": 34500000, "dieu_kien": "Quốc tế chiều đi, cấp lần đầu"},
        {"so_tien": 8500000, "dieu_kien": "Phạm vi liên tỉnh, chuyển nhượng"},
    ]


def test_muc_chi_tiet_khu_trung_theo_cap() -> None:
    """Ba cách thức thực hiện lặp cùng bộ phí → chỉ giữ một lần."""
    fee_set = [
        {"gia_tri": 34500000, "description": "Quốc tế chiều đi"},
        {"gia_tri": 21500000, "description": "Phạm vi liên tỉnh"},
    ]
    phi = build_fee([{"fees": [dict(x) for x in fee_set]} for _ in range(3)])
    assert len(phi["muc_chi_tiet"]) == 2


def test_muc_chi_tiet_khong_khu_theo_so_tien() -> None:
    """CÙNG số tiền nhưng KHÁC điều kiện là hai mục khác nhau — không được khử.

    Thủ tục ``1.004376`` có hai mục cùng 21.500.000 ứng với hai trường hợp khác nhau.
    """
    phi = build_fee(
        [
            {
                "fees": [
                    {"gia_tri": 21500000, "description": "Cấp lần đầu"},
                    {"gia_tri": 21500000, "description": "Chuyển nhượng doanh nghiệp"},
                ]
            }
        ]
    )
    assert len(phi["muc_chi_tiet"]) == 2
    assert {x["dieu_kien"] for x in phi["muc_chi_tiet"]} == {
        "Cấp lần đầu",
        "Chuyển nhượng doanh nghiệp",
    }


def test_fee_detail_drops_zero_value_without_description() -> None:
    """``value = 0`` KHÔNG mô tả là nhãn MIEN_PHI thuần — không có gì để hiển thị."""
    phi = build_fee([{"fees": [{"gia_tri": 0, "description": ""}]}])
    assert phi["loai"] == "MIEN_PHI"
    assert phi["muc_chi_tiet"] == []


def test_phi_giu_muc_value_0_khi_co_description() -> None:
    """Thủ tục thật 2.000115: mọi mục phí đều value = 0 kèm mô tả — phải giữ.

    Bỏ hết thì `muc_chi_tiet` rỗng và chunk FEE không còn gì để nói, dù cổng có nêu
    "Theo quy định của Bộ Tài chính".
    """
    phi = build_fee(
        [
            {
                "fees": [
                    {"gia_tri": 0, "description": "Theo quy định của Bộ tài chính"},
                    {"gia_tri": 0, "description": "Theo quy định của Bộ Tài chính"},
                ]
            }
        ]
    )
    assert phi["loai"] == "THEO_QUY_DINH_CHUNG"
    assert phi["so_tien"] is None
    # Hai mô tả chỉ khác hoa/thường → gộp thành MỘT mục
    assert len(phi["muc_chi_tiet"]) == 1
    assert phi["muc_chi_tiet"][0]["so_tien"] is None
    assert phi["muc_chi_tiet"][0]["dieu_kien"]


def test_description_key_ignores_punctuation_and_case() -> None:
    """Cổng ghi cùng điều kiện với dấu câu / hoa-thường khác nhau ở các hình thức nộp."""
    for a, b in (
        ("…Đơn đề nghị hợp lệ.", "…Đơn đề nghị hợp lệ"),
        ("Theo quy định của Bộ tài chính", "Theo quy định của Bộ Tài chính"),
        ("Trường hợp a.\nTrong thời hạn 03 ngày.", "Trường hợp a\nTrong thời hạn 03 ngày"),
        ("Trường hợp cấp lại\nTrong thời hạn 3 ngày", "Trường hợp cấp lại"),
    ):
        assert _description_key(a) == _description_key(b), f"phải gộp: {a[:40]!r} vs {b[:40]!r}"


def test_description_key_keeps_semantic_difference() -> None:
    """Khác nội dung thật thì khóa phải KHÁC — không được gộp bừa."""
    for a, b in (
        ("Trường hợp cơ sở thay đổi tên cơ sở", "Trường hợp cơ sở thay đổi chủ cơ sở"),
        ("Theo Thông tư 17/2020/NĐ-CP", "Theo Thông tư 17/2020NĐCP"),
    ):
        assert _description_key(a) != _description_key(b), (
            f"KHÔNG được gộp: {a[:40]!r} vs {b[:40]!r}"
        )


def test_processing_time_merges_conditions_differing_only_in_punctuation() -> None:
    """Thủ tục thật 2.000115: ONLINE và DIRECT ghi cùng điều kiện, khác dấu chấm cuối."""
    processing_time = build_processing_time(
        [
            {
                "submissionMethod": "ONLINE",
                "processingTime": 3,
                "processingTimeUnit": "WORKING_DAY",
                "description": "Trường hợp cấp lại do bị mất hoặc bị hỏng.",
            },
            {
                "submissionMethod": "DIRECT",
                "processingTime": 3,
                "processingTimeUnit": "WORKING_DAY",
                "description": "Trường hợp cấp lại do bị mất hoặc bị hỏng",
            },
        ]
    )
    assert len(processing_time["muc_chi_tiet"]) == 1
    assert processing_time["muc_chi_tiet"][0]["hinh_thuc"] == ["Trực tuyến", "Trực tiếp"]


def test_fee_detail_empty_when_unknown() -> None:
    phi = build_fee([{"fees": []}])
    assert phi["loai"] == "CHUA_XAC_DINH"
    assert phi["muc_chi_tiet"] == []


def test_muc_chi_tiet_bo_muc_khong_co_so_tien() -> None:
    """Mục có mô tả nhưng không có ``value`` thì không phải mức phí cụ thể."""
    phi = build_fee([{"fees": [{"description": "Theo quy định pháp luật"}]}])
    assert phi["muc_chi_tiet"] == []


def test_processing_time_has_structure_for_querying() -> None:
    processing_time = build_processing_time(
        [{"processingTime": 2, "processingTimeUnit": "WORKING_DAY"}]
    )
    assert processing_time["loai"] == "SO"
    assert processing_time["moc"] == [{"gia_tri": 2, "don_vi": "WORKING_DAY"}]
    assert processing_time["nhieu_don_vi"] is False


def test_processing_time_multiple_units_not_cumulative() -> None:
    """Thủ tục thật 3.000242 có cả '15 Ngày' và '1 Giờ' — không được cộng thành 16."""
    processing_time = build_processing_time(
        [
            {"processingTime": 15, "processingTimeUnit": "DAY"},
            {"processingTime": 1, "processingTimeUnit": "HOUR"},
        ]
    )
    assert processing_time["nhieu_don_vi"] is True
    assert {m["don_vi"] for m in processing_time["moc"]} == {"DAY", "HOUR"}


def test_processing_time_always_has_4_keys() -> None:
    processing_time = build_processing_time([])
    assert set(processing_time) == {"loai", "moc", "nhieu_don_vi", "muc_chi_tiet"}
    assert processing_time["loai"] == "CHUA_XAC_DINH"


def test_processing_time_has_no_summary() -> None:
    """``tom_tat`` đã bỏ: nó gộp max theo đơn vị, tạo câu trả lời sai kiểu cộng dồn."""
    assert "tom_tat" not in build_processing_time(
        [{"processingTime": 15, "processingTimeUnit": "DAY"}]
    )

    # ─────────── processing_time.muc_chi_tiet: cặp (thời hạn, điều kiện) ───────────


def test_processing_time_detail_keeps_value_and_method() -> None:
    """Mỗi mốc thời hạn đi kèm mô tả điều kiện NGUYÊN VĂN và hình thức nộp."""
    processing_time = build_processing_time(
        [
            {
                "submissionMethod": "ONLINE",
                "processingTime": 15,
                "processingTimeUnit": "DAY",
                "description": "Đối với doanh nghiệp nhà nước thuộc UBND tỉnh",
            },
            {
                "submissionMethod": "POSTAL",
                "processingTime": 1,
                "processingTimeUnit": "HOUR",
                "description": "Nhận kết quả qua dịch vụ bưu chính công ích.",
            },
        ]
    )
    assert processing_time["muc_chi_tiet"] == [
        {
            "gia_tri": 15,
            "don_vi": "DAY",
            "dieu_kien": "Đối với doanh nghiệp nhà nước thuộc UBND tỉnh",
            "hinh_thuc": ["Trực tuyến"],
        },
        {
            "gia_tri": 1,
            "don_vi": "HOUR",
            "dieu_kien": "Nhận kết quả qua dịch vụ bưu chính công ích.",
            "hinh_thuc": ["Bưu chính"],
        },
    ]


def test_processing_time_has_no_generated_label() -> None:
    """KHÔNG có trường `description` tự sinh — nó che mất điều kiện khác nhau.

    Bug thật: 6 mốc `3 Ngày làm việc` của ``2.000115`` từng nhìn giống hệt nhau vì
    `description` chỉ là nhãn ghép từ số + đơn vị.
    """
    processing_time = build_processing_time(
        [
            {
                "submissionMethod": "ONLINE",
                "processingTime": 3,
                "processingTimeUnit": "WORKING_DAY",
                "description": "Trường hợp cấp lại do mất hoặc hỏng",
            }
        ]
    )
    muc = processing_time["muc_chi_tiet"][0]
    assert "description" not in muc
    assert muc["dieu_kien"] == "Trường hợp cấp lại do mất hoặc hỏng"


def test_processing_time_keeps_distinct_conditions_same_days() -> None:
    """Thủ tục thật 2.000115: nhiều mốc `3 Ngày làm việc` với điều kiện KHÁC nhau."""
    description = [
        "Trường hợp cấp lại do Giấy chứng nhận bị mất hoặc bị hỏng",
        "Trường hợp cơ sở thay đổi tên cơ sở nhưng không đổi chủ cơ sở",
        "Trường hợp cơ sở thay đổi chủ cơ sở nhưng không đổi tên cơ sở",
        "Trường hợp chuỗi cơ sở kinh doanh thực phẩm có giảm",
        "Trường hợp cơ sở thay đổi địa điểm sản xuất",
        "Trường hợp Giấy chứng nhận hết hiệu lực",
    ]
    processing_time = build_processing_time(
        [
            {
                "submissionMethod": "ONLINE",
                "processingTime": 3,
                "processingTimeUnit": "WORKING_DAY",
                "description": m,
            }
            for m in description
        ]
    )
    assert len(processing_time["muc_chi_tiet"]) == 6
    assert len({x["dieu_kien"] for x in processing_time["muc_chi_tiet"]}) == 6


def test_processing_time_detail_merges_same_condition_methods() -> None:
    """Cùng thời hạn + cùng mô tả nhưng khác hình thức nộp → MỘT mục, hai hình thức.

    Đây là trường hợp thật của ``3.000242``: DIRECT và ONLINE cùng 15 Ngày, cùng mô tả.
    """
    processing_time = build_processing_time(
        [
            {
                "submissionMethod": "DIRECT",
                "processingTime": 5,
                "processingTimeUnit": "WORKING_DAY",
                "description": "cấp có thẩm quyền xem xét, ban hành văn bản đồng ý",
            },
            {
                "submissionMethod": "ONLINE",
                "processingTime": 5,
                "processingTimeUnit": "WORKING_DAY",
                "description": "cấp có thẩm quyền xem xét, ban hành văn bản đồng ý",
            },
        ]
    )
    assert len(processing_time["muc_chi_tiet"]) == 1
    assert processing_time["muc_chi_tiet"][0]["hinh_thuc"] == ["Trực tiếp", "Trực tuyến"]


def test_processing_time_detail_not_merged_when_condition_differs() -> None:
    """CÙNG thời hạn nhưng KHÁC mô tả là hai tình huống khác nhau — không được gộp."""
    processing_time = build_processing_time(
        [
            {
                "submissionMethod": "DIRECT",
                "processingTime": 5,
                "processingTimeUnit": "WORKING_DAY",
                "description": "cơ quan chuyên môn trình Chủ tịch UBND tỉnh",
            },
            {
                "submissionMethod": "DIRECT",
                "processingTime": 5,
                "processingTimeUnit": "WORKING_DAY",
                "description": "cấp có thẩm quyền xem xét, ban hành văn bản",
            },
        ]
    )
    assert len(processing_time["muc_chi_tiet"]) == 2


def test_processing_time_detail_adds_milestone_from_description() -> None:
    """Đơn vị OTHER thì mốc lấy từ mô tả — chi tiết vẫn phải sinh ra."""
    processing_time = build_processing_time(
        [
            {
                "submissionMethod": "DIRECT",
                "processingTime": 0,
                "processingTimeUnit": "OTHER",
                "description": "Thời hạn giải quyết 90 ngày kể từ ngày nhận hồ sơ",
            }
        ]
    )
    assert processing_time["loai"] == "TRONG_TEXT"
    assert any(m["gia_tri"] == 90 and m["don_vi"] == "DAY" for m in processing_time["muc_chi_tiet"])


def test_processing_time_detail_empty_when_unknown() -> None:
    processing_time = build_processing_time([])
    assert processing_time["muc_chi_tiet"] == []
    assert processing_time["moc"] == []
