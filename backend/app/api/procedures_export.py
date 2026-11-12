"""Xuất danh sách thủ tục hành chính ra Excel cho báo cáo quản trị."""

from __future__ import annotations

import io
from collections import Counter
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import text

from backend.app.auth.dependencies import AdminUser, require_admin
from backend.app.db.postgres import engine

router = APIRouter(
    prefix="/procedures",
    tags=["admin-procedure-export"],
    dependencies=[Depends(require_admin)],
)

#: Nhãn hiển thị cho 15 domain_group. Fallback vẫn hoạt động nếu có nhóm mới.
DOMAIN_GROUP_LABELS: dict[str, str] = {
    "THONG_TIN_KHOA_HOC_CONG_NGHE": "Thông tin và Khoa học công nghệ",
    "CONG_THUONG_NANG_LUONG": "Công thương và Năng lượng",
    "TU_PHAP_BO_TRO": "Tư pháp và Bổ trợ tư pháp",
    "NONG_LAM_THUY_SAN": "Nông nghiệp, Lâm nghiệp và Thủy sản",
    "XAY_DUNG_GIAO_THONG": "Xây dựng và Giao thông",
    "TAI_NGUYEN_MOI_TRUONG": "Tài nguyên và Môi trường",
    "VAN_HOA_THE_THAO_DU_LICH": "Văn hóa, Thể thao và Du lịch",
    "LAO_DONG_AN_SINH_XA_HOI": "Lao động, An sinh xã hội",
    "Y_TE_SUC_KHOE": "Y tế và Sức khỏe",
    "DOANH_NGHIEP_DAU_TU": "Doanh nghiệp và Đầu tư",
    "NOI_VU_TON_GIAO_DAN_TOC": "Nội vụ, Tôn giáo và Dân tộc",
    "GIAO_DUC_DAO_TAO": "Giáo dục và Đào tạo",
    "QUOC_PHONG_NGOAI_VU": "Quốc phòng và Ngoại vụ",
    "TAI_CHINH_NGAN_SACH": "Tài chính và Ngân sách",
    "AN_NINH_TRAT_TU_CU_TRU": "An ninh, Trật tự và Cư trú",
}

STATUS_LABELS = {
    "UPDATED": "Đã cập nhật",
    "ACTIVE": "Đang áp dụng",
    "Đã công khai": "Đã công khai",
}

HEADERS = (
    "STT",
    "Mã TTHC",
    "Tên TTHC",
    "Lĩnh vực",
    "Nhóm lĩnh vực",
    "Cấp thực hiện",
    "Cơ quan ban hành",
    "Số quyết định",
    "Ngày quyết định",
    "Trạng thái",
    "Nguồn",
)

_HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
_HEADER_FONT = Font(bold=True, color="FFFFFF")
_THIN = Side(style="thin", color="D9E2F3")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


def group_label(value: str) -> str:
    slug = str(value or "").strip()
    if not slug:
        return "Chưa xác định"
    if slug in DOMAIN_GROUP_LABELS:
        return DOMAIN_GROUP_LABELS[slug]
    return slug.replace("_", " ").strip().title()


def status_label(value: str) -> str:
    raw = str(value or "").strip()
    return STATUS_LABELS.get(raw, raw or "Chưa xác định")


def _audit(conn: Any, admin: dict[str, Any], *, rows: int, filters: dict[str, Any]) -> None:
    user_id = admin.get("id")
    if user_id is not None and conn.execute(
        text("SELECT 1 FROM users WHERE id = :id"), {"id": user_id}
    ).first() is None:
        user_id = None
    import json

    conn.execute(
        text(
            """
            INSERT INTO audit_logs (user_id, action, entity, detail)
            VALUES (:user_id, 'procedure_export', 'procedures', CAST(:detail AS jsonb))
            """
        ),
        {
            "user_id": user_id,
            "detail": json.dumps(
                {"rows": rows, "filters": filters}, ensure_ascii=False
            ),
        },
    )


