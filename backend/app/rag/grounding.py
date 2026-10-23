"""Phase 3 — ground subject mentions from a QuestionFrame into real entities.

The semantic parser only extracts *mentions* (verbatim text). It must never assign a
procedure code, a document key or a Neo4j id. This module is the only place allowed to turn
a mention into an identifier, and it does so with the deterministic resolvers that already
exist in the project:

```text
code -> exact name -> entity/document vocabulary -> vector resolver -> ambiguous / not_found
```

No LLM call and no new database table are involved. Vector search reuses the caller's
``get_vector`` so a question is still embedded at most once per turn.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from backend.app.rag import disambiguation, graph_query, resolver, theme_agreement

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle
    from backend.app.rag.resolve import Resolution
    from backend.app.workflow.question_frame import QuestionFrame

logger = logging.getLogger(__name__)

GroundingStatus = Literal["resolved", "ambiguous", "not_found", "context_required"]

#: A procedure code as it appears in user text: ``1.001699`` or ``1,001699``.
CODE_PATTERN = re.compile(r"\b\d{1,3}[.,]\d{5,6}\b")

#: Mention type -> closed-vocabulary kind used by ``graph_query``.
ENTITY_KIND = {
    "agency": "co_quan",
    "field": "linh_vuc",
    "administrative_level": "cap",
    "domain_group": "domain_group",
}

#: Maximum number of alternatives exposed to the user when asking back.
MAX_ALTERNATIVES = 5


@dataclass(slots=True)
class SubjectGrounding:
    """One mention resolved (or not) against real data.

    ``index`` is the position in ``QuestionFrame["subject_mentions"]``; requests point at it
    through ``subject_ref``. Keeping the index stable is what lets later phases say exactly
    which request is ambiguous.
    """

    index: int
    status: GroundingStatus
    type: str
    mention: str
    code: str = ""
    name: str = ""
    method: str = ""
    score: float = 0.0
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    #: Top-10 ứng viên cho bước gỡ rối (khác ``alternatives`` chỉ 3 lựa chọn hỏi lại).
    candidates: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mention_index": self.index,
            "status": self.status,
            "type": self.type,
            "mention": self.mention,
            "code": self.code,
            "name": self.name,
            "method": self.method,
            "score": round(float(self.score), 4),
            "alternatives": self.alternatives,
            "candidates": self.candidates,
            "note": self.note,
        }


class _MemoVector:
    """Embed once, reuse for every mention in the same turn."""

    __slots__ = ("_question", "_get", "_value", "_lock")

    def __init__(
        self,
        question: str,
        get_vector: Callable[[], Awaitable[list[float]]] | None,
    ) -> None:
        self._question = question
        self._get = get_vector
        self._value: list[float] | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> list[float]:
        if self._value is not None:
            return self._value
        async with self._lock:
            if self._value is None:
                if self._get is not None:
                    self._value = await self._get()
                else:  # caller had no vector yet — embed the question exactly once
                    from backend.app.rag import embeddings

                    self._value = await embeddings.embed(self._question)
        return self._value


async def _vocabulary() -> graph_query.Vocabulary:
    return await graph_query.vocabulary()


def _is_demonstrative(text: str) -> bool:
    return any(graph_query.has_phrase(text, item) for item in graph_query.DEMONSTRATIVES)


def _alternatives(rows: list[tuple[str, str, float]]) -> list[dict[str, Any]]:
    return [
        {"code": code, "name": name, "score": round(float(score), 4)}
        for code, name, score in rows[:MAX_ALTERNATIVES]
    ]


async def _ground_procedure(
    index: int, text: str, resolution: Resolution, memo: _MemoVector
) -> SubjectGrounding:
    """Procedure mention: code first, then the existing resolver (exact name, then vector)."""
    verified = {str(code): code for code in (resolution.codes or [])}
    mentioned_codes = [code.replace(",", ".") for code in CODE_PATTERN.findall(text)]

    # ① a verified code named in the mention — the strongest possible evidence
    for code in mentioned_codes:
        if code in verified:
            return SubjectGrounding(
                index=index, status="resolved", type="procedure", mention=text,
                code=code, method="code", score=1.0,
            )

    # ② a code the user typed that does not exist — must not be replaced by a similar procedure
    if mentioned_codes:
        asked = list(resolution.asked_codes or [])
        return SubjectGrounding(
            index=index, status="not_found", type="procedure", mention=text,
            method="code", note=f"mã không tồn tại: {', '.join(asked or mentioned_codes)}",
        )

    # ③ a demonstrative without an antecedent — the turn has nothing to point at
    if _is_demonstrative(text) and not resolution.codes and not resolution.ma:
        return SubjectGrounding(
            index=index, status="context_required", type="procedure", mention=text,
            note="đại từ chỉ định không có tiền ngữ trong câu",
        )

    # The parser mention is an identity hint, not a replacement for the user's case details.
    # Resolve against the whole turn so the vector search can distinguish similar procedures.
    target = resolution.question or text
    try:
        found = await resolver.resolve_procedure(target, codes=None, get_vector=memo.get)
    except Exception as exc:  # noqa: BLE001 — grounding failure must not break the turn
        logger.warning("Grounding procedure failed: %s", exc)
        return SubjectGrounding(
            index=index, status="not_found", type="procedure", mention=text,
            note=f"resolver lỗi: {type(exc).__name__}",
        )

    candidate_rows = [
        {"code": code, "name": name, "score": round(float(score), 4)}
        for code, name, score in (found.candidates or [])
    ]
    if found.code and not found.ambiguous:
        return SubjectGrounding(
            index=index, status="resolved", type="procedure", mention=text,
            code=found.code, name=found.name, method=found.method or "vector",
            score=float(found.confidence or 0.0), candidates=candidate_rows,
        )
    if found.ambiguous and found.alternatives:
        return SubjectGrounding(
            index=index, status="ambiguous", type="procedure", mention=text,
            method=found.method or "vector", score=float(found.confidence or 0.0),
            alternatives=_alternatives(list(found.alternatives)),
            candidates=candidate_rows,
            note=found.note,
        )
    return SubjectGrounding(
        index=index, status="not_found", type="procedure", mention=text,
        method=found.method, note=found.note or "không khớp thủ tục nào",
    )


def _ground_document(index: int, text: str, vocab: graph_query.Vocabulary) -> SubjectGrounding:
    matched = graph_query.match_documents(text, vocab)
    if matched.unique is not None:
        return SubjectGrounding(
            index=index, status="resolved", type="document", mention=text,
            code=matched.unique.key, name=matched.unique.name, method="vocabulary", score=1.0,
        )
    if matched.candidates:
        return SubjectGrounding(
            index=index, status="ambiguous", type="document", mention=text, method="vocabulary",
            alternatives=_alternatives([(m.key, m.name, 1.0) for m in matched.candidates]),
        )
    return SubjectGrounding(
        index=index, status="not_found", type="document", mention=text, method="vocabulary",
    )


def _ground_entity(
    index: int, text: str, mention_type: str, vocab: graph_query.Vocabulary
) -> SubjectGrounding:
    expected_kind = ENTITY_KIND.get(mention_type)
    if expected_kind is None:
        return SubjectGrounding(
            index=index, status="not_found", type=mention_type, mention=text,
            note="loại chủ thể này chưa có từ điển đóng",
        )

    matched, ambiguous = graph_query.match_entities(text, vocab)
    if matched is not None:
        if matched.kind == expected_kind:
            return SubjectGrounding(
                index=index, status="resolved", type=mention_type, mention=text,
                code=matched.value, name=matched.label, method="vocabulary", score=1.0,
            )
        return SubjectGrounding(
            index=index, status="not_found", type=mention_type, mention=text,
            method="vocabulary", note=f"khớp loại khác: {matched.kind}",
        )
    if ambiguous:
        same = [m for m in ambiguous if m.kind == expected_kind]
        if same:
            return SubjectGrounding(
                index=index, status="ambiguous", type=mention_type, mention=text,
                method="vocabulary",
                alternatives=_alternatives([(m.value, m.label, 1.0) for m in same]),
                note="nhiều thực thể cùng khớp",
            )
    return SubjectGrounding(
        index=index, status="not_found", type=mention_type, mention=text, method="vocabulary",
    )


def _request_for_mention(frame: QuestionFrame, index: int) -> dict[str, Any] | None:
    for request in frame.get("requests") or []:
        ref = request.get("subject_ref")
        if ref is not None and int(ref) == int(index):
            return request
    return None


def _facet_for_mention(frame: QuestionFrame, index: int) -> str:
    """Khía cạnh đầu tiên của một ý trỏ tới mention, nếu so sánh được bằng section."""
    for request in frame.get("requests") or []:
        ref = request.get("subject_ref")
        if ref is None or int(ref) != int(index):
            continue
        facade = request.get("facet")
        value = str(getattr(facade, "value", facade) or "")
        if value in theme_agreement.THEME_FACETS:
            return value
    return ""


async def _apply_disambiguation(
    items: list[SubjectGrounding], frame: QuestionFrame, question: str
) -> None:
    """Gỡ rối thủ tục bằng tình huống + điều kiện thời hạn.

    Chỉ áp dụng cho câu hỏi **thời hạn** và khi có ít nhất hai ứng viên. Có thể **ghi đè**
    kết quả resolver đã ``resolved`` — đây là thay đổi có chủ ý, vì vector top-1 có thể sai
    (A2). Mọi lần đổi đều ghi lý do vào ``note``.
    """
    for item in items:
        if item.type != "procedure" or len(item.candidates) < 2:
            continue
        request = _request_for_mention(frame, item.index)
        if request is None:
            continue
        facade = request.get("facet")
        facet = str(getattr(facade, "value", facade) or "")
        scenario = " ".join(str(request.get("scenario") or "").split())
        text = scenario or item.mention or question
        try:
            decision = await disambiguation.rerank(
                [
                    (str(row["code"]), str(row.get("name") or ""), float(row.get("score") or 0.0))
                    for row in item.candidates
                ],
                text=text,
                facet=facet,
            )
        except Exception as exc:  # noqa: BLE001 — gỡ rối lỗi không được làm hỏng lượt
            logger.warning("Gỡ rối thủ tục lỗi: %s", exc)
            continue
        if decision is None:
            continue
        item.status = "resolved"
        item.code = decision.code
        item.name = decision.name or item.name
        item.method = "disambiguation"
        item.score = decision.score
        item.note = decision.note


async def _apply_theme_agreement(
    items: list[SubjectGrounding], frame: QuestionFrame
) -> None:
    """Biến ``ambiguous`` thành ``resolved`` **chỉ khi** nhóm thủ tục trả lời được.

    Không có nhóm, nhóm không đồng thuận và không có đại diện → giữ nguyên ``ambiguous``
    để bước sau hỏi lại như cũ.
    """
    requests = frame.get("requests") or []
    if not requests:
        return
    for item in items:
        if item.type != "procedure" or item.status != "ambiguous":
            continue
        facet = _facet_for_mention(frame, item.index)
        if not facet:
            continue
        codes = [str(alt.get("code")) for alt in item.alternatives if alt.get("code")]
        try:
            decision = await theme_agreement.resolve_theme(codes, facet)
        except Exception as exc:  # noqa: BLE001 — so sánh lỗi không được làm hỏng lượt
            logger.warning("So sánh nhóm thủ tục lỗi: %s", exc)
            continue
        if decision is None:
            continue
        item.status = "resolved"
        item.code = decision.code
        item.name = decision.name or item.name
        item.method = "theme"
        item.score = item.score or 1.0
        item.note = decision.note


async def ground_frame(
    frame: QuestionFrame,
    resolution: Resolution,
    *,
    question: str = "",
    get_vector: Callable[[], Awaitable[list[float]]] | None = None,
) -> list[SubjectGrounding]:
    """Ground every subject mention. Never raises: a failed mention becomes ``not_found``."""
    mentions = list(frame.get("subject_mentions") or [])
    if not mentions:
        return []

    memo = _MemoVector(question or resolution.question, get_vector)
    items: list[SubjectGrounding] = []
    for index, mention in enumerate(mentions):
        mention_type = str(mention.get("type") or "unknown")
        text = str(mention.get("text") or "").strip()
        if not text:
            continue
        try:
            if mention_type == "procedure":
                item = await _ground_procedure(index, text, resolution, memo)
            elif mention_type == "document":
                item = _ground_document(index, text, await _vocabulary())
                if item.status == "not_found":
                    # "Đơn đăng ký biến động…" là tên mẫu đơn, parser có thể gán nhầm
                    # document. Thử lại như tên thủ tục trước khi kết luận không tìm thấy.
                    thu_lai = await _ground_procedure(index, text, resolution, memo)
                    if thu_lai.status != "not_found":
                        item = thu_lai
            elif mention_type in ENTITY_KIND:
                item = _ground_entity(index, text, mention_type, await _vocabulary())
            else:
                item = SubjectGrounding(
                    index=index, status="not_found", type=mention_type, mention=text,
                    note="loại chủ thể chưa được hỗ trợ ở giai đoạn này",
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Grounding mention %s failed: %s", index, exc)
            item = SubjectGrounding(
                index=index, status="not_found", type=mention_type, mention=text,
                note=f"grounding lỗi: {type(exc).__name__}",
            )
        items.append(item)
    await _apply_disambiguation(items, frame, question or resolution.question)
    await _apply_theme_agreement(items, frame)
    return items


# ── Aggregates used by the adapter and by later phases ─────────────────────


def procedure_groundings(items: list[SubjectGrounding]) -> list[SubjectGrounding]:
    return [item for item in items if item.type == "procedure"]


def resolved_procedure(items: list[SubjectGrounding]) -> SubjectGrounding | None:
    """First resolved procedure mention, if any."""
    return next(
        (item for item in items if item.type == "procedure" and item.status == "resolved"), None
    )


def ambiguous_procedure(items: list[SubjectGrounding]) -> SubjectGrounding | None:
    return next(
        (item for item in items if item.type == "procedure" and item.status == "ambiguous"), None
    )


def context_required_mention(items: list[SubjectGrounding]) -> SubjectGrounding | None:
    return next((item for item in items if item.status == "context_required"), None)


def first_ambiguous(items: list[SubjectGrounding]) -> SubjectGrounding | None:
    """Any ambiguous mention (procedure, document or closed entity) that can offer options."""
    return next(
        (item for item in items if item.status == "ambiguous" and item.alternatives), None
    )


def unresolved_subject_refs(frame: QuestionFrame, items: list[SubjectGrounding]) -> list[int]:
    """Request indexes whose ``subject_ref`` is ambiguous, missing or needs context."""
    bad = {
        item.index
        for item in items
        if item.status in {"ambiguous", "not_found", "context_required"}
    }
    return [
        index
        for index, request in enumerate(frame.get("requests") or [])
        if request.get("subject_ref") is not None and int(request["subject_ref"]) in bad
    ]


__all__ = [
    "CODE_PATTERN",
    "ENTITY_KIND",
    "GroundingStatus",
    "MAX_ALTERNATIVES",
    "SubjectGrounding",
    "ambiguous_procedure",
    "context_required_mention",
    "first_ambiguous",
    "ground_frame",
    "procedure_groundings",
    "resolved_procedure",
    "unresolved_subject_refs",
]
