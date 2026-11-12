"""Facet hợp đồng cho quan hệ thủ tục liên thông.

Các test này chỉ kiểm tra schema/facet, không gọi LLM và không phụ thuộc Neo4j.
"""

from __future__ import annotations

from backend.app.workflow.question_frame import Facet


def test_component_facets_exist() -> None:
    assert Facet.COMPONENTS.value == "components"
    assert Facet.PARENT_INTERLINKED.value == "parent_interlinked"


def test_related_procedures_van_tach_biet() -> None:
    assert Facet.RELATED_PROCEDURES.value == "related_procedures"
    assert Facet.RELATED_PROCEDURES is not Facet.COMPONENTS
    assert Facet.RELATED_PROCEDURES is not Facet.PARENT_INTERLINKED
