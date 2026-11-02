from __future__ import annotations

from backend.app.documents.source import extract_attachments


def test_trich_duoc_file_tu_execution_cases() -> None:
    record = {
        "ma_thu_tuc": "1.001699",
        "detail_url": "https://example.test/1.001699",
        "executionCases": [
            {
                "profileComponents": [
                    {
                        "profileComponentId": "component-1",
                        "name": "Đơn đề nghị theo Mẫu số 01",
                        "attachments": [
                            {
                                "id": "file-1",
                                "fileName": "Mus01 don.docx",
                                "bucketName": "dvc",
                                "filePath": "configuring/file-1/Mus01 don.docx",
                            }
                        ],
                    }
                ]
            }
        ],
    }

    rows = list(extract_attachments(record))

    assert len(rows) == 1
    assert rows[0].procedure_code == "1.001699"
    assert rows[0].file_name == "Mus01 don.docx"
    assert rows[0].file_id == "file-1"
    assert rows[0].source_bucket == "dvc"


def test_bo_qua_component_khong_co_attachment() -> None:
    record = {
        "ma_thu_tuc": "1.001699",
        "executionCases": [
            {
                "profileComponents": [
                    {"name": "Bản sao giấy tờ", "attachments": []}
                ]
            }
        ],
    }

    assert list(extract_attachments(record)) == []