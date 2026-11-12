"""Quản trị FAQ nâng cao: bulk, import/export Excel, template.

Toàn bộ route nằm dưới ``/api/admin`` và kế thừa ``require_admin``.
Import là all-or-nothing: validate hết file trước, chỉ ghi DB khi không có lỗi.
"""

from __future__ import annotations

import io
import json
import logging
import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.datavalidation import DataValidation
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.app.api.faq import FAQ_INTENTS
from backend.app.auth.dependencies import AdminUser, require_admin
from backend.app.config import settings
from backend.app.db.postgres import engine

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/faq",
    tags=["admin-faq"],
    dependencies=[Depends(require_admin)],
)

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 1_000

IMPORT_HEADERS = (
    "Câu hỏi",
    "Câu trả lời",
    "Mã thủ tục",
    "Danh mục",
    "Trạng thái",
)

EXPORT_HEADERS = (
    "Mã FAQ",
    "Câu hỏi",
    "Câu trả lời",
    "Mã thủ tục",
    "Tên thủ tục",
    "Danh mục",
    "Trạng thái",
    "Ngày tạo",
    "Ngày cập nhật",
)

_STATUS_LABELS = {
    "": "draft",
    "draft": "draft",
    "bản nháp": "draft",
    "ban nhap": "draft",
    "ready": "ready",
    "đang hoạt động": "ready",
    "dang hoat dong": "ready",
    "active": "ready",
}

_CATEGORY_LABELS = {
    label.casefold(): key for key, label in FAQ_INTENTS.items()
}
_CATEGORY_KEYS = set(FAQ_INTENTS)


class FaqBulkIds(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=MAX_IMPORT_ROWS)


class FaqBulkStatus(FaqBulkIds):
    status: Literal["ready", "draft"]


class ImportIssue(BaseModel):
    row: int
    column: str
    message: str


def normalize_question(value: str) -> str:
    """Chuẩn hóa câu hỏi giống lúc kiểm tra trùng."""
    return " ".join(str(value).casefold().split())


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value).strip()


def _header_map(values: tuple[Any, ...]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for index, value in enumerate(values):
        name = _cell_text(value)
        if name:
            mapping[name.casefold()] = index
    return mapping


def _parse_status(value: str) -> str | None:
    return _STATUS_LABELS.get(value.casefold().strip())


def _parse_category(value: str) -> str | None:
    normalized = value.casefold().strip()
    if normalized in _CATEGORY_KEYS:
        return normalized
    return _CATEGORY_LABELS.get(normalized)


def parse_faq_workbook(content: bytes) -> tuple[list[dict[str, Any]], list[ImportIssue]]:
    """Đọc và validate cấu trúc file; không truy cập DB."""
    issues: list[ImportIssue] = []
    try:
        workbook = load_workbook(
            io.BytesIO(content), read_only=True, data_only=False
        )
    except Exception:
        return [], [ImportIssue(row=1, column="File", message="Không đọc được file .xlsx.")]

    try:
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=False)
        try:
            header_cells = next(rows)
        except StopIteration:
            return [], [ImportIssue(row=1, column="File", message="File không có dữ liệu.")]

        mapping = _header_map(tuple(cell.value for cell in header_cells))
        indexes: dict[str, int] = {}
        for header in IMPORT_HEADERS:
            index = mapping.get(header.casefold())
            if index is None:
                issues.append(
                    ImportIssue(
                        row=1,
                        column=header,
                        message=f"Thiếu cột bắt buộc: {header}.",
                    )
                )
            else:
                indexes[header] = index
        if issues:
            return [], issues

        parsed: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for excel_row, cells in enumerate(rows, start=2):
            values = [_cell_text(cell.value) for cell in cells]
            if not any(values):
                continue

            def get(header: str, values: list[str] = values) -> str:
                index = indexes[header]
                return values[index] if index < len(values) else ""

            if any(
                cell.data_type == "f"
                for cell in cells[: max(indexes.values()) + 1]
            ):
                issues.append(
                    ImportIssue(
                        row=excel_row,
                        column="File",
                        message="Không chấp nhận ô công thức; hãy dán giá trị.",
                    )
                )
                continue

            question = get("Câu hỏi")
            answer = get("Câu trả lời")
            procedure_code = get("Mã thủ tục")
            category_raw = get("Danh mục")
            status_raw = get("Trạng thái")

            if not question:
                issues.append(
                    ImportIssue(row=excel_row, column="Câu hỏi", message="Không được để trống.")
                )
            if not answer:
                issues.append(
                    ImportIssue(
                        row=excel_row, column="Câu trả lời", message="Không được để trống."
                    )
                )
            if not category_raw:
                issues.append(
                    ImportIssue(row=excel_row, column="Danh mục", message="Không được để trống.")
                )
            category = _parse_category(category_raw) if category_raw else None
            if category_raw and category is None:
                issues.append(
                    ImportIssue(
                        row=excel_row,
                        column="Danh mục",
                        message="Danh mục không thuộc danh sách hỗ trợ.",
                    )
                )
            status = _parse_status(status_raw)
            if status is None:
                issues.append(
                    ImportIssue(
                        row=excel_row,
                        column="Trạng thái",
                        message="Chỉ nhận Bản nháp hoặc Đang hoạt động.",
                    )
                )

            if question and category and status is not None:
                key = (procedure_code.upper(), normalize_question(question))
                if key in seen:
                    issues.append(
                        ImportIssue(
                            row=excel_row,
                            column="Câu hỏi",
                            message="Trùng câu hỏi + mã thủ tục trong cùng file.",
                        )
                    )
                seen.add(key)
                parsed.append(
                    {
                        "row": excel_row,
                        "question": question,
                        "answer": answer,
                        "procedure_code": procedure_code or None,
                        "intent": category,
                        "status": status,
                    }
                )

        if len(parsed) > MAX_IMPORT_ROWS:
            issues.append(
                ImportIssue(
                    row=1,
                    column="File",
                    message=f"Tối đa {MAX_IMPORT_ROWS} dòng dữ liệu.",
                )
            )
        return parsed, issues
    finally:
        workbook.close()


