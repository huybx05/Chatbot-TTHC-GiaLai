from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceAttachment:
    """Một file mẫu trong raw API, chưa được tải về."""

    procedure_code: str
    profile_component_id: str
    document_name: str
    file_name: str
    file_id: str
    source_bucket: str
    source_path: str
    source_url: str
    case_index: int
    component_index: int
    attachment_index: int

    @property
    def sort_order(self) -> int:
        return (
            self.case_index * 1_000_000
            + self.component_index * 1_000
            + self.attachment_index
        )