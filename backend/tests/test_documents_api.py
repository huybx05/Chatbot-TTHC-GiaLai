from __future__ import annotations

import io
from uuid import UUID

from backend.app.documents.repository import DocumentRecord
from backend.app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

DOC_ID = UUID("11111111-1111-1111-1111-111111111111")


def make_document() -> DocumentRecord:
    return DocumentRecord(
        id=DOC_ID,
        procedure_code="1.001699",
        document_name="Đơn đề nghị",
        file_name="Mus01 don.docx",
        mime_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        size_bytes=3,
        checksum_sha256="a" * 64,
        object_key="procedures/1.001699/a.docx",
    )


def test_list_documents(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.documents.repository.procedure_exists",
        lambda code: True,
    )
    monkeypatch.setattr(
        "backend.app.documents.repository.list_documents",
        lambda code: [make_document()],
    )

    response = client.get("/api/v1/procedures/1.001699/documents")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["file_name"] == "Mus01 don.docx"
    assert body["items"][0]["download_url"].endswith(
        f"/documents/{DOC_ID}/download"
    )


def test_list_documents_thu_tuc_khong_ton_tai(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.documents.repository.procedure_exists",
        lambda code: False,
    )

    response = client.get("/api/v1/procedures/9.999999/documents")

    assert response.status_code == 404


def test_download_document(monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.app.documents.repository.get_document",
        lambda document_id: make_document(),
    )

    class FakeStorage:
        def open_stream(self, key: str):
            return io.BytesIO(b"abc")

    monkeypatch.setattr(
        "backend.app.api.documents.S3Storage.from_settings",
        lambda: FakeStorage(),
    )

    response = client.get(f"/api/v1/documents/{DOC_ID}/download")

    assert response.status_code == 200
    assert response.content == b"abc"
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats"
    )
    assert "attachment" in response.headers["content-disposition"]