"""Phase 3 tests — subject grounding.

No model calls and no database: the resolvers and the closed vocabulary are replaced with
fakes. These tests lock the policy that matters for safety:

* a verified code always wins;
* an unknown code is never replaced by a similar procedure;
* a demonstrative without an antecedent asks for a code/name;
* an ambiguous mention carries real alternatives for the clarify UI.
"""

from __future__ import annotations

import asyncio

from backend.app.rag import graph_query, grounding, resolver
from backend.app.rag.grounding import SubjectGrounding, ground_frame
from backend.app.workflow import question_parser
from backend.app.workflow.question_frame import (
    QUESTION_FRAME_SCHEMA_VERSION,
    AmbiguityInfo,
    AmbiguityKind,
    Facet,
    QuestionFrame,
    QuestionScope,
    RequestOperation,
    SubjectType,
)
from backend.app.workflow.question_parser import ParseResult


def _resolution(**over):
    from backend.app.rag.resolve import Resolution

    base = Resolution(question="câu hỏi")
    for key, value in over.items():
        setattr(base, key, value)
    return base


def _frame(mentions, requests=None) -> QuestionFrame:
    return QuestionFrame(
        schema_version=QUESTION_FRAME_SCHEMA_VERSION,
        scope=QuestionScope.TTHC,
        subject_mentions=[
            {"type": SubjectType(kind), "text": text} for kind, text in mentions
        ],
        requests=requests
        or [
            {
                "text": "cần gì",
                "facet": Facet.REQUIRED_DOCUMENTS,
                "operation": RequestOperation.GET,
                "subject_ref": 0,
                "constraints": [],
            }
        ],
        ambiguity=AmbiguityInfo(present=False, kind=AmbiguityKind.NONE, reason=""),
    )


# ── procedure mentions ─────────────────────────────────────────────────────


def test_verified_code_is_resolved_without_calling_resolver(monkeypatch) -> None:
    def reject(*_a, **_k):
        raise AssertionError("có mã đã xác minh thì không được gọi resolver")

    monkeypatch.setattr(resolver, "resolve_procedure", reject)
    items = asyncio.run(
        ground_frame(
            _frame([("procedure", "thủ tục 1.001699")]),
            _resolution(codes=["1.001699"]),
        )
    )
    assert items[0].status == "resolved"
    assert items[0].code == "1.001699"
    assert items[0].method == "code"


def test_unknown_code_is_not_replaced(monkeypatch) -> None:
    def reject(*_a, **_k):
        raise AssertionError("mã không tồn tại thì không được tìm theo nghĩa")

    monkeypatch.setattr(resolver, "resolve_procedure", reject)
    items = asyncio.run(
        ground_frame(
            _frame([("procedure", "thủ tục 1.999999")]),
            _resolution(asked_codes=["1.999999"]),
        )
    )
    assert items[0].status == "not_found"
    assert "1.999999" in items[0].note


def test_demonstrative_without_antecedent_needs_context() -> None:
    items = asyncio.run(
        ground_frame(_frame([("procedure", "thủ tục này")]), _resolution())
    )
    assert items[0].status == "context_required"


def test_resolver_resolved(monkeypatch) -> None:
    async def fake(_text, *, codes=None, get_vector=None):
        return resolver.ProcedureResolution(
            code="1.001699", name="Cấp Giấy xác nhận khuyết tật", method="vector", confidence=0.84
        )

    monkeypatch.setattr(resolver, "resolve_procedure", fake)
    items = asyncio.run(
        ground_frame(
            _frame([("procedure", "giấy xác nhận khuyết tật")]),
            _resolution(),
        )
    )
    assert items[0].status == "resolved"
    assert items[0].code == "1.001699"
    assert items[0].method == "vector"


def test_procedure_grounding_keeps_full_question_context(monkeypatch) -> None:
    seen: list[str] = []

    async def fake(text, *, codes=None, get_vector=None):
        seen.append(text)
        return resolver.ProcedureResolution(code="1.115362", method="vector", confidence=0.8)

    monkeypatch.setattr(resolver, "resolve_procedure", fake)
    question = "Sang tên quyền sử dụng đất trong dự án thì mất bao lâu?"
    asyncio.run(
        ground_frame(
            _frame([("procedure", "sang tên")]),
            _resolution(question=question),
        )
    )
    assert seen == [question]


def test_resolver_ambiguous_keeps_alternatives(monkeypatch) -> None:
    async def fake(_text, *, codes=None, get_vector=None):
        return resolver.ProcedureResolution(
            ambiguous=True,
            alternatives=[("1.115345", "Cấp đổi", 0.66), ("1.115350", "Cấp lại", 0.65)],
            note="hai thủ tục sát nhau",
        )

    monkeypatch.setattr(resolver, "resolve_procedure", fake)
    items = asyncio.run(
        ground_frame(_frame([("procedure", "đổi sổ đỏ bị rách")]), _resolution())
    )
    assert items[0].status == "ambiguous"
    assert [a["code"] for a in items[0].alternatives] == ["1.115345", "1.115350"]


