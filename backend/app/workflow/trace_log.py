"""Append-only diagnostic trace for one workflow turn (version 3).

Mỗi dòng là một JSON object đủ để trả lời: **câu hỏi đã đi qua bước nào, dừng ở đâu,
vì sao**. Log cố ý gọn: chỉ giữ tín hiệu dùng để chẩn đoán, không đổ toàn bộ state.

Ghi log **không bao giờ** được làm hỏng lượt trả lời: mọi lỗi ghi file đều bị nuốt.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

_LOCK = threading.Lock()
_ROOT = Path(__file__).resolve().parents[3]
_MAX_ANSWER_CHARS = 3000
_MAX_CONTENT_CHARS = 300
_MAX_ERROR_CHARS = 1200
_MAX_LIST_ITEMS = 6
TRACE_VERSION = 3


def _path() -> Path:
    value = os.getenv("WORKFLOW_TRACE_JSONL_PATH", "").strip()
    return Path(value) if value else _ROOT / "logs" / "workflow_trace.jsonl"


def _short(value: object, limit: int = _MAX_CONTENT_CHARS) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _rows(
    value: object,
    *,
    limit: int = _MAX_LIST_ITEMS,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value[:limit] if isinstance(item, dict)]


def _frame(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    mentions = [
        {
            "type": _short(item.get("type")),
            "text": _short(item.get("text")),
        }
        for item in _rows(value.get("subject_mentions"))
    ]
    requests = [
        {
            "text": _short(item.get("text")),
            "facet": _short(item.get("facet")),
            "operation": _short(item.get("operation")),
            "subject_ref": item.get("subject_ref"),
            "scenario": _short(item.get("scenario")),
        }
        for item in _rows(value.get("requests"))
    ]
    ambiguity = value.get("ambiguity")
    if not isinstance(ambiguity, dict):
        ambiguity = {}
    return {
        "scope": _short(value.get("scope")),
        "subject_mentions": mentions,
        "requests": requests,
        "ambiguity": {
            "present": bool(ambiguity.get("present")),
            "kind": _short(ambiguity.get("kind")),
            "reason": _short(ambiguity.get("reason")),
        },
    }


def _groundings(value: object) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in _rows(value):
        alternatives = [
            {
                "code": _short(alt.get("code")),
                "name": _short(alt.get("name")),
            }
            for alt in _rows(item.get("alternatives"), limit=3)
        ]
        result.append(
            {
                "mention": _short(item.get("mention")),
                "status": _short(item.get("status")),
                "type": _short(item.get("type")),
                "code": _short(item.get("code")),
                "name": _short(item.get("name")),
                "method": _short(item.get("method")),
                "score": item.get("score"),
                "alternatives": alternatives,
                "note": _short(item.get("note")),
            }
        )
    return result


def _resolution(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "code": _short(value.get("code")),
        "name": _short(value.get("name")),
        "method": _short(value.get("method")),
        "confidence": value.get("confidence"),
        "ambiguous": bool(value.get("ambiguous")),
        "note": _short(value.get("note")),
    }


def _identity(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        return {}
    return {
        "code": _short(value.get("code")),
        "name": _short(value.get("name")),
        "method": _short(value.get("method")),
        "score": value.get("score"),
        "source": _short(value.get("source")),
        "evidence_count": int(value.get("evidence_count") or 0),
    }


def _candidates(value: object) -> list[dict[str, Any]]:
    return [
        {
            **_identity(item),
            "ambiguous": bool(item.get("ambiguous")),
        }
        for item in _rows(value, limit=5)
    ]


def _rewrite(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        return {"used": False}
    anchor = value.get("anchor")
    if not isinstance(anchor, dict):
        anchor = None
    return {
        "used": bool(value.get("used")),
        "is_followup": bool(value.get("is_followup")),
        "confidence": value.get("confidence"),
        "reason": _short(value.get("reason")),
        "attempts": int(value.get("attempts") or 0),
        "latency_ms": int(value.get("latency_ms") or 0),
        "error_type": _short(value.get("error_type")),
        "anchor": (
            {"code": _short(anchor.get("code")), "name": _short(anchor.get("name"))}
            if anchor
            else None
        ),
    }


def _memory(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or not value:
        return {}

    topics = [
        {
            "order": topic.get("order"),
            "code": _short(topic.get("procedure_code") or topic.get("code")),
            "name": _short(topic.get("procedure_name") or topic.get("name")),
        }
        for topic in _rows(value.get("topics"), limit=10)
    ]
    active = value.get("active_procedure")
    if not isinstance(active, dict):
        active = None
    return {
        "has_summary": bool(value.get("summary")),
        "summary_chars": len(str(value.get("summary") or "")),
        "recent_turns": len(value.get("recent_turns") or []),
        "topics": topics,
        "active_procedure": (
            {"code": _short(active.get("code")), "name": _short(active.get("name"))}
            if active
            else None
        ),
        "recalled_turns": len(value.get("recalled_turns") or []),
        "last_outcome": _short(value.get("last_outcome")),
    }


def _plan(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    tasks = [
        {
            "request_index": task.get("request_index"),
            "facet": _short(task.get("facet")),
            "operation": _short(task.get("operation")),
            "subject_ref": task.get("subject_ref"),
            "subject_code": _short(task.get("subject_code")),
            "procedure_codes": [
                _short(code)
                for code in (task.get("procedure_codes") or [])
            ],
            "status": _short(task.get("status")),
        }
        for task in _rows(value.get("tasks"))
    ]
    return {"task_count": len(value.get("tasks") or []), "tasks": tasks}


def _coverage(value: object) -> list[dict[str, Any]]:
    return [
        {
            "request_index": item.get("request_index"),
            "status": _short(item.get("status")),
            "facet": _short(item.get("facet")),
            "reason": _short(item.get("reason")),
        }
        for item in _rows(value)
    ]


def _thieu(value: object) -> list[Any]:
    if not isinstance(value, list):
        return []
    result: list[Any] = []
    for item in value[:_MAX_LIST_ITEMS]:
        if isinstance(item, dict):
            result.append(
                {
                    "request_index": item.get("request_index"),
                    "facet": _short(item.get("facet")),
                    "reason": _short(item.get("reason")),
                }
            )
        elif str(item).strip():
            result.append(_short(item))
    return result


def _evidence(value: object) -> list[dict[str, Any]]:
    keep = (
        "kind",
        "procedure_code",
        "procedure_name",
        "title",
        "section_type",
        "request_index",
        "facet",
        "score",
        "source",
        "detail_url",
        "document_code",
        "verified",
        "verification",
        "result_kind",
        "metadata",
    )
    rows = [
        {
            **{key: row[key] for key in keep if key in row},
            "content": _short(row.get("content")),
        }
        for row in _rows(value)
    ]
    return rows


def _citations(value: object) -> list[dict[str, Any]]:
    keep = ("procedure_code", "procedure_name", "title", "document_code", "detail_url")
    return [
        {key: _short(row.get(key)) for key in keep if row.get(key) is not None}
        for row in _rows(value)
    ]


def _clarify(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "question": _short(value.get("question")),
        "options": [
            {
                "value": _short(option.get("value")),
                "label": _short(option.get("label")),
            }
            for option in _rows(value.get("options"), limit=5)
        ],
    }


def _verification(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "status": _short(value.get("status")),
        "issues": [_short(item) for item in (value.get("issues") or [])[:5]],
    }


def _record(question: str, state: dict[str, Any]) -> dict[str, Any]:
    trace = state.get("trace")
    if not isinstance(trace, dict):
        trace = {}
    original = str(
        state.get("original_question")
        or trace.get("original_question")
        or question
        or ""
    )
    retrieval = str(
        state.get("retrieval_question")
        or trace.get("retrieval_question")
        or question
        or ""
    )
    rewrite = state.get("rewrite")
    if not isinstance(rewrite, dict) or not rewrite:
        rewrite = trace.get("rewrite")
    memory = state.get("memory")
    if not isinstance(memory, dict) or not memory:
        memory = trace.get("memory")
    timings = state.get("timings")
    if not isinstance(timings, dict):
        timings = {}
    tokens = state.get("tokens")
    if not isinstance(tokens, dict):
        tokens = {}
    total_ms = int(state.get("total_ms") or state.get("ms") or 0)
    timing_total = int(timings.get("total_ms") or total_ms)

    return {
        "trace_version": TRACE_VERSION,
        "trace_id": str(uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "question": _short(original),
        "retrieval_question": _short(retrieval),
        "rewrite": _rewrite(rewrite),
        "memory": _memory(memory),
        # ── kết cục ──────────────────────────────────────────────────────
        "outcome": _short(state.get("outcome")),
        "branch": _short(state.get("branch")),
        "branch_signal": _short(state.get("branch_signal")),
        "branch_reason": _short(state.get("branch_reason")),
        "ran": bool(state.get("ran", True)),
        "error": _short(state.get("error"), _MAX_ERROR_CHARS),
        "answer_error": _short(state.get("answer_error"), _MAX_ERROR_CHARS),
        "refusal": _short(state.get("refusal")),
        "clarify": _clarify(state.get("clarify")),
        "thieu": _thieu(state.get("thieu")),
        # ── hiểu câu hỏi ─────────────────────────────────────────────────
        "router_source": _short(state.get("router_source")),
        "router_fallback_reason": _short(state.get("router_fallback_reason")),
        "question_frame": _frame(state.get("question_frame")),
        "plan_class": _short(state.get("plan_class")),
        "plan_class_reason": _short(state.get("plan_class_reason")),
        "resolution": _resolution(state.get("resolution")),
        "candidate_procedures": _candidates(state.get("candidate_procedures")),
        "grounded_procedure": _identity(state.get("grounded_procedure")),
        "answered_procedure": _identity(state.get("answered_procedure")),
        "groundings": _groundings(state.get("groundings")),
        # ── truy xuất ────────────────────────────────────────────────────
        "plan": _plan(state.get("plan")),
        "coverage": _coverage(state.get("coverage")),
        "evidence_count": len(state.get("evidence") or []),
        "evidence": _evidence(state.get("evidence")),
        "citation_count": len(state.get("citations") or []),
        "citations": _citations(state.get("citations")),
        # ── kiểm chứng ───────────────────────────────────────────────────
        "verification": _verification(state.get("verification")),
        # ── câu trả lời ──────────────────────────────────────────────────
        "answer": _short(state.get("answer"), _MAX_ANSWER_CHARS),
        # ── chi phí ──────────────────────────────────────────────────────
        "embedding_used": bool(state.get("embedding_used")),
        "tokens": {
            "input": int(tokens.get("input") or 0),
            "output": int(tokens.get("output") or 0),
        },
        "timings": {
            "resolve_ms": int(timings.get("resolve_ms") or 0),
            "router_ms": int(timings.get("router_ms") or 0),
            "grounding_ms": int(timings.get("grounding_ms") or 0),
            "generate_ms": int(timings.get("generate_ms") or 0),
            "total_ms": timing_total,
        },
        "ms": int(state.get("ms") or 0),
        "total_ms": total_ms,
    }


def append_from_state(
    question: str,
    state: dict[str, Any],
    *,
    ms: int = 0,
    ran: bool = True,
    source: str = "",
    phase: str = "final",
    error_detail: str = "",
) -> None:
    """Ghi một lượt từ state (dùng được cả sau khi stream xong)."""
    record = _record(question, {**state, "ran": ran})
    record["source"] = source
    record["phase"] = phase
    total_ms = int(ms or record.get("ms") or record.get("total_ms") or 0)
    record["ms"] = total_ms
    record["total_ms"] = total_ms
    record["timings"]["total_ms"] = total_ms
    if error_detail:
        record["error_detail"] = _short(error_detail, _MAX_ERROR_CHARS)
    try:
        path = _path()
        with _LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError:
        return


def append(
    result: Any,
    *,
    source: str = "api",
    phase: str = "final",
    error_detail: str = "",
) -> None:
    """Ghi từ ``RunResult`` (đường thường)."""
    state = dict(result.state)
    state["ms"] = result.ms
    state["total_ms"] = result.ms
    append_from_state(
        result.question,
        state,
        ms=result.ms,
        ran=result.ran,
        source=source,
        phase=phase,
        error_detail=error_detail,
    )


__all__ = ["TRACE_VERSION", "append", "append_from_state"]
