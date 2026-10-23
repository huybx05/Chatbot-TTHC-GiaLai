"""Giai đoạn 4 — gỡ rối thủ tục bằng điều kiện thời hạn.

Dùng dữ liệu giả, không gọi mô hình, không chạm DB.
"""

from __future__ import annotations

import asyncio

from backend.app.rag import disambiguation


def _patch_cases(monkeypatch, data: dict[str, list[dict]]) -> None:
    async def fake_load(*_args, **_kwargs):
        return data

    monkeypatch.setattr(disambiguation.time_cases, "load", fake_load)


def _data() -> dict[str, list[dict]]:
    return {
        "1.115351": [
            {
                "gia_tri": 2,
                "don_vi": "WORKING_DAY",
                "dieu_kien": (
                    "Thời gian thực hiện thủ tục hành chính này được tính kể từ ngày "
                    "nhận được hồ sơ hợp lệ, không bao gồm thời gian giải quyết"
                ),
            }
        ],
        "1.115362": [
            {
                "gia_tri": 14,
                "don_vi": "WORKING_DAY",
                "dieu_kien": (
                    "Áp dụng đối với trường hợp cho thuê, cho thuê lại quyền sử dụng đất "
                    "trong dự án xây dựng kinh doanh kết cấu hạ tầng"
                ),
            },
            {
                "gia_tri": 17.5,
                "don_vi": "WORKING_DAY",
                "dieu_kien": "Áp dụng đối với trường hợp chuyển nhượng, thừa kế, tặng cho",
            },
        ],
    }


def test_case_coverage_co_ban() -> None:
    assert (
        disambiguation.case_coverage("cho thuê lại trong dự án", "cho thuê lại trong dự án")
        == 1.0
    )
    assert disambiguation.case_coverage("", "abc") == 0.0


def test_doi_thu_tuc_khi_tinh_huong_khop_dieu_kien(monkeypatch) -> None:
    _patch_cases(monkeypatch, _data())
    decision = asyncio.run(
        disambiguation.rerank(
            [
                ("1.115351", "Xóa đăng ký thuê", 0.8061),
                ("1.115362", "Đăng ký biến động", 0.7348),
            ],
            text="cho thuê lại quyền sử dụng đất trong dự án xây dựng kinh doanh kết cấu hạ tầng",
            facet="processing_time",
        )
    )
    assert decision is not None
    assert decision.code == "1.115362"
    assert decision.reason == "case_condition"


def test_khong_doi_khi_chenh_lech_nho(monkeypatch) -> None:
    _patch_cases(monkeypatch, _data())
    monkeypatch.setattr(disambiguation, "CASE_WEIGHT", 0.02)
    decision = asyncio.run(
        disambiguation.rerank(
            [
                ("1.115351", "Xóa", 0.9500),
                ("1.115362", "Đăng ký", 0.8000),
            ],
            text="cho thuê lại quyền sử dụng đất trong dự án xây dựng kinh doanh kết cấu hạ tầng",
            facet="processing_time",
        )
    )
    assert decision is None


def test_chi_ap_dung_cho_cau_hoi_thoi_han(monkeypatch) -> None:
    _patch_cases(monkeypatch, _data())
    decision = asyncio.run(
        disambiguation.rerank(
            [("1.115351", "Xóa", 0.8), ("1.115362", "Đăng ký", 0.7)],
            text="cho thuê lại trong dự án",
            facet="submission_method",
        )
    )
    assert decision is None


def test_thieu_tinh_huong_thi_khong_doi(monkeypatch) -> None:
    _patch_cases(monkeypatch, _data())
    decision = asyncio.run(
        disambiguation.rerank(
            [("1.115351", "Xóa", 0.8), ("1.115362", "Đăng ký", 0.7)],
            text="",
            facet="processing_time",
        )
    )
    assert decision is None
