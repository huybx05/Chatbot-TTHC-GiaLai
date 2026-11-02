from __future__ import annotations

from data_pipeline.indexing.neo4j import agency_values


def test_agency_falls_back_to_thuc_hien_when_tham_quyen_empty() -> None:
    record = {
        "co_quan_co_tham_quyen": "",
        "co_quan_thuc_hien": "Ủy ban Nhân dân xã, phường, thị trấn.",
    }

    assert agency_values(record, "co_quan_co_tham_quyen") == [
        "Ủy ban Nhân dân xã, phường, thị trấn."
    ]


def test_agency_prefers_tham_quyen_when_present() -> None:
    record = {
        "co_quan_co_tham_quyen": "Sở Tư pháp",
        "co_quan_thuc_hien": "Ủy ban Nhân dân xã",
    }

    assert agency_values(record, "co_quan_co_tham_quyen") == ["Sở Tư pháp"]


def test_agency_sentinel_is_skipped() -> None:
    record = {
        "co_quan_co_tham_quyen": "Không có thông tin",
        "co_quan_thuc_hien": "Không có thông tin",
    }

    assert agency_values(record, "co_quan_co_tham_quyen") == []


def test_agency_without_fallback_returns_value() -> None:
    record = {"co_quan_ban_hanh": "Bộ Y tế"}

    assert agency_values(record, "co_quan_ban_hanh") == ["Bộ Y tế"]
