"""Hai bản ``normalize_key`` phải cho kết quả giống hệt nhau.

Backend có bản sao của hàm trong ``data_pipeline/indexing/neo4j.py``. Nếu ai sửa một
bên mà quên bên kia, ``VanBanPhapLy.key`` sẽ không còn khớp và truy vấn T4 trả **0
dòng mà không báo lỗi** — đúng loại hỏng im lặng khó phát hiện nhất.

Test này là hàng rào: hai bản lệch nhau là đỏ ngay.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from backend.app.text_norm import (
    document_name_phrases,
    document_numbers,
    normalize_key,
    strip_accents,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _bo_index():
    """Nạp module bộ index theo đường dẫn, để không phụ thuộc ``sys.path``."""
    duong_dan = REPO_ROOT / "data_pipeline" / "indexing" / "neo4j.py"
    if not duong_dan.exists():
        pytest.skip("không tìm thấy data_pipeline/indexing/neo4j.py")
    spec = importlib.util.spec_from_file_location("_pipeline_neo4j", duong_dan)
    if spec is None or spec.loader is None:
        pytest.skip("không nạp được module bộ index")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_pipeline_neo4j"] = module
    spec.loader.exec_module(module)
    return module


MAU = [
    "102/2024/NĐ-CP",
    "102/2024/ND CP",
    "31/2024/QH15",
    "104/2026/QĐ-UBND",
    "816/QĐ-UBND",
    "08/2023/TT-BLĐTBXH",
    "09/2025/NQ-HĐND",
    "49/2026/NĐ-CP",
    "01/2019/TT BLDTBXH",
    " 136/2025/TT-BTC ",
    "NGHỊ ĐỊNH SỐ 136/2025/NĐ-CP",
    "",
    "không có số hiệu",
]


@pytest.mark.parametrize("mau", MAU)
def test_normalize_key_giong_bo_index(mau: str) -> None:
    """Backend và bộ index phải chuẩn hoá **y hệt** nhau."""
    pipeline = _bo_index()
    assert normalize_key(mau) == pipeline.normalize_key(mau), (
        f"normalize_key lệch giữa backend và bộ index với {mau!r} — "
        "sửa một bên mà quên bên kia sẽ làm truy vấn văn bản trả 0 dòng"
    )


def test_normalize_key_dung_dang_luu_trong_db() -> None:
    """Giá trị này là **đo được** từ Neo4j thật, không phải suy đoán."""
    assert normalize_key("102/2024/NĐ-CP") == "102/2024/ND CP"
    assert normalize_key("31/2024/QH15") == "31/2024/QH15"
    assert normalize_key("104/2026/QĐ-UBND") == "104/2026/QD UBND"


def test_document_numbers_trich_va_chuan_hoa() -> None:
    assert document_numbers("Nghị định 102/2024/NĐ-CP là căn cứ của thủ tục nào?") == [
        "102/2024/ND CP"
    ]
    # Hai văn bản trong một câu.
    assert document_numbers("So sánh 31/2024/QH15 và 102/2024/NĐ-CP") == [
        "31/2024/QH15",
        "102/2024/ND CP",
    ]
    # Số điện thoại / mã thủ tục không bị nhận nhầm là số hiệu văn bản.
    assert document_numbers("Thủ tục 1.115374, điện thoại 0901234567") == []


def test_document_name_phrases_cat_dung_menh_de() -> None:
    assert document_name_phrases("Luật Đất đai là căn cứ của thủ tục nào?") == ["Đất đai"]
    assert document_name_phrases("Nghị định thư quy định về hồ sơ") == ["thư"]
    # Có số hiệu thì KHÔNG trích tên — nhánh tên chỉ dùng khi thiếu số hiệu.
    assert document_name_phrases("Nghị định 102/2024/NĐ-CP quy định gì?") == []


def test_strip_accents_bo_dau() -> None:
    assert strip_accents("Luật Đất đai") == "luat dat dai"
    assert strip_accents("Cấp tỉnh") == "cap tinh"
