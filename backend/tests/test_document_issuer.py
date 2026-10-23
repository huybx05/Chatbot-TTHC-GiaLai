"""Test bảng suy cơ quan ban hành từ hậu tố số hiệu văn bản."""

from __future__ import annotations

import pytest
from data_pipeline.indexing.neo4j import (
    DOCUMENT_ISSUER_SUFFIX,
    document_issuing_agency,
)


@pytest.mark.parametrize(
    ("so_hieu", "mong_doi"),
    [
        ("105/2016/QH13", "Quốc hội"),
        ("44/2024/QH15", "Quốc hội"),
        ("68/2020/QH14", "Quốc hội"),
        ("163/2025/ND CP", "Chính phủ"),
        ("42/2025/ND CP", "Chính phủ"),
        ("66 7/2025/NQ CP", "Chính phủ"),
        ("41/2023/TT BTC", "Bộ Tài chính"),
        ("04/2020/TT BTP", "Bộ Tư pháp"),
        ("15/2024/TT BYT", "Bộ Y tế"),
        ("08/2023/TT BLDTBXH", "Bộ Lao động - Thương binh và Xã hội"),
        ("10/2024/TT BTNMT", "Bộ Tài nguyên và Môi trường"),
        ("104/2026/QD UBND", "UBND tỉnh"),
        ("09/2025/NQ HDND", "Hội đồng nhân dân"),
    ],
)
def test_suy_duoc_co_quan(so_hieu: str, mong_doi: str) -> None:
    assert document_issuing_agency(so_hieu) == mong_doi


@pytest.mark.parametrize(
    "so_hieu",
    [
        "",  # rỗng
        "CUU HO",  # dữ liệu rác, không có dấu /
        "NGHI DINH QUY DINH CHI TIET",  # tên bị dùng làm mã
        "12/2024/XX YY",  # hậu tố lạ
    ],
)
def test_khong_suy_duoc_tra_none(so_hieu: str) -> None:
    assert document_issuing_agency(so_hieu) is None


def test_hau_to_long_nhat_thang() -> None:
    """``TT BTTTT`` không được cắt nhầm thành ``TT BTT``, và ``ND CP`` không lấn ``NQ CP``."""
    assert document_issuing_agency("01/2024/TT BTTTT") == "Bộ Thông tin và Truyền thông"
    assert document_issuing_agency("01/2024/NQ CP") == "Chính phủ"


def test_bang_khong_co_hau_to_trung_lap_nguy_hiem() -> None:
    """Không hai hậu tố nào trùng nhau — nếu trùng, kết quả phụ thuộc thứ tự."""
    hau_to = [h for h, _ in DOCUMENT_ISSUER_SUFFIX]
    assert len(hau_to) == len(set(hau_to))
