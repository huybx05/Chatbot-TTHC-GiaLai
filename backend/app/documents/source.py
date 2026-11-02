from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from backend.app.documents.types import SourceAttachment


def _text(value: Any) -> str:
    """Chuẩn hoá khoảng trắng nhưng giữ nguyên nội dung."""
    return " ".join(str(value or "").split())


def _raw_text(value: Any) -> str:
    """Tên file: chỉ strip, không gộp khoảng trắng bên trong."""
    return str(value or "").strip()


def extract_attachments(
    record: dict[str, Any],
    *,
    procedure_code: str = "",
) -> Iterator[SourceAttachment]:
    """Sinh từng attachment từ một bản ghi raw API."""
    code = procedure_code or _raw_text(record.get("ma_thu_tuc"))
    detail_url = _raw_text(record.get("detail_url"))

    for case_index, case in enumerate(record.get("executionCases") or []):
        if not isinstance(case, dict):
            continue

        for component_index, component in enumerate(
            case.get("profileComponents") or []
        ):
            if not isinstance(component, dict):
                continue

            document_name = _text(component.get("name"))
            component_id = _raw_text(component.get("profileComponentId"))

            for attachment_index, attachment in enumerate(
                component.get("attachments") or []
            ):
                if not isinstance(attachment, dict):
                    continue

                file_name = _raw_text(attachment.get("fileName"))
                source_path = _raw_text(attachment.get("filePath"))
                if not file_name and not source_path:
                    continue

                yield SourceAttachment(
                    procedure_code=code,
                    profile_component_id=component_id,
                    document_name=document_name,
                    file_name=file_name,
                    file_id=_raw_text(attachment.get("id")),
                    source_bucket=_raw_text(attachment.get("bucketName")),
                    source_path=source_path,
                    source_url=detail_url,
                    case_index=case_index,
                    component_index=component_index,
                    attachment_index=attachment_index,
                )


def raw_paths(root: Path) -> list[Path]:
    """Toàn bộ file raw API, sắp xếp để kết quả tất định."""
    return sorted(root.rglob("*.json"))


def path_by_code(root: Path) -> dict[str, Path]:
    """`mã thủ tục → file raw` — quét một lần, không rglob lặp lại."""
    return {path.stem: path for path in raw_paths(root)}


def read_raw(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_attachments(
    root: Path,
    *,
    codes: Iterable[str] | None = None,
) -> Iterator[SourceAttachment]:
    """Duyệt attachment cho một danh sách mã, hoặc toàn bộ raw."""
    mapping = path_by_code(root)
    selected = list(codes) if codes else sorted(mapping)

    for code in selected:
        path = mapping.get(str(code))
        if path is None:
            continue

        try:
            record = read_raw(path)
        except (OSError, json.JSONDecodeError):
            continue

        yield from extract_attachments(record, procedure_code=str(code))