"""Lấy **mục nội dung** của thủ tục theo đúng khía cạnh câu hỏi (việc 13.13+).

Vì sao cần module này: câu hỏi nhiều ý bị trả lời thiếu không phải vì dữ liệu không có, mà vì
nhánh đã chạy chỉ lấy về **một** mẩu. Đo được: câu hỏi ba ý về thủ tục 1.001699 trúng kho FAQ
(trả về lệ phí), rồi câu trả lời nói "chưa ghi nhận thời hạn" — trong khi `PROCESSING_TIME` có
345 ký tự trong PostgreSQL.

Cách làm ở đây **không** phải thêm luật đoán câu hỏi: router đã tách câu hỏi thành các khía
cạnh thuộc chín giá trị đóng (:data:`~backend.app.workflow.state.NEED_HOP_LE`); module này ánh
xạ thẳng giá trị đó sang ``section_type`` trong bảng và đọc đúng dòng cần.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import text

from backend.app.db.postgres import engine

logger = logging.getLogger(__name__)

#: Ánh xạ **khía cạnh → giá trị ``section_type`` trong PostgreSQL**.
#:
#: Bảng này là chỗ duy nhất biết "hai bên gọi cùng một thứ bằng hai tên". Nó không đoán câu
#: hỏi — nó chỉ nối từ vựng của mô hình với từ vựng của dữ liệu. Dữ liệu có tên mới thì thêm
#: một dòng, không phải sửa luật nào.
KHIA_CANH_SANG_SECTION: dict[str, tuple[str, ...]] = {
    "required_documents": ("REQUIRED_DOCUMENTS",),
    "steps": ("STEPS",),
    "submission_method": ("SUBMISSION_METHOD",),
    "processing_time": ("PROCESSING_TIME",),
    "fee": ("FEE",),
    "result": ("RESULT",),
    "legal_basis": ("LEGAL_BASIS",),
    "requirements": ("REQUIREMENTS",),
    "general_info": ("GENERAL_INFO",),
}

#: Chiều ngược: ``section_type`` (chuẩn hoá) → khía cạnh. Dùng để biết bằng chứng đang có đã
#: phủ khía cạnh nào, nhờ vậy không truy xuất lại thứ đã có.
SECTION_SANG_KHIA_CANH: dict[str, str] = {
    gia_tri: khia_canh
    for khia_canh, cac_gia_tri in KHIA_CANH_SANG_SECTION.items()
    for gia_tri in cac_gia_tri
}

#: Dạng viết hoa/không dấu mà dữ liệu cũ dùng (``phi`` thay cho ``FEE``).
SECTION_BI_DANH: dict[str, str] = {
    "FEE": "FEE",
    "PHI": "FEE",
    "STEPS": "STEPS",
    "TRINH_TU_THUC_HIEN": "STEPS",
    "SUBMISSION_METHOD": "SUBMISSION_METHOD",
    "CACH_THUC_THUC_HIEN": "SUBMISSION_METHOD",
    "PROCESSING_TIME": "PROCESSING_TIME",
    "THOI_HAN": "PROCESSING_TIME",
    "REQUIRED_DOCUMENTS": "REQUIRED_DOCUMENTS",
    "THANH_PHAN_HO_SO": "REQUIRED_DOCUMENTS",
    "RESULT": "RESULT",
    "KET_QUA_XU_LY": "RESULT",
    "LEGAL_BASIS": "LEGAL_BASIS",
    "CAN_CU_PHAP_LY": "LEGAL_BASIS",
    "REQUIREMENTS": "REQUIREMENTS",
    "YEU_CAU_DIEU_KIEN": "REQUIREMENTS",
    "GENERAL_INFO": "GENERAL_INFO",
    "THONG_TIN_CHUNG": "GENERAL_INFO",
}


def khia_canh_cua(section_type: str) -> str | None:
    """``section_type`` thô của một mục bằng chứng ứng với khía cạnh nào.

    Dùng để tính **độ phủ**: khía cạnh nào đã có mục thì không truy xuất lại.
    """
    khoa = " ".join(str(section_type or "").split()).upper().replace(" ", "_")
    chuan = SECTION_BI_DANH.get(khoa, khoa)
    return SECTION_SANG_KHIA_CANH.get(chuan)


def _doc(codes: list[str], sections: list[str]) -> list[dict[str, Any]]:
    """Đọc các dòng cần dùng. Chạy trong thread vì ``engine`` là đồng bộ."""
    if not codes or not sections:
        return []

    sql = text(
        """
        SELECT s.procedure_code, s.section_type, s.title, s.content, s.detail_url,
               p.procedure_name
        FROM procedure_sections AS s
        LEFT JOIN procedures AS p ON p.procedure_code = s.procedure_code
        WHERE s.procedure_code = ANY(:codes)
          AND s.section_type = ANY(:sections)
        ORDER BY s.procedure_code, s.chunk_order
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"codes": codes, "sections": sections}).mappings()
        return [dict(r) for r in rows]


async def theo_khia_canh(codes: list[str], needs: list[str]) -> list[dict[str, Any]]:
    """Trả các mục của ``codes`` ứng với ``needs``.

    Không bao giờ ném lỗi: đây là bước **bổ sung**, DB lỗi thì lượt chạy vẫn đi tiếp với bằng
    chứng đã có — thiếu một mục còn hơn hỏng cả câu trả lời.
    """
    sections = [s for need in needs for s in KHIA_CANH_SANG_SECTION.get(need, ())]
    if not sections:
        return []

    try:
        return await asyncio.to_thread(_doc, list(codes), list(dict.fromkeys(sections)))
    except Exception as exc:  # noqa: BLE001 — bước bổ sung không được làm hỏng lượt
        logger.warning("Không đọc được mục nội dung theo khía cạnh: %s", str(exc)[:160])
        return []


async def theo_khia_canh_checked(
    codes: list[str], needs: list[str]
) -> tuple[list[dict[str, Any]], str]:
    """Như :func:`theo_khia_canh` nhưng **trả lỗi có cấu trúc** thay vì nuốt.

    Executor cần phân biệt "không có mục" với "PostgreSQL lỗi": cái đầu là ``empty``
    (dữ liệu không ghi nhận), cái sau là ``failed`` (hạ tầng lỗi). Trả ``(rows, error)``;
    ``error == ""`` nghĩa là truy vấn chạy được.
    """
    sections = [s for need in needs for s in KHIA_CANH_SANG_SECTION.get(need, ())]
    if not sections:
        return [], ""
    try:
        rows = await asyncio.to_thread(_doc, list(codes), list(dict.fromkeys(sections)))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Đọc mục nội dung lỗi: %s", exc)
        return [], f"{type(exc).__name__}: {str(exc)[:120]}"
    return rows, ""


__all__ = [
    "KHIA_CANH_SANG_SECTION",
    "SECTION_BI_DANH",
    "SECTION_SANG_KHIA_CANH",
    "khia_canh_cua",
    "theo_khia_canh_checked",
    "theo_khia_canh",
]