def _faq_key(procedure_code: str | None, question: str) -> tuple[str, str]:
    return ((procedure_code or "").upper(), normalize_question(question))


def _load_procedure_map(
    conn: Any, codes: set[str]
) -> dict[str, dict[str, str]]:
    if not codes:
        return {}
    rows = conn.execute(
        text(
            """
            SELECT procedure_code, procedure_name, detail_url
              FROM procedures
             WHERE procedure_code = ANY(:codes)
            """
        ),
        {"codes": sorted(codes)},
    ).mappings().all()
    return {
        str(row["procedure_code"]): {
            "name": str(row["procedure_name"] or ""),
            "detail_url": str(row["detail_url"] or ""),
        }
        for row in rows
    }


def _existing_keys(conn: Any) -> set[tuple[str, str]]:
    rows = conn.execute(
        text(
            """
            SELECT procedure_code, question
              FROM faq
            """
        )
    ).mappings().all()
    return {
        _faq_key(
            str(row["procedure_code"]) if row["procedure_code"] else None,
            str(row["question"]),
        )
        for row in rows
    }


def _audit(
    conn: Any,
    admin: dict[str, Any],
    action: str,
    *,
    entity_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    user_id = admin.get("id")
    if user_id is not None:
        exists = conn.execute(
            text("SELECT 1 FROM users WHERE id = :id"),
            {"id": user_id},
        ).first()
        if exists is None:
            user_id = None
    conn.execute(
        text(
            """
            INSERT INTO audit_logs (user_id, action, entity, entity_id, detail)
            VALUES (:user_id, :action, 'faq', :entity_id, CAST(:detail AS jsonb))
            """
        ),
        {
            "user_id": user_id,
            "action": action,
            "entity_id": entity_id,
            "detail": json.dumps(detail or {}, ensure_ascii=False),
        },
    )


def _enforce_same_origin(request: Request) -> None:
    """Chặn form cross-site gửi kèm cookie admin.

    SameSite=Lax đã chặn phần lớn trường hợp; kiểm tra Origin là lớp thứ hai.
    Request không có Origin (curl, test) được phép.
    """
    origin = (request.headers.get("origin") or "").rstrip("/")
    if not origin:
        return
    origin_host = urlsplit(origin).hostname or ""
    request_host = (request.headers.get("host") or "").split(":", 1)[0].lower()
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    allowed = {
        item.strip().rstrip("/")
        for item in settings.cors_origins.split(",")
        if item.strip()
    }
    if (
        origin in allowed
        or origin_host == request_host
        or (origin_host in local_hosts and request_host in local_hosts)
    ):
        return
    raise HTTPException(status_code=403, detail="Origin không được phép.")


def _error_response(issues: list[ImportIssue]) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "message": "File không hợp lệ, chưa ghi dữ liệu nào.",
            "errors": [issue.model_dump() for issue in issues[:100]],
        },
    )


