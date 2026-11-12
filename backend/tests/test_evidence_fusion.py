"""Hợp nhất bằng chứng trùng giữa các nhánh."""

from __future__ import annotations

from backend.app.rag.evidence import deduplicate_evidence


def _item(source: str, content: str, **extra):
    return {
        "kind": "graph" if source == "graph" else "section",
        "procedure_code": "2.002621",
        "section_type": "COMPONENTS_OF_PROCEDURE",
        "content": content,
        "source": source,
        "by_keyword": False,
        "by_vector": False,
        "keyword_rank": None,
        "vector_rank": None,
        "component_name": "Thành phần",
        "source_url": "https://dichvucong.gov.vn/x",
        "part_index": 0,
        **extra,
    }


def test_dedup_giu_nguon_graph_khi_trung_noi_dung() -> None:
    merged = deduplicate_evidence(
        [
            _item("hybrid", "Mã: 1.014137"),
            _item("graph", "Mã: 1.014137"),
        ]
    )

    assert len(merged) == 1
    assert merged[0]["source"] == "graph"


def test_dedup_hop_nhat_co_keyword_vector() -> None:
    merged = deduplicate_evidence(
        [
            _item("hybrid", "Mã: 1.014137", by_keyword=True, keyword_rank=1),
            _item("hybrid", "Mã: 1.014137", by_vector=True, vector_rank=2),
        ]
    )

    assert len(merged) == 1
    assert merged[0]["by_keyword"] is True
    assert merged[0]["by_vector"] is True
    assert merged[0]["keyword_rank"] == 1
    assert merged[0]["vector_rank"] == 2


def test_dedup_khong_gop_hai_thu_tuc_khac_nhau() -> None:
    merged = deduplicate_evidence(
        [
            _item("graph", "Mã: 1.014137"),
            _item("graph", "Mã: 1.116788", procedure_code="1.116788"),
        ]
    )

    assert len(merged) == 2


def test_dedup_khong_gop_hai_khia_canh_khac_nhau() -> None:
    merged = deduplicate_evidence(
        [
            _item("graph", "Mã: 1.014137", section_type="COMPONENTS_OF_PROCEDURE"),
            _item("graph", "Mã: 1.014137", section_type="PROCEDURES_BY_COMPONENT"),
        ]
    )

    assert len(merged) == 2