# ── document and closed-entity mentions ───────────────────────────────────


def _document_resolution(unique=None, candidates=()):
    return graph_query.DocumentResolution(unique=unique, candidates=list(candidates))


def test_document_unique(monkeypatch) -> None:
    async def fake_vocab():
        return graph_query.Vocabulary(run_id="test")

    monkeypatch.setattr(graph_query, "vocabulary", fake_vocab)
    monkeypatch.setattr(
        graph_query,
        "match_documents",
        lambda q, v: _document_resolution(
            unique=graph_query.DocumentMatch(
                key="102/2024/ND CP", name="Nghị định 102/2024", matched_by="number"
            )
        ),
    )
    items = asyncio.run(ground_frame(_frame([("document", "Nghị định 102/2024")]), _resolution()))
    assert items[0].status == "resolved"
    assert items[0].code == "102/2024/ND CP"


def test_document_ambiguous(monkeypatch) -> None:
    async def fake_vocab():
        return graph_query.Vocabulary(run_id="test")

    monkeypatch.setattr(graph_query, "vocabulary", fake_vocab)
    monkeypatch.setattr(
        graph_query,
        "match_documents",
        lambda q, v: _document_resolution(
            candidates=[
                graph_query.DocumentMatch(key="A", name="Văn bản A", matched_by="name"),
                graph_query.DocumentMatch(key="B", name="Văn bản B", matched_by="name"),
            ]
        ),
    )
    items = asyncio.run(ground_frame(_frame([("document", "nghị định về đất đai")]), _resolution()))
    assert items[0].status == "ambiguous"
    assert len(items[0].alternatives) == 2


def test_agency_entity_resolved(monkeypatch) -> None:
    async def fake_vocab():
        return graph_query.Vocabulary(run_id="test")

    monkeypatch.setattr(graph_query, "vocabulary", fake_vocab)
    monkeypatch.setattr(
        graph_query,
        "match_entities",
        lambda q, v: (
            graph_query.EntityMatch(kind="co_quan", value="Bộ Y tế", label="Bộ Y tế"),
            [],
        ),
    )
    items = asyncio.run(ground_frame(_frame([("agency", "Bộ Y tế")]), _resolution()))
    assert items[0].status == "resolved"
    assert items[0].code == "Bộ Y tế"


def test_entity_of_wrong_kind_is_not_used(monkeypatch) -> None:
    async def fake_vocab():
        return graph_query.Vocabulary(run_id="test")

    monkeypatch.setattr(graph_query, "vocabulary", fake_vocab)
    monkeypatch.setattr(
        graph_query,
        "match_entities",
        lambda q, v: (
            graph_query.EntityMatch(kind="linh_vuc", value="Y tế", label="Y tế"),
            [],
        ),
    )
    items = asyncio.run(ground_frame(_frame([("agency", "Y tế")]), _resolution()))
    assert items[0].status == "not_found"


# ── adapter: clarify carries real options ─────────────────────────────────


def _parse_result(frame: QuestionFrame) -> ParseResult:
    return ParseResult(
        frame=frame, ms=10, tokens_in=100, tokens_out=50, model="test"
    )


def test_adapter_uses_grounded_options_for_clarify() -> None:
    frame = _frame([("procedure", "đổi sổ đỏ bị rách")], requests=[])
    result = _parse_result(frame)
    ambiguous = SubjectGrounding(
        index=0,
        status="ambiguous",
        type="procedure",
        mention="đổi sổ đỏ bị rách",
        alternatives=[
            {"code": "1.115345", "name": "Cấp đổi Giấy chứng nhận", "score": 0.66},
            {"code": "1.115350", "name": "Cấp lại Giấy chứng nhận", "score": 0.65},
        ],
    )
    decision = question_parser.to_router_decision(result, _resolution(), [ambiguous])
    assert decision.signal == "clarify"
    assert [option["value"] for option in decision.clarify["options"]] == [
        "1.115345",
        "1.115350",
    ]


def test_adapter_without_grounding_keeps_old_behaviour() -> None:
    frame = _frame([("procedure", "thủ tục 1.001699")], requests=[])
    decision = question_parser.to_router_decision(_parse_result(frame), _resolution())
    assert decision.signal != "clarify"


