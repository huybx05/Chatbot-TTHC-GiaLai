"""Giai đoạn 3 — gom nhóm thủ tục từ tên.

Không gọi mô hình, không chạm DB: chỉ kiểm tra hàm thuần và quyết định của nhóm.
"""

from __future__ import annotations

from backend.app.rag import themes

NAMES = [
    ("1.115348", "Đăng ký biến động chuyển mục đích sử dụng đất không phải xin phép"),
    ("1.115366", "Đăng ký biến động đối với trường hợp đổi tên hoặc thay đổi thông tin"),
    ("1.115362", "Đăng ký biến động quyền sử dụng đất, quyền sở hữu tài sản gắn liền với đất"),
    ("1.011441", "Đăng ký biện pháp bảo đảm bằng quyền sử dụng đất, tài sản gắn liền"),
    ("1.115342", "Đăng ký, cấp Giấy chứng nhận đối với trường hợp chuyển nhượng dự án"),
    ("1.115344", "Đăng ký, cấp Giấy chứng nhận đối với trường hợp hộ gia đình đang sử dụng"),
    ("1.000001", "Cấp đổi Giấy chứng nhận quyền sử dụng đất"),
]


def test_chuan_hoa_bo_dau_va_d_chuong() -> None:
    assert themes.normalize_name("Đăng ký biến động") == "dang ky bien dong"


def test_khoa_bon_tu_tach_bien_dong_khoi_bien_phap() -> None:
    a = themes.theme_key("Đăng ký biến động quyền sử dụng đất")
    b = themes.theme_key("Đăng ký biện pháp bảo đảm bằng quyền sử dụng đất")
    assert a == "dang ky bien dong"
    assert b == "dang ky bien phap"
    assert a != b


def test_gom_dung_nhom_va_bo_nhom_mot_thanh_vien() -> None:
    groups = themes.group_procedures(NAMES)
    keys = set(groups)
    assert "dang ky bien dong" in keys
    assert "dang ky cap giay" in keys
    assert len(groups["dang ky bien dong"]) == 3
    assert len(groups["dang ky cap giay"]) == 2
    # "Cấp đổi ..." chỉ có một thủ tục → không thành nhóm
    assert all(len(items) >= 2 for items in groups.values())


def test_theme_id_duoc_lam_sach_va_canonical_giu_nguyen() -> None:
    groups = themes.group_procedures(NAMES)
    danh_sach = themes.to_themes(groups, {"dang_ky_bien_dong": "1.115362"})
    by_id = {item.theme_id: item for item in danh_sach}
    assert "dang_ky_bien_dong" in by_id
    assert "dang_ky_cap_giay" in by_id, "dấu phẩy trong tên không được lọt vào id"
    assert by_id["dang_ky_bien_dong"].canonical_code == "1.115362"
    assert by_id["dang_ky_cap_giay"].canonical_code == ""


def test_index_tim_nhom_chung() -> None:
    groups = themes.group_procedures(NAMES)
    index = themes.ThemeIndex(themes.to_themes(groups, {}))
    assert index.theme_of("1.115362").theme_id == "dang_ky_bien_dong"
    assert index.common_theme(["1.115362", "1.115366"]) is not None
    assert index.common_theme(["1.115362", "1.115342"]) is None
    assert index.common_theme(["1.115362", "9.999999"]) is None


def test_index_rong_khi_chua_co_bang() -> None:
    index = themes.ThemeIndex()
    assert not index
    assert index.theme_of("1.115362") is None


def test_dominant_theme_khi_da_so_ung_vien_cung_nhom() -> None:
    index = themes.ThemeIndex(
        [
            themes.Theme(
                theme_id="dang_ky_bien_dong",
                label="Đăng ký biến động",
                canonical_code="1.115362",
                members=("1.115362", "1.115369"),
            )
        ]
    )
    found = index.dominant_theme(["1.115362", "1.115369", "1.115343"])
    assert found is not None and found.theme_id == "dang_ky_bien_dong"
    assert index.dominant_theme(["1.115362", "1.115343"]) is None
