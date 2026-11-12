from __future__ import annotations

import io
from uuid import uuid4

from backend.app.api.faq_admin import (
    IMPORT_HEADERS,
    MAX_IMPORT_ROWS,
    parse_faq_workbook,
)
from backend.app.db.postgres import engine
from backend.app.main import app
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import text

client = TestClient(app)


def _workbook(rows: list[list[object]]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(list(IMPORT_HEADERS))
    for row in rows:
        sheet.append(row)
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_parse_faq_workbook_hop_le_va_trang_thai_trong_la_draft() -> None:
    rows, errors = parse_faq_workbook(
        _workbook(
            [
                [
                    "Câu hỏi kiểm thử?",
                    "Câu trả lời kiểm thử.",
                    "",
                    "Hồ sơ, giấy tờ",
                    "",
                ]
            ]
        )
    )

    assert errors == []
    assert rows[0]["question"] == "Câu hỏi kiểm thử?"
    assert rows[0]["intent"] == "required_documents"
    assert rows[0]["status"] == "draft"
    assert rows[0]["procedure_code"] is None


def test_parse_faq_workbook_bao_loi_theo_dong() -> None:
    rows, errors = parse_faq_workbook(
        _workbook(
            [
                ["", "Câu trả lời", "", "Hồ sơ, giấy tờ", ""],
                ["Câu hỏi 2", "", "", "Danh mục sai", "không hợp lệ"],
            ]
        )
    )

    assert rows == []
    assert {issue.column for issue in errors} >= {
        "Câu hỏi",
        "Câu trả lời",
        "Danh mục",
        "Trạng thái",
    }
    assert all(issue.row >= 2 for issue in errors)


def test_parse_faq_workbook_tu_choi_trung_trong_file() -> None:
    rows, errors = parse_faq_workbook(
        _workbook(
            [
                ["Trùng câu hỏi", "Đáp án 1", "", "Hồ sơ, giấy tờ", ""],
                ["  trùng   CÂU hỏi ", "Đáp án 2", "", "Hồ sơ, giấy tờ", ""],
            ]
        )
    )

    assert len(rows) == 2
    assert any("Trùng câu hỏi" in issue.message for issue in errors)


def test_parse_faq_workbook_tu_choi_cong_thuc() -> None:
    data = _workbook([["Câu hỏi", "Đáp án", "", "Hồ sơ, giấy tờ", ""]])
    workbook = load_workbook(io.BytesIO(data))
    workbook.active["A2"] = "=1+1"
    output = io.BytesIO()
    workbook.save(output)

    rows, errors = parse_faq_workbook(output.getvalue())

    assert rows == []
    assert any("công thức" in issue.message for issue in errors)


def test_parse_faq_workbook_gioi_han_dong() -> None:
    rows, errors = parse_faq_workbook(
        _workbook(
            [
                ["Câu hỏi", "Đáp án", "", "Hồ sơ, giấy tờ", ""]
                for _ in range(MAX_IMPORT_ROWS + 1)
            ]
        )
    )

    assert len(rows) == MAX_IMPORT_ROWS + 1
    assert any("Tối đa" in issue.message for issue in errors)


def test_import_export_template_endpoints() -> None:
    marker = uuid4().hex
    created: list[str] = []
    try:
        imported = client.post(
            "/api/admin/faq/import",
            files={
                "file": (
                    "faq.xlsx",
                    _workbook(
                        [
                            [
                                f"Câu hỏi {marker}?",
                                "Câu trả lời import.",
                                "",
                                "Thông tin chung",
                                "Đang hoạt động",
                            ]
                        ]
                    ),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert imported.status_code == 200, imported.text
        assert imported.json()["imported"] == 1

        with engine.connect() as conn:
            created = [
                str(row["faq_id"])
                for row in conn.execute(
                    text(
                        "SELECT faq_id FROM faq WHERE question = :q"
                    ),
                    {"q": f"Câu hỏi {marker}?"},
                ).mappings()
            ]
        assert len(created) == 1

        exported = client.get("/api/admin/faq/export?status=ready")
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument"
        )
        exported_book = load_workbook(io.BytesIO(exported.content))
        assert exported_book.active["A1"].value == "Mã FAQ"

        template = client.get("/api/admin/faq/template")
        assert template.status_code == 200
        template_book = load_workbook(io.BytesIO(template.content))
        assert template_book.active["A1"].value == "Câu hỏi"
        validations = list(template_book.active.data_validations.dataValidation)
        assert validations
        assert template_book["DanhMuc"].sheet_state == "hidden"

        deleted = client.post(
            "/api/admin/faq/bulk/delete", json={"ids": created}
        )
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] == 1
        created = []
    finally:
        for faq_id in created:
            client.delete(f"/api/admin/faq/{faq_id}")


def test_bulk_status_all_or_nothing() -> None:
    created = client.post(
        "/api/admin/faq",
        json={
            "question": f"FAQ bulk {uuid4()}",
            "answer": "Đáp án",
            "intent": "general_info",
            "status": "draft",
        },
    )
    assert created.status_code == 200
    faq_id = created.json()["id"]
    try:
        result = client.post(
            "/api/admin/faq/bulk/status",
            json={"ids": [faq_id], "status": "ready"},
        )
        assert result.status_code == 200
        assert result.json()["updated"] == 1

        missing = client.post(
            "/api/admin/faq/bulk/status",
            json={"ids": [faq_id, str(uuid4())], "status": "draft"},
        )
        assert missing.status_code == 404
        with engine.connect() as conn:
            status = conn.execute(
                text("SELECT status FROM faq WHERE faq_id = :id"),
                {"id": faq_id},
            ).scalar_one()
        assert status == "ready"
    finally:
        client.delete(f"/api/admin/faq/{faq_id}")


def test_faq_id_khong_hop_le_tra_404() -> None:
    response = client.post(
        "/chat",
        json={"question": "Câu hỏi", "faq_id": str(uuid4())},
    )
    assert response.status_code == 404


def test_faq_gan_thu_tuc_tra_citation_detail_url() -> None:
    created = client.post(
        "/api/admin/faq",
        json={
            "question": f"FAQ citation {uuid4()}",
            "answer": "Câu trả lời có nguồn.",
            "intent": "general_info",
            "status": "ready",
            "procedure_code": "1.004873",
        },
    )
    assert created.status_code == 200
    faq_id = created.json()["id"]
    try:
        response = client.post(
            "/chat",
            json={"question": "FAQ citation", "faq_id": faq_id},
        )
        assert response.status_code == 200
        citations = response.json()["citations"]
        assert citations
        assert citations[0]["url"].startswith("http")
    finally:
        client.delete(f"/api/admin/faq/{faq_id}")
