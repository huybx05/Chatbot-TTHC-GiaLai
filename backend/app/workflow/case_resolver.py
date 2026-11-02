"""Resolve a natural-language case from execution-case metadata.

Người dùng không bao giờ phải gõ ``(1.2)`` hay mã case. Module này so khớp câu hỏi với
``case_name``/``block_heading`` và chỉ chọn khi có tín hiệu phân biệt giữa các case.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from backend.app.text_norm import strip_accents

_STOP = frozenset(
    {
        "cua", "va", "cho", "trong", "doi", "voi", "truong", "hop", "cong", "trinh",
        "thu", "tuc", "ho", "so", "can", "gi", "nhu", "the", "nao", "toi", "ban",
        "la", "co", "khong", "duoc", "khi", "tai", "o", "cac", "mot", "nhung",
        "nay", "do", "ra", "vao", "tu", "den", "ve", "theo", "de", "bi", "cai",
        "nha", "xin", "muon", "hoi", "nop", "giay", "to", "loai", "nhom",
    }
)


def _tokens(text: str) -> set[str]:
    raw = strip_accents(str(text or "")).lower()
    return {
        word
        for word in raw.replace("/", " ").replace(",", " ").replace(":", " ").split()
        if len(word) >= 3 and word not in _STOP
    }


def _cases(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[int] = set()
    cases: list[dict[str, Any]] = []
    for item in items:
        meta = item.get("metadata") or {}
        order = int(meta.get("case_order") or 0)
        if order <= 0 or order in seen:
            continue
        seen.add(order)
        cases.append(
            {
                "case_order": order,
                "case_name": str(meta.get("case_name") or ""),
                "tokens": _tokens(str(meta.get("case_name") or ""))
                | _tokens(str(meta.get("block_heading") or "")),
            }
        )
    return cases


def select_case(question: str, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Trả case khớp, hoặc ``None`` nếu câu hỏi là hỏi chung/không đủ tín hiệu."""
    cases = _cases(items)
    if len(cases) < 2:
        return None

    counts = Counter(token for case in cases for token in case["tokens"])
    question_tokens = _tokens(question)
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for case in cases:
        distinctive = {
            token
            for token in case["tokens"]
            if counts[token] == 1 and token in question_tokens
        }
        scored.append((len(distinctive), case["case_order"], case))

    scored.sort(key=lambda row: (row[0], -row[1]), reverse=True)
    best_score, _, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0

    # Một token đặc trưng đủ dài, hoặc hai token đặc trưng, mới đủ chắc.
    if best_score == 0:
        return None
    if best_score == 1 and second_score == 1:
        return None
    if best_score == 1:
        strong = [
            token
            for token in best["tokens"]
            if counts[token] == 1 and token in question_tokens and len(token) >= 3
        ]
        if not strong:
            return None
    return {
        "case_order": best["case_order"],
        "case_name": best["case_name"],
        "confidence": round(best_score / max(1, len(best["tokens"])), 3),
    }


def filter_items(
    items: list[dict[str, Any]], case: dict[str, Any] | None
) -> list[dict[str, Any]]:
    if case is None:
        return items
    order = int(case["case_order"])
    return [
        item
        for item in items
        if int((item.get("metadata") or {}).get("case_order") or 0) == order
    ]
