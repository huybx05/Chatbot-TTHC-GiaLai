from __future__ import annotations

import io

from backend.app.db.postgres import engine
from backend.app.main import app
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import text

client = TestClient(app)


def test_export_procedures_mot_dong_moi_thu_tuc_va_sap_xep() -> None:
    with engine.connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM procedures")).scalar_one()

    response = client.get(
        "/api/admin/procedures/export",
        headers={"Host": "localhost"},
    )

    assert response.status_code == 200, response.text
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="danh_sach_tthc.xlsx"'
    )
    workbook = load_workbook(io.BytesIO(response.content))
    sheet = workbook["Danh sách TTHC"]
    assert [cell.value for cell in sheet[1]] == [
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
    ]
    assert sheet.max_row == total + 1

    dates = [
        str(sheet.cell(row=row, column=9).value or "")
        for row in range(2, min(sheet.max_row, 50) + 1)
    ]
    non_empty = [value for value in dates if value]
    assert non_empty == sorted(non_empty, reverse=True)
    assert all(
        sheet.cell(row=row, column=9).number_format == "DD/MM/YYYY"
        for row in range(2, min(sheet.max_row, 50) + 1)
        if sheet.cell(row=row, column=9).value
    )

    # Cột Lĩnh vực (D) đứng trước Nhóm lĩnh vực (E).
    assert sheet.cell(row=2, column=4).value
    assert sheet.cell(row=2, column=5).value
    assert "_" not in str(sheet.cell(row=2, column=5).value)


def test_export_filter_theo_linh_vuc() -> None:
    with engine.connect() as conn:
        source_field = conn.execute(
            text(
                """
                SELECT source_field
                  FROM procedures
                 WHERE nullif(btrim(source_field), '') IS NOT NULL
                 LIMIT 1
                """
            )
        ).scalar_one()
        expected = conn.execute(
            text("SELECT count(*) FROM procedures WHERE source_field = :field"),
            {"field": source_field},
        ).scalar_one()

    response = client.get(
        "/api/admin/procedures/export",
        params={"source_field": source_field},
        headers={"Host": "localhost"},
    )
    assert response.status_code == 200
    workbook = load_workbook(io.BytesIO(response.content))
    sheet = workbook["Danh sách TTHC"]
    assert sheet.max_row == expected + 1
    assert all(
        sheet.cell(row=row, column=4).value == source_field
        for row in range(2, sheet.max_row + 1)
    )
