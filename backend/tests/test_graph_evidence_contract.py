from __future__ import annotations

from backend.app.rag.evidence import from_graph
from backend.app.rag.graph_query import GraphEvidence


def test_from_graph_keeps_procedure_source() -> None:
    graph = GraphEvidence(
        intent="AGENCY",
        title="Cơ quan liên quan",
        procedure_code="1.004873",
        detail_url="https://dichvucong.gov.vn/thu-tuc-hanh-chinh/019d2bfd-6eb3-7019-bf3f-fc58c9ee44b9",
        rows=[{"vai_tro": "Cơ quan ban hành", "gia_tri": "Bộ Tư pháp"}],
    )

    items = from_graph(graph)

    assert items
    assert items[0]["procedure_code"] == "1.004873"
    assert items[0]["detail_url"].startswith("https://dichvucong.gov.vn/")


def test_from_graph_falls_back_to_evidence_url() -> None:
    graph = GraphEvidence(
        intent="LEGAL_BASIS_OF_PROCEDURE",
        title="Văn bản là căn cứ pháp lý",
        procedure_code="1.004873",
        document_code="01/2022/TT BTP",
        detail_url="https://dichvucong.gov.vn/thu-tuc-hanh-chinh/019d2bfd-6eb3-7019-bf3f-fc58c9ee44b9",
        rows=[{"ten": "Thông tư 01/2022/TT-BTP"}],
    )

    items = from_graph(graph)

    assert items[0]["procedure_code"] == "1.004873"
    assert items[0]["document_code"] == "01/2022/TT BTP"
    assert items[0]["detail_url"]
