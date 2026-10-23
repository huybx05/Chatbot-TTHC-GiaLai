"""Structured infrastructure errors for the three retrieval tools.

Each test proves that a backend outage becomes an **error**, not an empty result. Empty means
"dữ liệu không ghi nhận"; a connection refusal must never be reported that way.
"""

from __future__ import annotations

import asyncio

import pytest
from backend.app.rag import fact_lookup, graph_query, hybrid, sections

# ── PostgreSQL ────────────────────────────────────────────────────────────


def test_sections_returns_error_when_db_fails(monkeypatch) -> None:
    def hong(codes, rows):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(sections, "_doc", hong)
    rows, error = asyncio.run(sections.theo_khia_canh_checked(["1.001699"], ["fee"]))
    assert rows == []
    assert "connection refused" in error


def test_sections_success_has_no_error(monkeypatch) -> None:
    monkeypatch.setattr(sections, "_doc", lambda codes, rows: [{"section_type": "FEE"}])
    rows, error = asyncio.run(sections.theo_khia_canh_checked(["1.001699"], ["fee"]))
    assert rows and error == ""


def test_fact_lookup_returns_error_when_db_fails(monkeypatch) -> None:
    def hong(codes):
        raise RuntimeError("timeout")

    monkeypatch.setattr(fact_lookup, "_query_facts", hong)
    facts, error = asyncio.run(fact_lookup.get_facts_checked(["1.001699"]))
    assert facts == []
    assert "timeout" in error


# ── Neo4j ─────────────────────────────────────────────────────────────────


def test_graph_marks_failed_when_vocabulary_unavailable(monkeypatch) -> None:
    async def hong():
        raise RuntimeError("Neo4j down")

    monkeypatch.setattr(graph_query, "vocabulary", hong)
    evidence = asyncio.run(
        graph_query.answer("Thủ tục 1.001699 do cơ quan nào ban hành?", codes=["1.001699"])
    )
    assert evidence.failed is True
    assert evidence.note


def test_graph_success_is_not_failed() -> None:
    evidence = graph_query.GraphEvidence(intent="AGENCY", title="Cơ quan")
    assert evidence.failed is False


# ── Elasticsearch / Qdrant ────────────────────────────────────────────────


def test_keyword_search_records_error(monkeypatch) -> None:
    def hong(question, top_k, codes):
        raise RuntimeError("ES down")

    monkeypatch.setattr(hybrid, "_search_es", hong)
    errors: list[str] = []
    rows = asyncio.run(hybrid.keyword_only("phí", errors=errors))
    assert rows == []
    assert errors and "ES down" in errors[0]


def test_vector_search_records_error(monkeypatch) -> None:
    class HongClient:
        async def query_points(self, **_kwargs):
            raise RuntimeError("Qdrant down")

    monkeypatch.setattr(hybrid, "_qdrant_client", lambda: HongClient())
    errors: list[str] = []
    rows = asyncio.run(hybrid.vector_only([0.1], errors=errors))
    assert rows == []
    assert errors and "Qdrant down" in errors[0]


@pytest.mark.parametrize("field", ["errors"])
def test_retrieval_outcome_has_errors_field(field: str) -> None:
    from backend.app.rag.types import RetrievalOutcome

    outcome = RetrievalOutcome(candidates=[])
    assert getattr(outcome, field) == []
