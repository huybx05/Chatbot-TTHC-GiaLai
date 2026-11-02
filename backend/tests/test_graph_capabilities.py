from __future__ import annotations

from backend.app.rag.graph_capabilities import (
    ENTITY_TO_FACET,
    FORWARD_CAPABILITY,
    REVERSE_CAPABILITY,
)


def test_forward_capabilities_cover_expected_facets() -> None:
    expected = {
        "issuing_agency",
        "implementing_agency",
        "legal_basis",
        "result",
        "target_audience",
    }
    assert expected <= set(FORWARD_CAPABILITY)
    assert FORWARD_CAPABILITY["result"].intent == "RESULT"


def test_reverse_capabilities_cover_list_entities() -> None:
    expected = {
        "issuing_agency",
        "administrative_level",
        "field",
        "domain_group",
    }
    assert expected <= set(REVERSE_CAPABILITY)
    assert set(ENTITY_TO_FACET) >= {
        "agency",
        "administrative_level",
        "field",
        "domain_group",
    }
