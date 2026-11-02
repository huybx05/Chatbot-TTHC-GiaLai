"""Ba tầng procedure trong workflow.

``candidate`` là giả thuyết, ``grounded`` đã được grounding xác nhận, còn
``answered`` là procedure thực sự dùng để trả lời (có evidence). Chỉ tầng
``answered`` mới được phép đi vào memory.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any


def _value(item: Any, key: str, default: Any = "") -> Any:
    if isinstance(item, Mapping):
        return item.get(key, default)
    return getattr(item, key, default)


def _candidate(
    *,
    code: Any,
    name: Any,
    score: Any,
    source: str,
    ambiguous: bool = False,
) -> dict[str, Any]:
    value = str(code or "").strip()
    if not value:
        return {}
    return {
        "code": value,
        "name": str(name or value).strip(),
        "score": float(score or 0.0),
        "source": source,
        "ambiguous": bool(ambiguous),
    }


def candidates_from_resolution(
    resolution: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(resolution, Mapping):
        return []
    result: list[dict[str, Any]] = []
    primary = _candidate(
        code=resolution.get("code"),
        name=resolution.get("name"),
        score=resolution.get("confidence"),
        source=str(resolution.get("method") or "resolution"),
        ambiguous=bool(resolution.get("ambiguous")),
    )
    if primary:
        result.append(primary)
    for item in resolution.get("alternatives") or []:
        alternative = _candidate(
            code=_value(item, "code"),
            name=_value(item, "name"),
            score=_value(item, "score"),
            source="resolution_alternative",
            ambiguous=True,
        )
        if alternative:
            result.append(alternative)
    return result


def candidates_from_groundings(
    groundings: Sequence[Any],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in groundings:
        if str(_value(item, "type")) != "procedure":
            continue
        if str(_value(item, "status")) == "resolved":
            candidate = _candidate(
                code=_value(item, "code"),
                name=_value(item, "name") or _value(item, "mention"),
                score=_value(item, "score"),
                source=str(_value(item, "method") or "grounding"),
            )
            if candidate:
                result.append(candidate)

        for alternative in (
            list(_value(item, "alternatives", []) or [])
            + list(_value(item, "candidates", []) or [])
        ):
            candidate = _candidate(
                code=_value(alternative, "code"),
                name=_value(alternative, "name"),
                score=_value(alternative, "score"),
                source="grounding_alternative",
                ambiguous=True,
            )
            if candidate:
                result.append(candidate)
    return _dedupe(result)


def _dedupe(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    by_code: dict[str, dict[str, Any]] = {}
    for item in items:
        code = str(item.get("code") or "")
        if not code:
            continue
        current = by_code.get(code)
        if current is None or float(item.get("score") or 0.0) >= float(
            current.get("score") or 0.0
        ):
            by_code[code] = item
    return list(by_code.values())


def merge_candidates(
    *groups: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for group in groups:
        merged.extend(group)
    return _dedupe(merged)


def grounded_procedure(
    resolution: Mapping[str, Any] | None,
    groundings: Sequence[Any],
) -> dict[str, Any]:
    for item in groundings:
        if str(_value(item, "type")) != "procedure":
            continue
        if str(_value(item, "status")) != "resolved":
            continue
        code = str(_value(item, "code") or "").strip()
        if not code:
            continue
        return {
            "code": code,
            "name": str(_value(item, "name") or code),
            "method": str(_value(item, "method") or ""),
            "score": float(_value(item, "score") or 0.0),
            "source": "grounding",
        }

    if not isinstance(resolution, Mapping):
        return {}
    code = str(resolution.get("code") or "").strip()
    method = str(resolution.get("method") or "")
    if code and (
        method in {"code", "exact_name"} or method.startswith("grounding:")
    ):
        return {
            "code": code,
            "name": str(resolution.get("name") or code),
            "method": method,
            "score": float(resolution.get("confidence") or 0.0),
            "source": method or "resolution",
        }
    return {}


def answered_procedure(
    resolution: Mapping[str, Any] | None,
    grounded: Mapping[str, Any] | None,
    evidence: Sequence[Any],
    outcome: str,
) -> dict[str, Any]:
    if str(outcome) != "answered" or not evidence:
        return {}

    if isinstance(grounded, Mapping) and str(grounded.get("code") or "").strip():
        code = str(grounded["code"]).strip()
        return {
            "code": code,
            "name": str(grounded.get("name") or code),
            "source": "grounded",
            "evidence_count": len(evidence),
        }

    if isinstance(resolution, Mapping) and str(resolution.get("code") or "").strip():
        code = str(resolution["code"]).strip()
        return {
            "code": code,
            "name": str(resolution.get("name") or code),
            "source": "resolution",
            "evidence_count": len(evidence),
        }
    return {}