@router.post("/bulk/status")
def bulk_status(
    payload: FaqBulkStatus,
    admin: AdminUser,
    request: Request,
) -> dict[str, int]:
    _enforce_same_origin(request)
    ids = list(dict.fromkeys(payload.ids))
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                UPDATE faq
                   SET status = :status,
                       updated_at = NOW()
                 WHERE faq_id = ANY(:ids)
                """
            ),
            {"status": payload.status, "ids": ids},
        )
        if result.rowcount != len(ids):
            raise HTTPException(
                status_code=404,
                detail="Một hoặc nhiều FAQ không tồn tại; chưa thay đổi dòng nào.",
            )
        _audit(
            conn,
            admin,
            "faq_bulk_status",
            detail={"status": payload.status, "ids": [str(item) for item in ids]},
        )
    return {"updated": len(ids)}


@router.post("/bulk/delete")
def bulk_delete(
    payload: FaqBulkIds,
    admin: AdminUser,
    request: Request,
) -> dict[str, int]:
    _enforce_same_origin(request)
    ids = list(dict.fromkeys(payload.ids))
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM faq WHERE faq_id = ANY(:ids)"),
            {"ids": ids},
        )
        if result.rowcount != len(ids):
            raise HTTPException(
                status_code=404,
                detail="Một hoặc nhiều FAQ không tồn tại; chưa xóa dòng nào.",
            )
        _audit(
            conn,
            admin,
            "faq_bulk_delete",
            detail={"ids": [str(item) for item in ids]},
        )
    return {"deleted": len(ids)}


@router.post("/import")
async def import_faqs(
    admin: AdminUser,
    request: Request,
    file: Annotated[UploadFile, File()],
) -> dict[str, int]:
    _enforce_same_origin(request)
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Chỉ nhận file .xlsx.")
    content = await file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=400, detail="File vượt quá 5 MB.")
    if not content:
        raise HTTPException(status_code=400, detail="File rỗng.")

    rows, issues = parse_faq_workbook(content)
    if issues:
        raise _error_response(issues)
    if not rows:
        raise HTTPException(status_code=400, detail="File không có dòng dữ liệu.")
    if len(rows) > MAX_IMPORT_ROWS:
        raise HTTPException(
            status_code=400, detail=f"Tối đa {MAX_IMPORT_ROWS} dòng dữ liệu."
        )

    codes = {row["procedure_code"] for row in rows if row["procedure_code"]}
    with engine.begin() as conn:
        # Serialize import để hai file đồng thời không cùng lọt qua bước kiểm trùng.
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('faq_import'))"))
        procedure_map = _load_procedure_map(conn, codes)
        for code in codes:
            if code not in procedure_map:
                for row in rows:
                    if row["procedure_code"] == code:
                        issues.append(
                            ImportIssue(
                                row=row["row"],
                                column="Mã thủ tục",
                                message=f"Mã thủ tục {code} không tồn tại.",
                            )
                        )
        existing = _existing_keys(conn)
        for row in rows:
            key = _faq_key(row["procedure_code"], row["question"])
            if key in existing:
                issues.append(
                    ImportIssue(
                        row=row["row"],
                        column="Câu hỏi",
                        message="Câu hỏi + mã thủ tục đã tồn tại trong hệ thống.",
                    )
                )
        if issues:
            raise _error_response(issues)

        insert_sql = text(
            """
            INSERT INTO faq (
                procedure_code, procedure_name, question, answer, intent,
                status, priority, confidence, detail_url, created_by
            ) VALUES (
                :procedure_code, :procedure_name, :question, :answer, :intent,
                :status, 0, 1.0, :detail_url, :created_by
            )
            """
        )
        payload = []
        for row in rows:
            procedure = procedure_map.get(str(row["procedure_code"] or ""), {})
            payload.append(
                {
                    **row,
                    "procedure_name": procedure.get("name") or None,
                    "detail_url": procedure.get("detail_url") or None,
                    "created_by": str(admin.get("username") or "admin"),
                }
            )
        try:
            conn.execute(insert_sql, payload)
        except IntegrityError as exc:
            logger.warning("FAQ import integrity error: %s", exc)
            raise HTTPException(
                status_code=409,
                detail="Dữ liệu trùng hoặc không hợp lệ; chưa ghi dòng nào.",
            ) from exc

        _audit(
            conn,
            admin,
            "faq_import",
            detail={
                "file": file.filename,
                "rows": len(rows),
                "size_bytes": len(content),
            },
        )
    return {"imported": len(rows)}


def _excel_safe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _safe_filename(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value)[:120] or "faq_export.xlsx"


@router.get("/export")
def export_faqs(
    admin: AdminUser,
    status_filter: Literal["all", "ready", "draft"] = Query(
        default="all", alias="status"
    ),
    procedure_code: str = Query(default=""),
) -> StreamingResponse:
    conditions = []
    params: dict[str, Any] = {}
    if status_filter != "all":
        conditions.append("f.status = :status")
        params["status"] = status_filter
    if procedure_code.strip():
        conditions.append("f.procedure_code = :procedure_code")
        params["procedure_code"] = procedure_code.strip()
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT f.faq_id::text AS id,
                       f.question,
                       f.answer,
                       f.procedure_code,
                       COALESCE(p.procedure_name, f.procedure_name) AS procedure_name,
                       f.intent,
                       f.status,
                       f.created_at::text AS created_at,
                       f.updated_at::text AS updated_at
                  FROM faq AS f
                  LEFT JOIN procedures AS p
                    ON p.procedure_code = f.procedure_code
                  {where}
                 ORDER BY f.updated_at DESC
                """
            ),
            params,
        ).mappings().all()
        _audit(
            conn,
            admin,
            "faq_export",
            detail={
                "status": status_filter,
                "procedure_code": procedure_code.strip() or None,
                "rows": len(rows),
            },
        )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "FAQ"
    sheet.append(list(EXPORT_HEADERS))
    for row in rows:
        sheet.append(
            [
                _excel_safe(row["id"]),
                _excel_safe(row["question"]),
                _excel_safe(row["answer"]),
                _excel_safe(row["procedure_code"]) if row["procedure_code"] else "",
                _excel_safe(row["procedure_name"]) if row["procedure_name"] else "",
                _excel_safe(FAQ_INTENTS.get(str(row["intent"]), row["intent"])),
                "Đang hoạt động" if row["status"] == "ready" else "Bản nháp",
                _excel_safe(row["created_at"]),
                _excel_safe(row["updated_at"]),
            ]
        )
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = f"A1:I{max(1, sheet.max_row)}"
    for column, width in {
        "A": 38,
        "B": 48,
        "C": 70,
        "D": 16,
        "E": 36,
        "F": 24,
        "G": 18,
        "H": 22,
        "I": 22,
    }.items():
        sheet.column_dimensions[column].width = width

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    suffix = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{_safe_filename(f"faq_export_{suffix}.xlsx")}"'
            )
        },
    )


