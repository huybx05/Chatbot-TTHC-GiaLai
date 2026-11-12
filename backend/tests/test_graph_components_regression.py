"""Hợp đồng hồi quy cho câu hỏi thành phần TTHC liên thông.

Fixture là dữ liệu kiểm thử, không phải logic nghiệp vụ. Code xử lý phải
tổng quát theo facet/capability/shape; các mã cụ thể ở đây chỉ dùng để khóa
hành vi hồi quy của bộ dữ liệu hiện tại.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "graph_components_regression.json"


def _cases() -> list[dict[str, object]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_has_component_cases() -> None:
    items = _cases()

    assert len(items) >= 5
    assert any(item.get("expected_facet") == "components" for item in items)
    assert any(item.get("expected_facet") == "parent_interlinked" for item in items)


def test_fixture_declares_expected_contract() -> None:
    for item in _cases():
        assert isinstance(item.get("question"), str)
        assert str(item["question"]).strip()
        assert item.get("expected_facet") in {"components", "parent_interlinked"}
        assert item.get("expected_intent") in {
            "COMPONENTS_OF_PROCEDURE",
            "PROCEDURES_BY_COMPONENT",
        }
        assert isinstance(item.get("require_citation"), bool)


def test_fixture_questions_are_unique() -> None:
    questions = [str(item["question"]).strip() for item in _cases()]

    assert len(questions) == len(set(questions))


@pytest.mark.parametrize(
    ("field", "expected_type"),
    [
        ("expected_codes", list),
        ("expected_child_codes", list),
    ],
)
def test_optional_expected_code_lists_have_correct_type(
    field: str, expected_type: type
) -> None:
    for item in _cases():
        if field in item:
            assert isinstance(item[field], expected_type)


def test_component_case_has_expected_codes_or_component_name() -> None:
    for item in _cases():
        if item.get("expected_facet") != "components":
            continue

        assert "expected_codes" in item or "expected_child_codes" in item
        if item.get("expected_codes"):
            assert all(isinstance(code, str) and code for code in item["expected_codes"])
