from __future__ import annotations

import pytest
from backend.app.documents.importer import (
    build_headers,
    build_object_key,
    import_attachments,
    validate_content_type,
    validate_extension,
)
from backend.app.documents.types import SourceAttachment


def make_attachment(**overrides) -> SourceAttachment:
    data = {
        "procedure_code": "1.001699",
        "profile_component_id": "component-1",
        "document_name": "Đơn đề nghị",
        "file_name": "Mus01 don.docx",
        "file_id": "file-1",
        "source_bucket": "dvc",
        "source_path": "configuring/file-1/Mus01 don.docx",
        "source_url": "https://dichvucong.gov.vn/thu-tuc-hanh-chinh/abc",
        "case_index": 0,
        "component_index": 0,
        "attachment_index": 0,
    }
    data.update(overrides)
    return SourceAttachment(**data)


def test_build_headers_dung_referer() -> None:
    headers = build_headers(make_attachment())

    assert headers["Content-Type"] == "application/json; charset=UTF-8"
    assert headers["Accept"] == "application/json;odata=verbose"
    assert headers["Referer"].endswith("/abc")


def test_object_key_co_ma_va_checksum() -> None:
    key = build_object_key("1.001699", "a" * 64, ".docx")

    assert key == f"procedures/1.001699/{'a' * 64}.docx"


def test_validate_extension_chap_nhan_docx() -> None:
    assert validate_extension("Mus01 don.docx") == ".docx"


def test_validate_extension_tu_choi_exe() -> None:
    with pytest.raises(ValueError):
        validate_extension("virus.exe")


def test_validate_content_type_chap_nhan_cfb_cho_doc() -> None:
    assert (
        validate_content_type("application/x-cfb", ".doc")
        == "application/msword"
    )


def test_validate_content_type_tu_choi_cfb_cho_docx() -> None:
    with pytest.raises(ValueError):
        validate_content_type("application/x-cfb", ".docx")


def test_validate_content_type_giu_nguyen_docx() -> None:
    content_type = (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    )

    assert validate_content_type(content_type, ".docx") == content_type


def test_import_attachments_giu_cung_file_id_o_thu_tuc_khac(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_import(attachment: SourceAttachment, storage: object) -> str:
        calls.append(attachment.procedure_code)
        return "uploaded"

    monkeypatch.setattr(
        "backend.app.documents.importer.import_attachment",
        fake_import,
    )

    stats = import_attachments(
        [
            make_attachment(procedure_code="1.001699", file_id="same-file"),
            make_attachment(procedure_code="1.001700", file_id="same-file"),
        ],
        storage=object(),
        delay=0,
    )

    assert calls == ["1.001699", "1.001700"]
    assert stats.attachments == 2


def test_import_attachments_bo_qua_file_id_trung_trong_cung_thu_tuc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fake_import(attachment: SourceAttachment, storage: object) -> str:
        calls.append(attachment.file_id)
        return "uploaded"

    monkeypatch.setattr(
        "backend.app.documents.importer.import_attachment",
        fake_import,
    )

    stats = import_attachments(
        [
            make_attachment(procedure_code="1.001699", file_id="same-file"),
            make_attachment(procedure_code="1.001699", file_id="same-file"),
        ],
        storage=object(),
        delay=0,
    )

    assert calls == ["same-file"]
    assert stats.duplicates == 1