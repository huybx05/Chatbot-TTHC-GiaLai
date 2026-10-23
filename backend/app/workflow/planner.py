"""Phase 4 — deterministic retrieval planner.

The planner receives a ``QuestionFrame`` plus its groundings and produces concrete retrieval
tasks. It is **code only**: no LLM call, no database query, no SQL/Cypher text.

Capability is a closed matrix. A facet is planned only when a template exists and the evidence
returns a column that identifies the exact thing asked for:

```text
facet                 intent                     expected node types
issuing_agency        AGENCY                     BAN_HANH_BOI
implementing_agency   AGENCY                     CO_THAM_QUYEN
coordinating_agency   AGENCY                     PHOI_HOP
authorized_agency     AGENCY                     DUOC_UY_QUYEN
administrative_level  CLASSIFY                   CAP_THUC_HIEN
field                 CLASSIFY                   LINH_VUC
domain_group          CLASSIFY                   DOMAIN_GROUP
status                CLASSIFY                   TRANG_THAI
target_audience       AUDIENCE                   (one relation, no filter needed)
legal_basis           LEGAL_BASIS_OF_PROCEDURE   (document rows)
```

For list/count without a procedure code the planner selects the reverse templates
(``PROCEDURES_BY_AGENCY/FIELD/LEVEL/GROUP``). Anything outside the matrix is ``unsupported``;
the planner never falls back to keyword classification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from backend.app.rag.grounding import SubjectGrounding
from backend.app.workflow.question_frame import Facet, QuestionScope, RequestOperation

if TYPE_CHECKING:  # pragma: no cover - typing only
    from backend.app.workflow.question_frame import QuestionFrame

logger = logging.getLogger(__name__)

TOOL_SECTION = "section_lookup"
TOOL_GRAPH = "graph"
TOOL_HYBRID = "hybrid"
TOOL_FACT = "fact_lookup"

SECTION_FACETS = frozenset(
    {
        Facet.REQUIRED_DOCUMENTS.value,
        Facet.STEPS.value,
        Facet.SUBMISSION_METHOD.value,
        Facet.PROCESSING_TIME.value,
        Facet.FEE.value,
        Facet.RESULT.value,
        Facet.REQUIREMENTS.value,
    }
)

AGGREGATE_OPERATIONS = frozenset({RequestOperation.LIST.value, RequestOperation.COUNT.value})
UNSUPPORTED_OPERATIONS = frozenset(
    {RequestOperation.COMPARE.value, RequestOperation.RANK.value}
)
UNSUPPORTED_FACETS = frozenset({Facet.RELATED_PROCEDURES.value, Facet.UNKNOWN.value})

#: Constraints the reverse Graph templates can filter on (``Shape.filter_param``).
REVERSE_CONSTRAINTS = frozenset({"agency", "field", "administrative_level", "domain_group"})

REASON_UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
REASON_UNSUPPORTED_FACET = "UNSUPPORTED_FACET"
REASON_UNSUPPORTED_COUNT = "UNSUPPORTED_COUNT"
REASON_UNSUPPORTED_CONSTRAINT = "UNSUPPORTED_CONSTRAINT"
REASON_MISSING_SUBJECT = "MISSING_SUBJECT"
REASON_AMBIGUOUS_SUBJECT = "AMBIGUOUS_SUBJECT"
REASON_UNRESOLVED_SUBJECT = "UNRESOLVED_SUBJECT"
REASON_CONTEXT_REQUIRED = "CONTEXT_REQUIRED"


@dataclass(frozen=True, slots=True)
class Capability:
    """A template the planner is allowed to use for one facet."""

    intent: str
    expected_types: tuple[str, ...] = ()


#: Forward templates: the procedure code is known, the answer is about that procedure.
FORWARD_CAPABILITY: dict[str, Capability] = {
    Facet.ISSUING_AGENCY.value: Capability("AGENCY", ("BAN_HANH_BOI",)),
    Facet.IMPLEMENTING_AGENCY.value: Capability("AGENCY", ("CO_THAM_QUYEN",)),
    Facet.COORDINATING_AGENCY.value: Capability("AGENCY", ("PHOI_HOP",)),
    Facet.AUTHORIZED_AGENCY.value: Capability("AGENCY", ("DUOC_UY_QUYEN",)),
    Facet.ADMINISTRATIVE_LEVEL.value: Capability("CLASSIFY", ("CAP_THUC_HIEN",)),
    Facet.FIELD.value: Capability("CLASSIFY", ("LINH_VUC",)),
    Facet.DOMAIN_GROUP.value: Capability("CLASSIFY", ("DOMAIN_GROUP",)),
    Facet.STATUS.value: Capability("CLASSIFY", ("TRANG_THAI",)),
    Facet.TARGET_AUDIENCE.value: Capability("AUDIENCE"),
    Facet.LEGAL_BASIS.value: Capability("LEGAL_BASIS_OF_PROCEDURE"),
}

#: Reverse templates: the subject is an entity (agency, field, level, group), no code.
REVERSE_CAPABILITY: dict[str, Capability] = {
    Facet.ISSUING_AGENCY.value: Capability("PROCEDURES_BY_AGENCY"),
    Facet.IMPLEMENTING_AGENCY.value: Capability("PROCEDURES_BY_AGENCY"),
    Facet.COORDINATING_AGENCY.value: Capability("PROCEDURES_BY_AGENCY"),
    Facet.AUTHORIZED_AGENCY.value: Capability("PROCEDURES_BY_AGENCY"),
    Facet.ADMINISTRATIVE_LEVEL.value: Capability("PROCEDURES_BY_LEVEL"),
    Facet.FIELD.value: Capability("PROCEDURES_BY_FIELD"),
    Facet.DOMAIN_GROUP.value: Capability("PROCEDURES_BY_GROUP"),
}


@dataclass(slots=True)
class Task:
    """One retrieval action for one request."""

    request_index: int
    tool: str
    facet: str
    operation: str
    intent: str = ""
    expected_types: tuple[str, ...] = ()
    procedure_codes: tuple[str, ...] = ()
    subject_ref: int | None = None
    constraints: tuple[dict[str, str], ...] = ()
    reason: str = ""
    merged_from: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "request_index": self.request_index,
            "tool": self.tool,
            "facet": self.facet,
            "operation": self.operation,
            "procedure_codes": list(self.procedure_codes),
        }
        if self.intent:
            data["intent"] = self.intent
        if self.expected_types:
            data["expected_types"] = list(self.expected_types)
        if self.subject_ref is not None:
            data["subject_ref"] = self.subject_ref
        if self.constraints:
            data["constraints"] = list(self.constraints)
        if self.reason:
            data["reason"] = self.reason
        if self.merged_from:
            data["merged_from"] = list(self.merged_from)
        return data


@dataclass(slots=True)
class Plan:
    tasks: list[Task] = field(default_factory=list)
    unsupported: list[dict[str, Any]] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not self.tasks

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks": [task.to_dict() for task in self.tasks],
            "unsupported": list(self.unsupported),
        }


def _blocked_reason(status: str) -> str:
    if status == "ambiguous":
        return REASON_AMBIGUOUS_SUBJECT
    if status == "context_required":
        return REASON_CONTEXT_REQUIRED
    return REASON_UNRESOLVED_SUBJECT


def _subject_for(
    request: dict[str, Any], by_index: dict[int, SubjectGrounding]
) -> tuple[tuple[str, ...], str]:
    """Return ``(codes, blocked_reason)``. Empty codes = no procedure code required."""
    ref = request.get("subject_ref")
    if ref is None:
        return (), ""
    item = by_index.get(int(ref))
    if item is None:
        return (), REASON_MISSING_SUBJECT
    if item.status != "resolved":
        return (), _blocked_reason(item.status)
    if item.type == "procedure":
        return ((item.code,) if item.code else ()), ""
    return (), ""


def _normalize_constraints(request: dict[str, Any]) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    for item in request.get("constraints") or []:
        kind = str(item.get("type") or "").strip()
        text = " ".join(str(item.get("text") or "").split())
        if kind or text:
            rows.append({"type": kind, "text": text})
    return tuple(rows)


def _constraints_allowed(
    constraints: tuple[dict[str, str], ...], *, tool: str, intent: str
) -> bool:
    """Only reverse graph templates can filter, and only on known parameters."""
    if not constraints:
        return True
    if tool != TOOL_GRAPH or not intent.startswith("PROCEDURES_BY_"):
        return False
    return all(item["type"] in REVERSE_CONSTRAINTS for item in constraints)


def _choose_tool(
    facet: str, operation: str, codes: tuple[str, ...]
) -> tuple[str, str, tuple[str, ...], str]:
    """Return ``(tool, intent, expected_types, reason)``. Non-empty reason = unsupported."""
    if operation in UNSUPPORTED_OPERATIONS:
        return "", "", (), REASON_UNSUPPORTED_OPERATION
    if facet in UNSUPPORTED_FACETS:
        return "", "", (), REASON_UNSUPPORTED_FACET

    if facet in FORWARD_CAPABILITY or facet in REVERSE_CAPABILITY:
        # With a code the forward template answers "what is X of this procedure"; without one
        # the only meaningful template is the reverse one, which starts from an entity.
        cap = FORWARD_CAPABILITY.get(facet) if codes else REVERSE_CAPABILITY.get(facet)
        if cap is None:
            return "", "", (), REASON_UNSUPPORTED_FACET
        return TOOL_GRAPH, cap.intent, cap.expected_types, ""

    if facet == Facet.GENERAL_INFO.value:
        if operation in AGGREGATE_OPERATIONS:
            return "", "", (), REASON_UNSUPPORTED_OPERATION
        return (TOOL_FACT, "", (), "") if codes else (TOOL_HYBRID, "", (), "")

    if facet in SECTION_FACETS:
        if operation == RequestOperation.COUNT.value:
            return "", "", (), REASON_UNSUPPORTED_COUNT
        return (TOOL_SECTION, "", (), "") if codes else (TOOL_HYBRID, "", (), "")

    return "", "", (), REASON_UNSUPPORTED_FACET


def plan_retrieval(frame: QuestionFrame, groundings: list[SubjectGrounding]) -> Plan:
    """Build a plan from a validated frame and its groundings. Never raises."""
    by_index = {item.index: item for item in groundings}
    plan = Plan()

    if frame.get("scope") in {QuestionScope.OUT_OF_SCOPE, QuestionScope.SMALLTALK}:
        return plan

    seen: dict[tuple[Any, ...], Task] = {}

    for index, request in enumerate(frame.get("requests") or []):
        facet = str(request.get("facet") or Facet.UNKNOWN.value)
        operation = str(request.get("operation") or RequestOperation.GET.value)
        text = " ".join(str(request.get("text") or "").split())

        codes, blocked = _subject_for(request, by_index)
        if blocked:
            plan.unsupported.append(
                {"request_index": index, "reason": blocked, "text": text}
            )
            continue

        tool, intent, expected_types, reason = _choose_tool(facet, operation, codes)
        if reason:
            plan.unsupported.append(
                {"request_index": index, "reason": reason, "text": text}
            )
            continue

        constraints = _normalize_constraints(request)
        if not _constraints_allowed(constraints, tool=tool, intent=intent):
            plan.unsupported.append(
                {
                    "request_index": index,
                    "reason": REASON_UNSUPPORTED_CONSTRAINT,
                    "text": text,
                    "constraints": list(constraints),
                }
            )
            continue

        # Structural key: two phrasings of the same need must merge; different constraints
        # must not.
        key = (
            tool,
            intent,
            expected_types,
            facet,
            operation,
            codes,
            tuple((item["type"], item["text"]) for item in constraints),
        )
        if key in seen:
            seen[key].merged_from.append(index)
            continue

        task = Task(
            request_index=index,
            tool=tool,
            facet=facet,
            operation=operation,
            intent=intent,
            expected_types=expected_types,
            procedure_codes=codes,
            subject_ref=request.get("subject_ref"),
            constraints=constraints,
        )
        seen[key] = task
        plan.tasks.append(task)

    plan.tasks.sort(key=lambda task: task.request_index)
    plan.unsupported.sort(key=lambda item: int(item["request_index"]))
    return plan


__all__ = [
    "AGGREGATE_OPERATIONS",
    "Capability",
    "FORWARD_CAPABILITY",
    "Plan",
    "REASON_AMBIGUOUS_SUBJECT",
    "REASON_CONTEXT_REQUIRED",
    "REASON_MISSING_SUBJECT",
    "REASON_UNRESOLVED_SUBJECT",
    "REASON_UNSUPPORTED_CONSTRAINT",
    "REASON_UNSUPPORTED_COUNT",
    "REASON_UNSUPPORTED_FACET",
    "REASON_UNSUPPORTED_OPERATION",
    "REVERSE_CAPABILITY",
    "REVERSE_CONSTRAINTS",
    "SECTION_FACETS",
    "TOOL_FACT",
    "TOOL_GRAPH",
    "TOOL_HYBRID",
    "TOOL_SECTION",
    "Task",
    "UNSUPPORTED_FACETS",
    "UNSUPPORTED_OPERATIONS",
    "plan_retrieval",
]
