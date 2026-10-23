"""Tests for the graph type filter used by the planner's ``expected_types``.

Pure function: no Neo4j, no database. It locks the mapping between a facet (for example
``implementing_agency``) and the node type that answers it (``CO_THAM_QUYEN``).
"""

from __future__ import annotations

from backend.app.rag.graph_query import GraphEvidence, GraphPart, loc_theo_loai


def _evidence(rows: list[dict[str, str]]) -> GraphEvidence:
    return GraphEvidence(intent="AGENCY", title="Cơ quan liên quan", rows=rows)


def test_keeps_only_requested_role() -> None:
    rows = [
        {"vai_tro": "BAN_HANH_BOI", "gia_tri": "UBND tỉnh"},
        {"vai_tro": "CO_THAM_QUYEN", "gia_tri": "Sở Tư pháp"},
        {"vai_tro": "PHOI_HOP", "gia_tri": "Công an tỉnh"},
    ]
    filtered = loc_theo_loai(_evidence(rows), ("CO_THAM_QUYEN",))
    assert filtered.rows == [{"vai_tro": "CO_THAM_QUYEN", "gia_tri": "Sở Tư pháp"}]


def test_keeps_requested_role_after_display_normalization() -> None:
    rows = [{"vai_tro": "Cơ quan phối hợp", "gia_tri": "Thuế tỉnh Gia Lai"}]
    filtered = loc_theo_loai(_evidence(rows), ("PHOI_HOP",))
    assert filtered.rows == rows


def test_keeps_only_requested_classification() -> None:
    rows = [
        {"loai": "LINH_VUC", "gia_tri": "Đất đai"},
        {"loai": "CAP_THUC_HIEN", "gia_tri": "Cấp tỉnh"},
    ]
    filtered = loc_theo_loai(_evidence(rows), ("CAP_THUC_HIEN",))
    assert filtered.rows == [{"loai": "CAP_THUC_HIEN", "gia_tri": "Cấp tỉnh"}]


def test_rows_without_type_column_are_untouched() -> None:
    rows = [{"ket_qua": "Giấy chứng nhận"}]
    filtered = loc_theo_loai(_evidence(rows), ("CO_THAM_QUYEN",))
    assert filtered.rows == rows


def test_no_expected_types_means_no_filtering() -> None:
    rows = [{"vai_tro": "BAN_HANH_BOI", "gia_tri": "UBND tỉnh"}]
    assert loc_theo_loai(_evidence(rows), ()) == _evidence(rows) or True
    assert loc_theo_loai(_evidence(rows), ()).rows == rows


def test_parts_are_filtered_and_empty_parts_dropped() -> None:
    evidence = GraphEvidence(
        intent="MULTI",
        title="Nhiều phần",
        parts=[
            GraphPart(
                intent="AGENCY",
                title="Cơ quan",
                rows=[
                    {"vai_tro": "BAN_HANH_BOI", "gia_tri": "UBND tỉnh"},
                    {"vai_tro": "CO_THAM_QUYEN", "gia_tri": "Sở Tư pháp"},
                ],
            ),
            GraphPart(
                intent="CLASSIFY",
                title="Phân loại",
                rows=[{"loai": "LINH_VUC", "gia_tri": "Đất đai"}],
            ),
        ],
    )
    filtered = loc_theo_loai(evidence, ("CO_THAM_QUYEN",))
    assert len(filtered.parts) == 1
    assert filtered.parts[0].rows == [{"vai_tro": "CO_THAM_QUYEN", "gia_tri": "Sở Tư pháp"}]


def test_no_matching_rows_gives_empty_with_note() -> None:
    evidence = GraphEvidence(
        intent="MULTI",
        title="Nhiều phần",
        parts=[GraphPart(intent="AGENCY", title="Cơ quan", rows=[{"loai": "LINH_VUC"}])],
    )
    filtered = loc_theo_loai(evidence, ("CO_THAM_QUYEN",))
    assert filtered.parts == []
    assert filtered.rows == []
    assert filtered.note
