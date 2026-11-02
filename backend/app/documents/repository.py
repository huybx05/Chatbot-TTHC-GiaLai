from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from backend.app.db.postgres import engine


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    id: UUID
    procedure_code: str
    document_name: str
    file_name: str
    mime_type: str | None
    size_bytes: int | None
    checksum_sha256: str
    object_key: str
    profile_component_id: str | None = None
    file_id: str | None = None
    file_ids: tuple[str, ...] = ()
    case_order: int = 0
    component_index: int = 0
    case_orders: tuple[int, ...] = ()
    component_indexes: tuple[int, ...] = ()


def procedure_exists(procedure_code: str) -> bool:
    with engine.connect() as conn:
        return bool(
            conn.execute(
                text(
                    "SELECT 1 FROM procedures "
                    "WHERE procedure_code = :code"
                ),
                {"code": procedure_code},
            ).scalar()
        )


def list_documents(
    procedure_code: str, case_orders: set[int] | None = None
) -> list[DocumentRecord]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT
                    id,
                    procedure_code,
                    document_name,
                    file_name,
                    mime_type,
                    size_bytes,
                    checksum_sha256,
                    object_key,
                    profile_component_id,
                    file_id,
                    file_ids,
                    case_order,
                    component_index,
                    case_orders,
                    component_indexes
                FROM procedure_documents
                WHERE procedure_code = :code
                  AND is_active = TRUE
                ORDER BY sort_order, file_name
                """
            ),
            {"code": procedure_code},
        ).mappings().all()

    records = [
        DocumentRecord(
            id=row["id"],
            procedure_code=row["procedure_code"],
            document_name=row["document_name"],
            file_name=row["file_name"],
            mime_type=row["mime_type"],
            size_bytes=row["size_bytes"],
            checksum_sha256=row["checksum_sha256"],
            object_key=row["object_key"],
            profile_component_id=row["profile_component_id"],
            file_id=row["file_id"],
            file_ids=tuple(str(value) for value in (row["file_ids"] or ())),
            case_order=int(row["case_order"] or 0),
            component_index=int(row["component_index"] or 0),
            case_orders=tuple(int(value) for value in (row["case_orders"] or ())),
            component_indexes=tuple(
                int(value) for value in (row["component_indexes"] or ())
            ),
        )
        for row in rows
    ]
    if case_orders:
        records = [
            record
            for record in records
            if set(record.case_orders or (record.case_order,)) & case_orders
        ]
    return records


def get_document(document_id: UUID) -> DocumentRecord | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT
                    id,
                    procedure_code,
                    document_name,
                    file_name,
                    mime_type,
                    size_bytes,
                    checksum_sha256,
                    object_key
                FROM procedure_documents
                WHERE id = :id
                  AND is_active = TRUE
                """
            ),
            {"id": document_id},
        ).mappings().first()

    if row is None:
        return None

    return DocumentRecord(
        id=row["id"],
        procedure_code=row["procedure_code"],
        document_name=row["document_name"],
        file_name=row["file_name"],
        mime_type=row["mime_type"],
        size_bytes=row["size_bytes"],
        checksum_sha256=row["checksum_sha256"],
        object_key=row["object_key"],
    )