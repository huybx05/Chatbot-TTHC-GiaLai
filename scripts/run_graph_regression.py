"""Run the 10-case Graph regression fixture against the real pipeline.

Usage:
    uv run python scripts/run_graph_regression.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.app.rag import retrieval  # noqa: E402

FIXTURE = REPO / "backend/tests/fixtures/graph_regression.json"


def _first_source(result: dict) -> str:
    sources = {
        str(item.get("source") or "")
        for item in result.get("evidence") or []
        if item.get("source")
    }
    if not sources:
        return ""
    return sorted(sources)[0]


def _first_intent(result: dict) -> str:
    for item in result.get("evidence") or []:
        section_type = str(item.get("section_type") or "")
        if section_type:
            return section_type
    return ""


def _citation_url(item: dict) -> str:
    return str(item.get("url") or item.get("detail_url") or "").strip()


def _citations_valid(result: dict) -> bool:
    citations = result.get("citations") or []
    return bool(citations) and all(_citation_url(item) for item in citations)


async def _run() -> int:
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
    failures = 0
    for case in cases:
        result = await retrieval.retrieve(
            str(case["question"]),
            generate=False,
            log_trace=False,
            source="graph_regression",
        )
        source = _first_source(result)
        intent = _first_intent(result)
        citations_ok = _citations_valid(result)
        status = str(result.get("outcome") or "")

        errors: list[str] = []
        if status != "answered":
            errors.append(f"outcome={status}")
        if source != case["expected_source"]:
            errors.append(f"source={source or 'none'}")
        if intent != case["expected_intent"]:
            errors.append(f"intent={intent or 'none'}")
        if case["require_citation"] and not citations_ok:
            errors.append("citation=missing_or_empty_url")

        mark = "OK" if not errors else "FAIL"
        print(
            f"[{mark}] {case['question']} "
            f"(source={source or '-'}, intent={intent or '-'}, "
            f"citations={len(result.get('citations') or [])})"
        )
        if errors:
            failures += 1
            print("       " + "; ".join(errors))

    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
