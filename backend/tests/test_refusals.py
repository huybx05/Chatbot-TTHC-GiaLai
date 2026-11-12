"""Câu từ chối phải nói đúng trạng thái dữ liệu, không dùng một câu chung."""

from __future__ import annotations

from backend.app.workflow import refusals


def test_da_biet_ma_va_thieu_thoi_han() -> None:
    message = refusals.facet_not_recorded(
        facets=["processing_time"],
        code="1.004873",
        name="Thủ tục cấp Giấy xác nhận tình trạng hôn nhân",
    )

    assert "1.004873" in message
    assert "thời hạn giải quyết" in message
    assert "chưa ghi nhận" in message
    assert "nêu mã hoặc tên" not in message


def test_thieu_luu_y_chi_noi_luu_y() -> None:
    message = refusals.facet_not_recorded(
        facets=["notes"],
        code="1.004873",
        name="Thủ tục cấp Giấy xác nhận tình trạng hôn nhân",
    )

    assert "Lưu ý" in message
    assert "1.004873" in message


def test_nguon_loi_khac_du_lieu_khong_co() -> None:
    message = refusals.source_failed()

    assert "nguồn dữ liệu" in message.lower()
    assert "chưa phải" in message


def test_khong_ho_tro_khac_khong_ghi_nhan() -> None:
    message = refusals.unsupported_facet()

    assert "chưa hỗ trợ" in message
    assert "chưa ghi nhận" not in message
