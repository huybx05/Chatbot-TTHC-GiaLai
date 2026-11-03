from __future__ import annotations

import hashlib
import io
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from sqlalchemy import text

from backend.app.db.postgres import engine
from backend.app.documents.storage import S3Storage
from backend.app.documents.types import SourceAttachment

DVC_PREVIEW_URL = (
    "https://dichvucong.gov.vn/api/v1/submitting/preview-attachment"
)
MAX_BYTES = 20 * 1024 * 1024
CHUNK_SIZE = 256 * 1024

ALLOWED_EXTENSIONS = {".doc", ".docx", ".pdf", ".xls", ".xlsx"}

ALLOWED_MIME_TYPES = {
    "application/msword",
    "application/pdf",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

# File .doc/.xls cũ có thể được cổng trả về dưới dạng Compound File Binary.
# Chỉ chấp nhận các MIME này cho đúng đuôi OLE, và chuẩn hoá lại MIME chuẩn.
CFB_MIME_TYPES = {
    "application/x-cfb",
    "application/cdfv2",
    "application/x-ole-storage",
}

CFB_MIME_BY_EXTENSION = {
    ".doc": "application/msword",
    ".xls": "application/vnd.ms-excel",
}

#: Một số file trên cổng DVC trả Content-Type chung chung.
#: Chỉ chuẩn hoá theo đuôi đã được validate trước khi gọi hàm này.
GENERIC_MIME_TYPES = {
    "application/octet-stream",
    "binary/octet-stream",
}

GENERIC_MIME_BY_EXTENSION = {
    ".doc": "application/msword",
    ".docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
    ".xls": "application/vnd.ms-excel",
    ".xlsx": (
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    ),
    ".pdf": "application/pdf",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

UPSERT_SQL = """
INSERT INTO procedure_documents (
    procedure_code,
    profile_component_id,
    file_id,
    file_ids,
    case_order,
    component_index,
    case_orders,
    component_indexes,
    document_name,
    file_name,
    mime_type,
    size_bytes,
    checksum_sha256,
    object_key,
    source_bucket,
    source_path,
    source_url,
    sort_order,
    is_active
) VALUES (
    :procedure_code,
    :profile_component_id,
    :file_id,
    ARRAY[:file_id]::text[],
    :case_order,
    :component_index,
    ARRAY[:case_order]::int[],
    ARRAY[:component_index]::int[],
    :document_name,
    :file_name,
    :mime_type,
    :size_bytes,
    :checksum_sha256,
    :object_key,
    :source_bucket,
    :source_path,
    :source_url,
    :sort_order,
    TRUE
)
ON CONFLICT (procedure_code, checksum_sha256)
DO UPDATE SET
    profile_component_id = EXCLUDED.profile_component_id,
    file_id = EXCLUDED.file_id,
    file_ids = ARRAY(
        SELECT DISTINCT unnest(procedure_documents.file_ids || EXCLUDED.file_ids)
    ),
    case_order = EXCLUDED.case_order,
    component_index = EXCLUDED.component_index,
    case_orders = ARRAY(
        SELECT DISTINCT unnest(procedure_documents.case_orders || EXCLUDED.case_orders)
    ),
    component_indexes = ARRAY(
        SELECT DISTINCT unnest(
            procedure_documents.component_indexes || EXCLUDED.component_indexes
        )
    ),
    document_name = EXCLUDED.document_name,
    file_name = EXCLUDED.file_name,
    mime_type = EXCLUDED.mime_type,
    size_bytes = EXCLUDED.size_bytes,
    object_key = EXCLUDED.object_key,
    source_path = EXCLUDED.source_path,
    source_url = EXCLUDED.source_url,
    is_active = TRUE,
    updated_at = NOW()
"""


@dataclass(slots=True)
class FetchedFile:
    content: bytes
    mime_type: str
    checksum: str
    extension: str


@dataclass(slots=True)
class ImportStats:
    attachments: int = 0
    uploaded: int = 0
    existing: int = 0
    duplicates: int = 0
    failed: int = 0
    dry_run: int = 0
    errors: list[str] = field(default_factory=list)


def build_headers(attachment: SourceAttachment) -> dict[str, str]:
    return {
        "Accept": "application/json;odata=verbose",
        "Content-Type": "application/json; charset=UTF-8",
        "Referer": attachment.source_url
        or "https://dichvucong.gov.vn/",
        "User-Agent": USER_AGENT,
    }


def validate_extension(file_name: str) -> str:
    extension = Path(file_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Đuôi file không hợp lệ: {file_name}")
    return extension


def validate_content_type(content_type: str, extension: str) -> str:
    """Chuẩn hoá MIME; chấp nhận CFB và octet-stream theo đuôi file."""
    if content_type in CFB_MIME_TYPES:
        normalized = CFB_MIME_BY_EXTENSION.get(extension)
        if normalized is None:
            raise ValueError(
                f"Content-Type {content_type} không hợp lệ cho {extension}"
            )
        return normalized

    if content_type in GENERIC_MIME_TYPES:
        normalized = GENERIC_MIME_BY_EXTENSION.get(extension)
        if normalized is None:
            raise ValueError(
                f"Content-Type {content_type} không hợp lệ cho {extension}"
            )
        return normalized

    if content_type not in ALLOWED_MIME_TYPES:
        raise ValueError(f"Content-Type không hợp lệ: {content_type}")

    return content_type


def build_object_key(
    procedure_code: str,
    checksum: str,
    extension: str,
) -> str:
    return f"procedures/{procedure_code}/{checksum}{extension}"


def fetch_attachment(attachment: SourceAttachment) -> FetchedFile:
    if not attachment.file_id:
        raise ValueError("Attachment không có file_id")

    extension = validate_extension(attachment.file_name)

    with httpx.Client(follow_redirects=True, timeout=60.0) as client:
        with client.stream(
            "POST",
            DVC_PREVIEW_URL,
            json={"fileId": attachment.file_id},
            headers=build_headers(attachment),
        ) as response:
            if response.status_code not in {200, 201}:
                raise ValueError(
                    f"HTTP {response.status_code}: {attachment.file_name}"
                )

            content_type = (
                response.headers.get("content-type", "")
                .split(";")[0]
                .strip()
                .lower()
            )
            normalized_content_type = validate_content_type(
                content_type,
                extension,
            )

            hasher = hashlib.sha256()
            buffer = bytearray()

            for chunk in response.iter_bytes(CHUNK_SIZE):
                if not chunk:
                    continue

                buffer.extend(chunk)
                hasher.update(chunk)

                if len(buffer) > MAX_BYTES:
                    raise ValueError(
                        f"File quá lớn: {attachment.file_name}"
                    )

    if not buffer:
        raise ValueError(f"File rỗng: {attachment.file_name}")

    return FetchedFile(
        content=bytes(buffer),
        mime_type=normalized_content_type,
        checksum=hasher.hexdigest(),
        extension=extension,
    )


def _upsert_document(
    attachment: SourceAttachment,
    fetched: FetchedFile,
    object_key: str,
) -> None:
    params = {
        "procedure_code": attachment.procedure_code,
        "profile_component_id": attachment.profile_component_id or None,
        "file_id": attachment.file_id or None,
        "case_order": attachment.case_index + 1,
        "component_index": attachment.component_index + 1,
        "document_name": attachment.document_name or attachment.file_name,
        "file_name": attachment.file_name,
        "mime_type": fetched.mime_type,
        "size_bytes": len(fetched.content),
        "checksum_sha256": fetched.checksum,
        "object_key": object_key,
        "source_bucket": attachment.source_bucket or None,
        "source_path": attachment.source_path or None,
        "source_url": attachment.source_url or None,
        "sort_order": attachment.sort_order,
    }

    with engine.begin() as conn:
        conn.execute(text(UPSERT_SQL), params)


def import_attachment(
    attachment: SourceAttachment,
    storage: S3Storage,
) -> str:
    fetched = fetch_attachment(attachment)
    object_key = build_object_key(
        attachment.procedure_code,
        fetched.checksum,
        fetched.extension,
    )

    if storage.exists(object_key):
        status = "existing"
    else:
        storage.put_stream(
            object_key,
            io.BytesIO(fetched.content),
            content_type=fetched.mime_type,
        )
        status = "uploaded"

    _upsert_document(attachment, fetched, object_key)
    return status


def import_attachments(
    attachments: Iterable[SourceAttachment],
    storage: S3Storage,
    *,
    dry_run: bool = False,
    delay: float = 0.5,
) -> ImportStats:
    stats = ImportStats()
    seen_refs: set[tuple[str, str]] = set()

    for attachment in attachments:
        if not attachment.file_id:
            stats.failed += 1
            stats.errors.append(f"Thiếu file_id: {attachment.file_name}")
            continue

        ref = (attachment.procedure_code, attachment.file_id)
        if ref in seen_refs:
            stats.duplicates += 1
            continue

        seen_refs.add(ref)
        stats.attachments += 1

        if dry_run:
            stats.dry_run += 1
            continue

        try:
            status = import_attachment(attachment, storage)
            if status == "uploaded":
                stats.uploaded += 1
            else:
                stats.existing += 1
        except Exception as exc:  # noqa: BLE001
            stats.failed += 1
            stats.errors.append(f"{attachment.file_name}: {exc}")

        if delay > 0:
            time.sleep(delay)

    return stats