from __future__ import annotations

import logging
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.app.config import settings
from backend.app.documents import repository
from backend.app.documents.storage import S3Storage, StorageError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])


class DocumentItem(BaseModel):
    id: UUID
    document_name: str
    file_name: str
    mime_type: str | None
    size_bytes: int | None
    download_url: str


class DocumentListResponse(BaseModel):
    items: list[DocumentItem]


def _download_url(document_id: UUID) -> str:
    return f"{settings.api_v1_prefix}/documents/{document_id}/download"


def _content_disposition(file_name: str) -> str:
    name = file_name or "document"
    fallback = "".join(
        char
        if char.isascii() and char.isprintable() and char not in '"\\'
        else "_"
        for char in name
    )
    return (
        f'attachment; filename="{fallback}"; '
        f"filename*=UTF-8''{quote(name)}"
    )


@router.get(
    "/procedures/{procedure_code}/documents",
    response_model=DocumentListResponse,
)
def list_procedure_documents(
    procedure_code: str,
) -> DocumentListResponse:
    if not repository.procedure_exists(procedure_code):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy thủ tục.",
        )

    documents = repository.list_documents(procedure_code)

    return DocumentListResponse(
        items=[
            DocumentItem(
                id=document.id,
                document_name=document.document_name,
                file_name=document.file_name,
                mime_type=document.mime_type,
                size_bytes=document.size_bytes,
                download_url=_download_url(document.id),
            )
            for document in documents
        ]
    )


@router.get("/documents/{document_id}/download")
def download_document(document_id: UUID) -> StreamingResponse:
    document = repository.get_document(document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy file.",
        )

    storage = S3Storage.from_settings()

    try:
        stream = storage.open_stream(document.object_key)
    except StorageError:
        logger.exception(
            "Không mở được object %s của thủ tục %s",
            document.object_key,
            document.procedure_code,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File không còn trong kho lưu trữ.",
        ) from None

    headers = {
        "Content-Disposition": _content_disposition(document.file_name),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "public, max-age=3600",
        "ETag": f'"{document.checksum_sha256}"',
    }
    if document.size_bytes is not None:
        headers["Content-Length"] = str(document.size_bytes)

    return StreamingResponse(
        stream,
        media_type=document.mime_type or "application/octet-stream",
        headers=headers,
    )