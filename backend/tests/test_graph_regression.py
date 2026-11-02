from __future__ import annotations

import json
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "graph_regression.json"


def cases() -> list[dict[str, object]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_has_ten_cases() -> None:
    items = cases()
    assert len(items) == 10
    assert all(str(item["question"]).strip() for item in items)


def test_every_case_declares_expected_source_and_citation() -> None:
    for item in cases():
        assert item["expected_intent"]
        assert item["expected_source"] in {"graph", "hybrid", "fact_lookup"}
        assert isinstance(item["require_citation"], bool)
