"""Append-only diagnostic trace for one workflow turn (version 2).

Mỗi dòng là một JSON object đủ để trả lời: **câu hỏi đã đi qua bước nào, dừng ở đâu, vì sao**.
Không chứa bí mật; nội dung bằng chứng bị cắt ngắn.

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
_MAX_EVIDENCE_CHARS = 1600
_MAX_ERROR_CHARS = 4000
TRACE_VERSION = 2


def _path() -> Path:
    value = os.getenv("WORKFLOW_TRACE_JSONL_PATH", "").strip()
    return Path(value) if value else _ROOT / "logs" / "workflow_trace.jsonl"


def _short(value: object, limit: int = _MAX_EVIDENCE_CHARS) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _evidence(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keep = (
        "kind", "procedure_code", "procedure_name", "title", "section_type",
        "request_index", "facet", "score", "source", "detail_url", "document_code",
        "verified", "verification", "result_kind",
    )
    return [
        {**{key: row[key] for key in keep if key in row}, "content": _short(row.get("content"))}
        for row in rows
    ]


def _record(question: str, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "trace_version": TRACE_VERSION,
        "trace_id": str(uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "question": question,
        # ── kết cục ──────────────────────────────────────────────────────
        "outcome": str(state.get("outcome") or ""),
        "branch": str(state.get("branch") or ""),
        "branch_signal": str(state.get("branch_signal") or ""),
        "branch_reason": str(state.get("branch_reason") or ""),
        "ran": bool(state.get("ran", True)),
        "error": str(state.get("error") or ""),
        "answer_error": str(state.get("answer_error") or ""),
        "refusal": str(state.get("refusal") or ""),
        "clarify": dict(state.get("clarify") or {}),
        "thieu": list(state.get("thieu") or []),
        # ── hiểu câu hỏi ─────────────────────────────────────────────────
        "router_source": str(state.get("router_source") or ""),
        "router_fallback_reason": str(state.get("router_fallback_reason") or ""),
        "question_frame": dict(state.get("question_frame") or {}),
        "plan_class": str(state.get("plan_class") or ""),
        "plan_class_reason": str(state.get("plan_class_reason") or ""),
        "request_plan_class": list(state.get("request_plan_class") or []),
        "resolution": dict(state.get("resolution") or {}),
        "groundings": list(state.get("groundings") or []),
        "discovery": list(state.get("discovery") or []),
        # ── truy xuất ────────────────────────────────────────────────────
        "plan": dict(state.get("plan") or {}),
        "coverage": list(state.get("coverage") or []),
        "fallbacks": list(state.get("fallback_from") or []),
        "evidence": _evidence(list(state.get("evidence") or [])),
        "citations": list(state.get("citations") or []),
        # ── kiểm chứng ───────────────────────────────────────────────────
        "verification": dict(state.get("verification") or {}),
        # ── câu trả lời ──────────────────────────────────────────────────
        "answer": str(state.get("answer") or ""),
        # ── chi phí ──────────────────────────────────────────────────────
        "embedding_used": bool(state.get("embedding_used")),
        "tokens": dict(state.get("tokens") or {}),
        "timings": dict(state.get("timings") or {}),
        "ms": int(state.get("ms") or 0),
        "total_ms": int(state.get("total_ms") or 0),
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
    record["ms"] = int(ms or record.get("ms") or 0)
    record["total_ms"] = int(ms or record.get("total_ms") or 0)
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