@router.get("/template")
def faq_template(admin: AdminUser) -> StreamingResponse:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "FAQ"
    sheet.append(list(IMPORT_HEADERS))
    sheet.freeze_panes = "A2"

    options = workbook.create_sheet("DanhMuc")
    for row_index, label in enumerate(FAQ_INTENTS.values(), start=1):
        options.cell(row=row_index, column=1, value=label)
    statuses = ["Bản nháp", "Đang hoạt động"]
    for row_index, label in enumerate(statuses, start=1):
        options.cell(row=row_index, column=2, value=label)
    options.sheet_state = "hidden"

    category_validation = DataValidation(
        type="list",
        formula1=f"DanhMuc!$A$1:$A${len(FAQ_INTENTS)}",
        allow_blank=False,
    )
    category_validation.error = "Chọn một danh mục trong danh sách."
    category_validation.errorTitle = "Danh mục không hợp lệ"
    category_validation.prompt = "Chọn danh mục của câu hỏi."
    category_validation.promptTitle = "Danh mục"
    sheet.add_data_validation(category_validation)
    category_validation.add("D2:D1001")

    status_validation = DataValidation(
        type="list",
        formula1="DanhMuc!$B$1:$B$2",
        allow_blank=True,
    )
    status_validation.error = "Chỉ chọn Bản nháp hoặc Đang hoạt động."
    status_validation.errorTitle = "Trạng thái không hợp lệ"
    status_validation.prompt = "Để trống = Bản nháp."
    status_validation.promptTitle = "Trạng thái"
    sheet.add_data_validation(status_validation)
    status_validation.add("E2:E1001")

    for column, width in {
        "A": 48,
        "B": 70,
        "C": 16,
        "D": 24,
        "E": 18,
    }.items():
        sheet.column_dimensions[column].width = width

    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    with engine.begin() as conn:
        _audit(conn, admin, "faq_template")
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="faq_template.xlsx"'
        },
    )
