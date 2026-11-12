from __future__ import annotations

from backend.app.rag.evidence import from_graph
from backend.app.rag.graph_query import GraphEvidence


def test_from_graph_thanh_phan_giu_ma_con_va_metadata() -> None:
    graph = GraphEvidence(
        intent="COMPONENTS_OF_PROCEDURE",
        title="Các thủ tục thành phần",
        procedure_code="2.002621",
        detail_url="https://dichvucong.gov.vn/thu-tuc-hanh-chinh-lien-thong/341088",
        rows=[
            {
                "ma_thanh_phan": "1.014137",
                "ten_thanh_phan": "Thủ tục cấp thẻ bảo hiểm y tế",
                "ten_goi": "Cấp thẻ bảo hiểm y tế",
                "source_code": "1.002535",
                "source_url": "https://dichvucong.gov.vn/thu-tuc-hanh-chinh-lien-thong/341088",
                "detail_url": "https://dichvucong.gov.vn/thu-tuc-hanh-chinh/019d2bff-3d08-7599-80c7-c185678b6753",
            }
        ],
    )

    items = from_graph(graph)

    assert items[0]["procedure_code"] == "1.014137"
    assert items[0]["procedure_name"] == "Thủ tục cấp thẻ bảo hiểm y tế"
    assert items[0]["component_name"] == "Cấp thẻ bảo hiểm y tế"
    assert items[0]["source_code"] == "1.002535"
    assert items[0]["source_url"].startswith("https://dichvucong.gov.vn/")


def test_from_graph_parent_interlinked_giu_ma_cha() -> None:
    graph = GraphEvidence(
        intent="PROCEDURES_BY_COMPONENT",
        title="Thủ tục cha",
        procedure_code="1.116788",
        detail_url="https://dichvucong.gov.vn/thu-tuc-hanh-chinh/1",
        rows=[
            {
                "ma_thu_tuc": "2.002622",
                "ten": "Đăng ký khai tử, xóa đăng ký thường trú",
                "ten_goi": "Xóa đăng ký thường trú",
                "source_code": "1.003197",
                "source_url": "https://dichvucong.gov.vn/thu-tuc-hanh-chinh-lien-thong/341089",
                "detail_url": "https://dichvucong.gov.vn/thu-tuc-hanh-chinh-lien-thong/341089",
            }
        ],
    )

    items = from_graph(graph)

    assert items[0]["procedure_code"] == "2.002622"
    assert items[0]["procedure_name"].startswith("Đăng ký khai tử")
    assert items[0]["component_name"] == "Xóa đăng ký thường trú"
    assert items[0]["source_code"] == "1.003197"


def test_from_graph_procedure_relations_giu_dung_hai_chieu() -> None:
    graph = GraphEvidence(
        intent="PROCEDURE_RELATIONS",
        title="Quan hệ thủ tục",
        procedure_code="1.001193",
        subject="Thủ tục đăng ký khai sinh",
        detail_url="https://dichvucong.gov.vn/thu-tuc-hanh-chinh/1",
        rows=[
            {
                "vai_tro": "Cha",
                "ma": "2.002621",
                "ten": "Đăng ký khai sinh, đăng ký thường trú",
                "ten_goi": "Thủ tục đăng ký khai sinh",
                "source_code": "1.001193",
                "source_url": "https://dichvucong.gov.vn/thu-tuc-hanh-chinh-lien-thong/341088",
                "detail_url": "https://dichvucong.gov.vn/thu-tuc-hanh-chinh-lien-thong/341088",
            }
        ],
    )

    items = from_graph(graph)

    assert items[0]["procedure_code"] == "2.002621"
    assert items[0]["procedure_name"] == "Đăng ký khai sinh, đăng ký thường trú"
    assert items[0]["component_name"] == "Thủ tục đăng ký khai sinh"
    assert items[0]["metadata"]["subject_code"] == "1.001193"
    assert items[0]["metadata"]["subject_name"] == "Thủ tục đăng ký khai sinh"


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