def test_adapter_ignores_subject_ambiguity_after_resolution() -> None:
    """Parser báo mơ hồ subject, nhưng grounding đã tìm ra mã — không được hỏi lại nữa."""
    frame = _frame([("procedure", "giấy xác nhận khuyết tật")], requests=[])
    frame["ambiguity"] = AmbiguityInfo(
        present=True, kind=AmbiguityKind.SUBJECT, reason="tên gọi có thể là thủ tục khác"
    )
    resolved = SubjectGrounding(
        index=0, status="resolved", type="procedure", mention="giấy xác nhận khuyết tật",
        code="1.001699", name="Cấp Giấy xác nhận khuyết tật", method="vector",
    )
    decision = question_parser.to_router_decision(
        _parse_result(frame), _resolution(), [resolved]
    )
    assert decision.signal != "clarify"


def test_adapter_ignores_ambiguous_mention_no_request_points_to() -> None:
    """Mention mơ hồ nhưng không ý nào trỏ tới (subject_ref=null) thì không được làm hỏi lại."""
    frame = _frame([("procedure", "một tên gì đó")], requests=[])
    frame["requests"] = [
        {
            "text": "danh sách thủ tục",
            "facet": Facet.GENERAL_INFO,
            "operation": RequestOperation.LIST,
            "subject_ref": None,
            "constraints": [],
        }
    ]
    unused = SubjectGrounding(
        index=0,
        status="ambiguous",
        type="procedure",
        mention="một tên gì đó",
        alternatives=[{"code": "1.1", "name": "A", "score": 0.5}],
    )
    decision = question_parser.to_router_decision(
        _parse_result(frame), _resolution(), [unused]
    )
    assert decision.signal != "clarify"


def test_adapter_uses_grounding_over_old_name_resolution() -> None:
    frame = _frame([("procedure", "giấy xác nhận khuyết tật")])
    grounded = SubjectGrounding(
        index=0,
        status="resolved",
        type="procedure",
        mention="giấy xác nhận khuyết tật",
        code="1.001699",
    )
    decision = question_parser.to_router_decision(
        _parse_result(frame), _resolution(ma="1.999999"), [grounded]
    )
    assert decision.subjects == ("1.001699",)


def test_adapter_does_not_retrieve_when_referenced_subject_is_not_found() -> None:
    frame = _frame([("procedure", "thủ tục không tồn tại")])
    missing = SubjectGrounding(
        index=0,
        status="not_found",
        type="procedure",
        mention="thủ tục không tồn tại",
    )
    decision = question_parser.to_router_decision(_parse_result(frame), _resolution(), [missing])
    assert decision.signal == "empty"
    assert decision.branch == ""


def test_adapter_does_not_merge_two_procedures_into_one_retrieval() -> None:
    frame = _frame(
        [("procedure", "thủ tục A"), ("procedure", "thủ tục B")],
        requests=[
            {
                "text": "hồ sơ A",
                "facet": Facet.REQUIRED_DOCUMENTS,
                "operation": RequestOperation.GET,
                "subject_ref": 0,
                "constraints": [],
            },
            {
                "text": "hồ sơ B",
                "facet": Facet.REQUIRED_DOCUMENTS,
                "operation": RequestOperation.GET,
                "subject_ref": 1,
                "constraints": [],
            },
        ],
    )
    items = [
        SubjectGrounding(index=0, status="resolved", type="procedure", mention="A", code="1.1"),
        SubjectGrounding(index=1, status="resolved", type="procedure", mention="B", code="1.2"),
    ]
    decision = question_parser.to_router_decision(_parse_result(frame), _resolution(), items)
    assert decision.signal == "empty"
    assert decision.branch == ""


# ── helpers ───────────────────────────────────────────────────────────────


def test_helpers_pick_the_right_items() -> None:
    items = [
        SubjectGrounding(index=0, status="not_found", type="procedure", mention="a"),
        SubjectGrounding(index=1, status="resolved", type="procedure", mention="b", code="1.1"),
        SubjectGrounding(
            index=2, status="ambiguous", type="procedure", mention="c", alternatives=[{"code": "x"}]
        ),
    ]
    assert grounding.resolved_procedure(items).code == "1.1"
    assert grounding.ambiguous_procedure(items).index == 2
    assert grounding.first_ambiguous(items).index == 2


def test_empty_frame_returns_empty() -> None:
    frame = _frame([])
    assert asyncio.run(ground_frame(frame, _resolution())) == []


def test_unresolved_subject_refs() -> None:
    frame = _frame(
        [("procedure", "a"), ("procedure", "b")],
        requests=[
            {
                "text": "x",
                "facet": Facet.FEE,
                "operation": RequestOperation.GET,
                "subject_ref": 0,
                "constraints": [],
            },
            {
                "text": "y",
                "facet": Facet.FEE,
                "operation": RequestOperation.GET,
                "subject_ref": 1,
                "constraints": [],
            },
        ],
    )
    items = [
        SubjectGrounding(index=0, status="resolved", type="procedure", mention="a", code="1.1"),
        SubjectGrounding(index=1, status="ambiguous", type="procedure", mention="b"),
    ]
    assert grounding.unresolved_subject_refs(frame, items) == [1]