def _query(
    *,
    q: str,
    domain_group: str,
    status: str,
    source_fields: list[str],
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: dict[str, Any] = {}
    if q.strip():
        conditions.append(
            "(p.procedure_code ILIKE :pattern OR p.procedure_name ILIKE :pattern)"
        )
        params["pattern"] = f"%{q.strip()}%"
    if domain_group.strip():
        conditions.append("p.domain_group = :domain_group")
        params["domain_group"] = domain_group.strip()
    if status.strip():
        conditions.append("p.status = :status")
        params["status"] = status.strip()
    cleaned_fields = [item for item in source_fields if item.strip()]
    if cleaned_fields:
        conditions.append("p.source_field = ANY(:source_fields)")
        params["source_fields"] = cleaned_fields
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    sql = text(
        f"""
        SELECT
            p.procedure_code,
            p.procedure_name,
            p.domain_group,
            p.source_field,
            p.administrative_levels,
            p.issuing_agency,
            p.decision_number,
            p.decision_date,
            p.status,
            p.detail_url,
            p.updated_at
          FROM procedures AS p
          {where}
         ORDER BY
            NULLIF(BTRIM(p.decision_date), '') DESC NULLS LAST,
            p.updated_at DESC NULLS LAST,
            p.procedure_code
        """
    )
    with engine.connect() as conn:
        return [dict(row) for row in conn.execute(sql, params).mappings().all()]


def _style_header(sheet: Any, columns: int) -> None:
    for col in range(1, columns + 1):
        cell = sheet.cell(row=1, column=col)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _BORDER
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:{get_column_letter(columns)}{max(1, sheet.max_row)}"


def _write_summary(sheet: Any, rows: list[dict[str, Any]]) -> None:
    sheet.title = "Tổng hợp"
    sheet["A1"] = "TỔNG HỢP THỦ TỤC HÀNH CHÍNH"
    sheet["A1"].font = Font(bold=True, size=14, color="1F4E78")
    sheet["A3"] = "Tổng số thủ tục"
    sheet["B3"] = len(rows)
    sheet["A3"].font = Font(bold=True)

    group_counts = Counter(
        group_label(str(row.get("domain_group") or "")) for row in rows
    )
    sheet["A5"] = "Nhóm lĩnh vực"
    sheet["B5"] = "Số lượng"
    for cell in (sheet["A5"], sheet["B5"]):
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.border = _BORDER
    row_index = 6
    for label, count in group_counts.most_common():
        sheet.cell(row=row_index, column=1, value=label).border = _BORDER
        sheet.cell(row=row_index, column=2, value=count).border = _BORDER
        row_index += 1

    field_counts = Counter(
        str(row.get("source_field") or "Chưa xác định").strip() for row in rows
    )
    start = row_index + 2
    sheet.cell(row=start, column=1, value="Lĩnh vực").font = _HEADER_FONT
    sheet.cell(row=start, column=2, value="Số lượng").font = _HEADER_FONT
    for cell in (sheet.cell(row=start, column=1), sheet.cell(row=start, column=2)):
        cell.fill = _HEADER_FILL
        cell.border = _BORDER
    for offset, (label, count) in enumerate(field_counts.most_common(), start=1):
        sheet.cell(row=start + offset, column=1, value=label).border = _BORDER
        sheet.cell(row=start + offset, column=2, value=count).border = _BORDER
    sheet.column_dimensions["A"].width = 46
    sheet.column_dimensions["B"].width = 14


def _build_workbook(rows: list[dict[str, Any]]) -> Workbook:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Danh sách TTHC"
    sheet.append(list(HEADERS))
    _style_header(sheet, len(HEADERS))

    for index, row in enumerate(rows, start=1):
        levels = row.get("administrative_levels") or []
        if isinstance(levels, str):
            levels = [levels]
        url = str(row.get("detail_url") or "").strip()
        raw_date = str(row.get("decision_date") or "").strip()
        try:
            decision_date: Any = date.fromisoformat(raw_date) if raw_date else ""
        except ValueError:
            decision_date = raw_date
        sheet.append(
            [
                index,
                str(row.get("procedure_code") or ""),
                str(row.get("procedure_name") or ""),
                str(row.get("source_field") or ""),
                group_label(str(row.get("domain_group") or "")),
                "; ".join(str(item) for item in levels if str(item).strip()),
                str(row.get("issuing_agency") or ""),
                str(row.get("decision_number") or ""),
                decision_date,
                status_label(str(row.get("status") or "")),
                "Xem nguồn" if url else "",
            ]
        )
        row_index = sheet.max_row
        sheet.cell(row=row_index, column=1).alignment = Alignment(horizontal="center")
        # Giữ mã TTHC dạng text để Excel không đổi 1.014137 thành số.
        sheet.cell(row=row_index, column=2).number_format = "@"
        sheet.cell(row=row_index, column=8).number_format = "@"
        if isinstance(decision_date, date):
            sheet.cell(row=row_index, column=9).number_format = "DD/MM/YYYY"
        elif decision_date:
            sheet.cell(row=row_index, column=9).number_format = "@"
        if url:
            cell = sheet.cell(row=row_index, column=11)
            cell.hyperlink = url
            cell.style = "Hyperlink"
        for col in range(1, len(HEADERS) + 1):
            sheet.cell(row=row_index, column=col).border = _BORDER
            sheet.cell(row=row_index, column=col).alignment = Alignment(
                vertical="top", wrap_text=col in (3, 4, 5)
            )

    widths = {
        "A": 6,
        "B": 16,
        "C": 58,
        "D": 32,
        "E": 32,
        "F": 26,
        "G": 30,
        "H": 20,
        "I": 18,
        "J": 18,
        "K": 14,
    }
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width

    summary = workbook.create_sheet("Tổng hợp")
    _write_summary(summary, rows)
    return workbook


@router.get("/export")
def export_procedures(
    admin: AdminUser,
    q: str = Query(default="", max_length=200),
    domain_group: str = Query(default="", max_length=100),
    status: str = Query(default="", max_length=50),
    source_field: Annotated[list[str] | None, Query()] = None,
) -> StreamingResponse:
    rows = _query(
        q=q,
        domain_group=domain_group,
        status=status,
        source_fields=source_field or [],
    )
    workbook = _build_workbook(rows)
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)

    with engine.begin() as conn:
        _audit(
            conn,
            admin,
            rows=len(rows),
            filters={
                "q": q,
                "domain_group": domain_group,
                "status": status,
                "source_field": source_field,
            },
        )

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="danh_sach_tthc.xlsx"'
        },
    )
