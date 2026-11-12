"""Đại từ "thủ tục này" chỉ cần hỏi lại khi thật sự không có tiền ngữ."""

from __future__ import annotations

from backend.app.rag.resolve import Resolution
from backend.app.workflow.graph import _thieu_tien_ngu


def test_dai_tu_sau_khi_da_dinh_danh_khong_bo_thanh_clarify() -> None:
    resolution = Resolution(
        question="Huy làm thủ tục đăng ký khai sinh, thủ tục này liên quan gì?",
        ma="1.001193",
        ten="Thủ tục đăng ký khai sinh",
    )

    assert not _thieu_tien_ngu(
        resolution.question,
        resolution,
        co_active=False,
        frame_missing_subject=False,
    )


def test_dai_tu_khong_co_tien_ngu_van_hoi_lai() -> None:
    resolution = Resolution(question="Thủ tục này liên quan gì?")

    assert _thieu_tien_ngu(
        resolution.question,
        resolution,
        co_active=False,
        frame_missing_subject=False,
    )
