"""Phase 5 — execute a RetrievalPlan, compute per-request coverage, run bounded fallback.

The executor is the only place that turns planned tasks into evidence. It reuses the existing
retrieval functions (sections, fact lookup, graph templates, hybrid) and adds four things the
single-branch flow could not do:

* run independent tasks in parallel, with a timeout per tool;
* tag every evidence item with the request it answers, so the answer can follow the user's
  order and a missing request is visible instead of silently dropped;
* compute coverage per request (``covered`` / ``empty`` / ``failed`` / ``unsupported``);
* fall back at most once per request, recording ``from`` -> ``to``.

The answer model never decides that data is missing; it only sees the evidence and the list of
facets that coverage marked empty.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from backend.app.rag import (
    contracts,
    embeddings,
    fact_lookup,
    graph_query,
    hybrid,
    resolve,
    sections,
)
from backend.app.rag.evidence import from_chunks, from_fact, from_graph, from_sections
from backend.app.workflow.planner import (
    REASON_AMBIGUOUS_SUBJECT,
    REASON_CONTEXT_REQUIRED,
    REASON_MISSING_SUBJECT,
    TOOL_FACT,
    TOOL_GRAPH,
    TOOL_HYBRID,
    TOOL_SECTION,
    Plan,
    Task,
)
from backend.app.workflow.state import AgentState

logger = logging.getLogger(__name__)

#: Timeout cho một task. Một nguồn chậm không được giữ cả lượt.
TASK_TIMEOUT_S = 6.0

STATUS_COVERED = "covered"
STATUS_EMPTY = "empty"
STATUS_FAILED = "failed"
STATUS_UNSUPPORTED = "unsupported"
STATUS_AMBIGUOUS = "ambiguous"

#: Lý do cần hỏi lại thay vì từ chối (subject chưa xác định).
CLARIFY_REASONS = frozenset(
    {REASON_AMBIGUOUS_SUBJECT, REASON_CONTEXT_REQUIRED, REASON_MISSING_SUBJECT}
)


@dataclass(slots=True)
class RequestCoverage:
    request_index: int
    status: str
    facet: str = ""
    tool: str = ""
    fallback_from: str = ""
    fallback_to: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "request_index": self.request_index,
            "status": self.status,
            "facet": self.facet,
            "tool": self.tool,
        }
        if self.fallback_from:
            data["fallback_from"] = self.fallback_from
            data["fallback_to"] = self.fallback_to
        if self.note:
            data["note"] = self.note
        return data


@dataclass(slots=True)
class ToolResult:
    """Kết quả một lần gọi tool: bằng chứng, hoặc yêu cầu hỏi lại từ Graph."""

    items: list[dict[str, Any]] = field(default_factory=list)
    clarify: dict[str, Any] | None = None
    #: ``""`` = chạy bình thường. ``failed`` = hạ tầng lỗi; ``unsupported`` = không áp được
    #: điều kiện. Không bao giờ để lỗi hạ tầng thành ``empty``.
    status: str = ""
    error: str = ""


@dataclass(slots=True)
class Execution:
    evidence: list[dict[str, Any]] = field(default_factory=list)
    coverage: list[RequestCoverage] = field(default_factory=list)
    #: (request_index, from_tool, to_tool) — ghi vào ``fallback_from`` của state.
    fallbacks: list[tuple[int, str, str]] = field(default_factory=list)
    #: Vector dùng cho hybrid, nếu executor đã nhúng. Node ghi lại vào state để không nhúng lần nữa.
    vector: list[float] | None = None
    vector_used: bool = False
    #: Câu hỏi lại do tool trả về (Graph mơ hồ văn bản/thực thể), kèm lựa chọn thật.
    clarifies: list[tuple[int, dict[str, Any]]] = field(default_factory=list)
    ms: int = 0

    @property
    def clarify(self) -> dict[str, Any] | None:
        return self.clarifies[0][1] if self.clarifies else None

    @property
    def covered(self) -> int:
        return sum(1 for item in self.coverage if item.status == STATUS_COVERED)

    @property
    def failed_all(self) -> bool:
        real = [item for item in self.coverage if item.status != STATUS_UNSUPPORTED]
        return bool(real) and all(item.status == STATUS_FAILED for item in real)


class _VectorSource:
    """Lazily embed the question once; reuse the stored vector when available."""

    def __init__(self, state: AgentState) -> None:
        self._state = state
        #: Single-flight: `create_task` chỉ chạy một lần; mọi task khác chờ đúng future đó.
        self._task: asyncio.Task[list[float]] | None = None
        self._value: list[float] | None = None
        self.used = False

    async def get(self) -> list[float]:
        if self._task is None:
            self._task = asyncio.create_task(self._load())
        return await self._task

    async def _load(self) -> list[float]:
        stored = resolve.get_vector(str(self._state.get("vector_hash") or ""))
        if stored is not None:
            self._value = stored
            return stored
        self.used = True
        self._value = await embeddings.embed(str(self._state.get("question") or ""))
        return self._value


def filter_by_facet(items: list[dict[str, Any]], facet: str) -> list[dict[str, Any]]:
    """Keep only items whose section belongs to the requested facet."""
    return [
        item
        for item in items
        if sections.khia_canh_cua(str(item.get("section_type") or "")) == facet
    ]


def _tag(items: list[dict[str, Any]], task: Task) -> list[dict[str, Any]]:
    for item in items:
        item["request_index"] = task.request_index
        item["facet"] = task.facet
    return items


async def _constraint_entity(
    task: Task,
) -> tuple[graph_query.EntityMatch | None, str]:
    """Ground a supported constraint. Trả ``(entity, lỗi)`` — **không** bỏ im lặng.

    Constraint có mà không ground được thì truy vấn sẽ rộng hơn người dùng yêu cầu. Vì vậy
    trường hợp đó phải thành ``unsupported``/``failed``, không được chạy như không có điều kiện.
    """
    kind_by_constraint = {
        "agency": "co_quan",
        "field": "linh_vuc",
        "administrative_level": "cap",
        "domain_group": "domain_group",
    }
    if not task.constraints:
        return None, ""
    try:
        vocabulary = await graph_query.vocabulary()
    except Exception as exc:  # noqa: BLE001
        return None, f"không nạp được từ điển đồ thị: {type(exc).__name__}"
    for constraint in task.constraints:
        kind = kind_by_constraint.get(constraint.get("type") or "")
        text = str(constraint.get("text") or "").strip()
        if kind is None or not text:
            continue
        matched, _ = graph_query.match_entities(text, vocabulary)
        if matched is not None and matched.kind == kind:
            return matched, ""
    return None, "không xác định được giá trị của điều kiện lọc"


async def _run_section(task: Task) -> ToolResult:
    rows, error = await sections.theo_khia_canh_checked(
        list(task.procedure_codes), [task.facet]
    )
    if error:
        return ToolResult([], status=STATUS_FAILED, error=error)
    return ToolResult(from_sections(rows))


async def _run_fact(task: Task) -> ToolResult:
    facts, error = await fact_lookup.get_facts_checked(list(task.procedure_codes))
    if error:
        return ToolResult([], status=STATUS_FAILED, error=error)
    return ToolResult([item for fact in facts for item in from_fact(fact)])


async def _run_graph(
    task: Task, question: str, vector_source: _VectorSource
) -> ToolResult:
    entity, loi_dieu_kien = await _constraint_entity(task)
    if task.constraints and entity is None:
        return ToolResult([], status=STATUS_UNSUPPORTED, error=loi_dieu_kien)
    evidence = await graph_query.answer(
        question,
        codes=list(task.procedure_codes) or None,
        requested_facets=[task.facet],
        get_vector=vector_source.get,
        entity=entity,
        expected_types=task.expected_types,
        intent=task.intent or None,
    )
    if getattr(evidence, "failed", False):
        return ToolResult([], status=STATUS_FAILED, error=evidence.note)
    if evidence.clarify:
        return ToolResult(
            [],
            {
                "question": evidence.clarify_question or "Bạn muốn chọn mục nào?",
                "options": list(evidence.options or []),
                "note": evidence.note,
            },
        )
    if not (evidence.rows or evidence.parts):
        return ToolResult([])
    return ToolResult(from_graph(evidence))


async def _run_hybrid(
    task: Task, question: str, vector_source: _VectorSource
) -> ToolResult:
    vector = await vector_source.get()
    outcome = await hybrid.hybrid(
        question,
        vector=vector,
        codes=list(task.procedure_codes) or None,
        # use_rerank=True,
        use_gate=not task.procedure_codes,
    )
    items = filter_by_facet(from_chunks(outcome.candidates), task.facet)
    errors = list(getattr(outcome, "errors", None) or [])
    if not items and errors:
        return ToolResult([], status=STATUS_FAILED, error="; ".join(errors))
    if task.procedure_codes:
        # Có mã đã xác thực: đoạn văn được neo vào thủ tục thật → bằng chứng đã kiểm.
        items = contracts.mark_verified(items, "hybrid_with_verified_code")
    return ToolResult(items)


async def _run_once(
    task: Task, question: str, vector_source: _VectorSource
) -> ToolResult:
    if task.tool == TOOL_SECTION:
        return await _run_section(task)
    if task.tool == TOOL_FACT:
        return await _run_fact(task)
    if task.tool == TOOL_GRAPH:
        return await _run_graph(task, question, vector_source)
    if task.tool == TOOL_HYBRID:
        return await _run_hybrid(task, question, vector_source)
    raise ValueError(f"tool không hỗ trợ: {task.tool}")


def _fallback_tool(task: Task) -> str:
    """The single fallback allowed per request (empty string = none)."""
    if task.tool == TOOL_SECTION:
        return TOOL_HYBRID
    if task.tool == TOOL_GRAPH and task.facet == "legal_basis":
        return TOOL_SECTION
    return ""


async def _execute_task(
    task: Task, question: str, vector_source: _VectorSource
) -> tuple[list[dict[str, Any]], RequestCoverage]:
    clarify: dict[str, Any] | None = None
    try:
        result = await asyncio.wait_for(
            _run_once(task, question, vector_source), timeout=TASK_TIMEOUT_S
        )
    except Exception as exc:  # noqa: BLE001 — một nguồn lỗi không làm mất nguồn khác
        logger.warning("Task %s (%s) lỗi: %s", task.request_index, task.tool, exc)
        items, status, note = [], STATUS_FAILED, f"{type(exc).__name__}: {str(exc)[:120]}"
    else:
        items = result.items
        clarify = result.clarify
        if result.status == STATUS_FAILED:
            status, note = STATUS_FAILED, result.error
        elif result.status == STATUS_UNSUPPORTED:
            status, note = STATUS_UNSUPPORTED, result.error
        elif clarify is not None:
            status = STATUS_AMBIGUOUS
            note = str(clarify.get("question") or "")
        else:
            status = STATUS_COVERED if items else STATUS_EMPTY
            note = ""

    fallback = ""
    if status in {STATUS_EMPTY, STATUS_FAILED}:
        alt = _fallback_tool(task)
        if alt:
            alt_task = Task(
                request_index=task.request_index,
                tool=alt,
                facet=task.facet,
                operation=task.operation,
                intent=task.intent,
                expected_types=task.expected_types,
                procedure_codes=task.procedure_codes,
                subject_ref=task.subject_ref,
                constraints=task.constraints,
            )
            try:
                alt_result = await asyncio.wait_for(
                    _run_once(alt_task, question, vector_source), timeout=TASK_TIMEOUT_S
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Fallback %s -> %s lỗi: %s", task.tool, alt, exc)
                alt_result = ToolResult([])
            if alt_result.items:
                items, status, note = alt_result.items, STATUS_COVERED, ""
                clarify = None
                fallback = alt
            elif alt_result.status == STATUS_FAILED:
                status, note = STATUS_FAILED, alt_result.error

    coverage = RequestCoverage(
        request_index=task.request_index,
        status=status,
        facet=task.facet,
        tool=fallback or task.tool,
        fallback_from=task.tool if fallback else "",
        fallback_to=fallback,
        note=note,
    )
    if clarify is not None:
        coverage.note = str(clarify.get("question") or coverage.note)
    return _tag(items, task), coverage, clarify


async def execute_plan(state: AgentState, plan: Plan) -> Execution:
    """Run every task (parallel), then attach coverage for unsupported requests."""
    started = time.perf_counter()
    question = str(state.get("question") or "")
    vector_source = _VectorSource(state)

    results = await asyncio.gather(
        *(_execute_task(task, question, vector_source) for task in plan.tasks)
    )

    execution = Execution()
    for items, coverage, clarify in results:
        execution.evidence.extend(items)
        execution.coverage.append(coverage)
        if clarify is not None:
            execution.clarifies.append((coverage.request_index, clarify))
        if coverage.fallback_from:
            execution.fallbacks.append(
                (coverage.request_index, coverage.fallback_from, coverage.fallback_to)
            )

    for item in plan.unsupported:
        execution.coverage.append(
            RequestCoverage(
                request_index=int(item["request_index"]),
                status=STATUS_UNSUPPORTED,
                facet=str(item.get("facet") or ""),
                note=str(item.get("reason") or ""),
            )
        )

    # Keep evidence in the order the user asked, even though tasks ran in parallel.
    execution.evidence.sort(key=lambda item: int(item.get("request_index") or 0))
    execution.coverage.sort(key=lambda item: item.request_index)

    execution.vector_used = vector_source.used
    execution.vector = vector_source._value  # noqa: SLF001
    execution.ms = int((time.perf_counter() - started) * 1000)
    return execution


__all__ = [
    "CLARIFY_REASONS",
    "Execution",
    "RequestCoverage",
    "STATUS_AMBIGUOUS",
    "STATUS_COVERED",
    "STATUS_EMPTY",
    "STATUS_FAILED",
    "STATUS_UNSUPPORTED",
    "TASK_TIMEOUT_S",
    "ToolResult",
    "filter_by_facet",
    "execute_plan",
]
