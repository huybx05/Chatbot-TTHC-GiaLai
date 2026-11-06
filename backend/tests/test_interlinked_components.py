"""Kiểm tra mapping TTHC liên thông → mã thủ tục thành phần."""

from data_pipeline.indexing.neo4j import load_interlinked_components


def test_interlinked_components_dung_ma_that():
    mapping = load_interlinked_components()

    assert [item["code"] for item in mapping["2.002621"]] == [
        "1.001193",
        "1.014137",
        "1.116788",
    ]
    assert [item["code"] for item in mapping["2.002622"]] == [
        "1.000656",
        "1.116788",
    ]
    assert [item["code"] for item in mapping["1.014475"]] == [
        "1.001029",
        "1.001612",
        "3.000243",
    ]
    assert [item["code"] for item in mapping["2.002804"]] == ["1.000801"]
    assert mapping["3.000153"] == []


def test_khong_tao_node_thanh_phan_tu_ten():
    mapping = load_interlinked_components()
    all_codes = {item["code"] for items in mapping.values() for item in items}

    assert all(code[0].isdigit() for code in all_codes)
    assert "1.003197" not in all_codes


def test_thanh_phan_cua_duoc_phep_truy_van():
    from backend.app.rag.graph_query import ALLOWED_RELATIONSHIPS, RELATION_LABELS

    assert RELATION_LABELS["THANH_PHAN_CUA"] == "Thành phần của"
    assert "THANH_PHAN_CUA" in ALLOWED_RELATIONSHIPS
