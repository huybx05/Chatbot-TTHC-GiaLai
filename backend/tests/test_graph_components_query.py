"""Hợp đồng query template cho quan hệ thành phần.

Test thuần, không cần Neo4j: chỉ kiểm tra Cypher sinh ra và tham số bind.
"""

from __future__ import annotations

from backend.app.rag.graph_query import INTENTS, build_plan
from backend.app.rag.graph_shapes import SHAPES, build_shape


def _spec(intent: str):
    return next(spec for spec in INTENTS if spec.intent == intent)


def test_components_shape_di_xuoi_tu_ma_cha() -> None:
    cypher = build_shape(SHAPES["COMPONENTS_OF_PROCEDURE"])

    assert "MATCH (p:ThuTuc {run_id: $run_id, key: $code})" in cypher
    assert "-[e1:THANH_PHAN_CUA]->" in cypher
    assert "e1.component_name" in cypher
    assert "x.detail_url" in cypher


def test_procedures_by_component_di_nguoc_tu_ma_con() -> None:
    cypher = build_shape(SHAPES["PROCEDURES_BY_COMPONENT"])

    assert "MATCH (p:ThuTuc {run_id: $run_id})" in cypher
    assert "-[e1:THANH_PHAN_CUA]->" in cypher
    assert "x.key = $component_code" in cypher
    assert "p.detail_url" in cypher


def test_build_plan_bind_code_cho_components() -> None:
    plan = build_plan(
        _spec("COMPONENTS_OF_PROCEDURE"),
        code="2.002621",
        doc_key=None,
        limit=20,
    )

    assert plan is not None
    assert plan.params["code"] == "2.002621"
    assert "component_code" not in plan.params


def test_build_plan_bind_component_code_cho_parent() -> None:
    plan = build_plan(
        _spec("PROCEDURES_BY_COMPONENT"),
        code="1.116788",
        doc_key=None,
        limit=20,
        component_code="1.116788",
    )

    assert plan is not None
    assert plan.params["component_code"] == "1.116788"
    assert "code" not in plan.params


def test_build_plan_tu_choi_parent_thieu_component_code() -> None:
    plan = build_plan(
        _spec("PROCEDURES_BY_COMPONENT"),
        code="1.116788",
        doc_key=None,
        limit=20,
    )

    assert plan is None
