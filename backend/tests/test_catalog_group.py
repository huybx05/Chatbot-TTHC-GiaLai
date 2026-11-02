from __future__ import annotations

from data_pipeline.crawler.catalog import parse_group_from_sheet_name


def test_group_name_removes_leading_number() -> None:
    assert parse_group_from_sheet_name("05. LAO_DONG_AN_SINH_XA_HOI") == (
        "LAO_DONG_AN_SINH_XA_HOI"
    )
    assert parse_group_from_sheet_name("2.CONG_THUONG_NANG_LUONG") == (
        "CONG_THUONG_NANG_LUONG"
    )


def test_group_name_without_number_is_kept() -> None:
    assert parse_group_from_sheet_name("TU_PHAP_BO_TRO") == "TU_PHAP_BO_TRO"
