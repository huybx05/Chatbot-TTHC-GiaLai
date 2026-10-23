"""Phase 5 tests — task execution, coverage and fallback.

Tool functions are replaced with fakes, so these tests are deterministic and do not touch
PostgreSQL, Neo4j or the model.
"""

from __future__ import annotations

import asyncio

from backend.app.workflow import executor, graph
from backend.app.workflow.planner import Plan, Task


def _state(question: str = "câu hỏi") -> dict:
    return {
        "question": question,
        "vector_hash": "",
        "fallback_from": [],
    }


def _task(index: int, tool: str, facet: str, *, codes: tuple[str, ...] = ("1.001699",)) -> Task:
    return Task(
        request_index=index,
        tool=tool,
        facet=facet,
        operation="get",
        intent="",
        procedure_codes=codes,
    )


def _evidence(index: int) -> dict:
    return {"kind": "section", "title": "Hồ sơ", "content": f"nội dung {index}"}


# ── coverage ───────────────────────────────────────────────────────────────


def test_covered_tasks_run_in_parallel_and_keep_user_order(monkeypatch) -> None:
    async def fake_section(task):
        return executor.ToolResult([_evidence(task.request_index)])

    async def fake_graph(task, question, vector_source):
        return executor.ToolResult([_evidence(task.request_index)])

    monkeypatch.setattr(executor, "_run_section", fake_section)
    monkeypatch.setattr(executor, "_run_graph", fake_graph)

    plan = Plan(
        tasks=[
            _task(1, "graph", "implementing_agency"),
            _task(0, "section_lookup", "required_documents"),
        ]
    )
    execution = asyncio.run(executor.execute_plan(_state(), plan))

    assert [item["request_index"] for item in execution.evidence] == [0, 1]
    assert [item.status for item in execution.coverage] == ["covered", "covered"]
    assert execution.covered == 2


def test_empty_section_falls_back_to_hybrid(monkeypatch) -> None:
    goi = {"hybrid": 0}

    async def fake_section(task):
        return executor.ToolResult([])

    async def fake_hybrid(task, question, vector_source):
        goi["hybrid"] += 1
        return executor.ToolResult([_evidence(task.request_index)])

    monkeypatch.setattr(executor, "_run_section", fake_section)
    monkeypatch.setattr(executor, "_run_hybrid", fake_hybrid)

    plan = Plan(tasks=[_task(0, "section_lookup", "required_documents")])
    execution = asyncio.run(executor.execute_plan(_state(), plan))

    assert goi["hybrid"] == 1
    coverage = execution.coverage[0]
    assert coverage.status == "covered"
    assert coverage.fallback_from == "section_lookup"
    assert coverage.fallback_to == "hybrid"
    assert execution.fallbacks == [(0, "section_lookup", "hybrid")]


def test_fallback_runs_at_most_once(monkeypatch) -> None:
    goi = {"hybrid": 0}

    async def fake_section(task):
        return executor.ToolResult([])

    async def fake_hybrid(task, question, vector_source):
        goi["hybrid"] += 1
        return executor.ToolResult([])

    monkeypatch.setattr(executor, "_run_section", fake_section)
    monkeypatch.setattr(executor, "_run_hybrid", fake_hybrid)

    execution = asyncio.run(
        executor.execute_plan(_state(), Plan(tasks=[_task(0, "section_lookup", "fee")]))
    )
    assert goi["hybrid"] == 1
    assert execution.coverage[0].status == "empty"


def test_failed_tool_is_reported_per_request(monkeypatch) -> None:
    async def fake_section(task):
        if task.request_index == 1:
            raise RuntimeError("PostgreSQL sập")
        return executor.ToolResult([_evidence(task.request_index)])

    monkeypatch.setattr(executor, "_run_section", fake_section)
    monkeypatch.setattr(
        executor, "_run_hybrid", lambda task, q, v: asyncio.sleep(0, result=executor.ToolResult([]))
    )

    plan = Plan(
        tasks=[
            _task(0, "section_lookup", "required_documents"),
            _task(1, "section_lookup", "processing_time"),
        ]
    )
    execution = asyncio.run(executor.execute_plan(_state(), plan))

    assert execution.coverage[0].status == "covered"
    assert execution.coverage[1].status == "failed"
    assert execution.failed_all is False


def test_all_failed_flag() -> None:
    coverage = [
        executor.RequestCoverage(request_index=0, status="failed"),
        executor.RequestCoverage(request_index=1, status="failed"),
    ]
    execution = executor.Execution(coverage=coverage)
    assert execution.failed_all is True


def test_unsupported_requests_get_coverage(monkeypatch) -> None:
    async def fake_section(task):
        return executor.ToolResult([_evidence(task.request_index)])

    monkeypatch.setattr(executor, "_run_section", fake_section)
    plan = Plan(
        tasks=[_task(0, "section_lookup", "fee")],
        unsupported=[{"request_index": 1, "reason": "UNSUPPORTED_OPERATION", "facet": "fee"}],
    )
    execution = asyncio.run(executor.execute_plan(_state(), plan))

    statuses = {item.request_index: item.status for item in execution.coverage}
    assert statuses == {0: "covered", 1: "unsupported"}


# ── outcome mapping in node_thuc_thi ───────────────────────────────────────


def _patch_execution(monkeypatch, execution: executor.Execution) -> None:
    async def fake(state, plan):
        return execution

    monkeypatch.setattr(executor, "execute_plan", fake)


def _plan_with_tasks() -> Plan:
    return Plan(tasks=[_task(0, "section_lookup", "fee")])


def test_partial_coverage_answers_and_lists_missing_facets(monkeypatch) -> None:
    _patch_execution(
        monkeypatch,
        executor.Execution(
            evidence=[_evidence(0)],
            coverage=[
                executor.RequestCoverage(0, "covered", facet="fee"),
                executor.RequestCoverage(1, "empty", facet="processing_time"),
            ],
        ),
    )
    monkeypatch.setattr(
        graph, "_plan_from_state", lambda state: _plan_with_tasks()
    )
    patch = asyncio.run(graph.node_thuc_thi(_state()))
    assert patch["outcome"] == "answered"
    assert patch["thieu"] == ["processing_time"]


def test_all_empty_abstains_with_insufficient_evidence(monkeypatch) -> None:
    _patch_execution(
        monkeypatch,
        executor.Execution(coverage=[executor.RequestCoverage(0, "empty", facet="fee")]),
    )
    monkeypatch.setattr(graph, "_plan_from_state", lambda state: _plan_with_tasks())
    patch = asyncio.run(graph.node_thuc_thi(_state()))
    assert patch["outcome"] == "abstained"
    assert patch["refusal"]


def test_all_failed_abstains_with_tool_unavailable(monkeypatch) -> None:
    _patch_execution(
        monkeypatch,
        executor.Execution(coverage=[executor.RequestCoverage(0, "failed", facet="fee")]),
    )
    monkeypatch.setattr(graph, "_plan_from_state", lambda state: _plan_with_tasks())
    patch = asyncio.run(graph.node_thuc_thi(_state()))
    assert patch["outcome"] == "abstained"
    assert "lỗi" in patch["refusal"].lower()


def test_unsupported_operation_abstains(monkeypatch) -> None:
    _patch_execution(
        monkeypatch,
        executor.Execution(
            coverage=[executor.RequestCoverage(0, "unsupported", facet="fee")]
        ),
    )
    monkeypatch.setattr(
        graph,
        "_plan_from_state",
        lambda state: Plan(
            unsupported=[{"request_index": 0, "reason": "UNSUPPORTED_OPERATION"}]
        ),
    )
    patch = asyncio.run(graph.node_thuc_thi(_state()))
    assert patch["outcome"] == "abstained"
    assert "so sánh" in patch["refusal"].lower() or "xếp hạng" in patch["refusal"].lower()


def test_clarify_reason_leads_to_clarify(monkeypatch) -> None:
    _patch_execution(
        monkeypatch,
        executor.Execution(
            coverage=[executor.RequestCoverage(0, "unsupported", facet="fee")]
        ),
    )
    monkeypatch.setattr(
        graph,
        "_plan_from_state",
        lambda state: Plan(
            unsupported=[{"request_index": 0, "reason": "AMBIGUOUS_SUBJECT"}]
        ),
    )
    patch = asyncio.run(graph.node_thuc_thi(_state()))
    assert patch["outcome"] == "clarify"


# ── các lỗi của giai đoạn 5 (mentor review) ───────────────────────────────


def test_hybrid_filters_by_facet() -> None:
    items = [
        {"section_type": "GENERAL_INFO", "content": "chung"},
        {"section_type": "REQUIRED_DOCUMENTS", "content": "hồ sơ"},
        {"section_type": "FEE", "content": "phí"},
    ]
    kept = executor.filter_by_facet(items, "required_documents")
    assert [item["section_type"] for item in kept] == ["REQUIRED_DOCUMENTS"]


def test_hybrid_wrong_facet_means_empty(monkeypatch) -> None:
    async def fake_hybrid(question, *, vector, codes=None, use_gate=True):
        return type(
            "KQ", (), {"candidates": []}
        )()

    # Không cần Candidate thật: hàm lọc chỉ chạy trên evidence sau khi from_chunks.
    import backend.app.workflow.executor as ex

    monkeypatch.setattr(ex, "from_chunks", lambda candidates: [{"section_type": "GENERAL_INFO"}])
    monkeypatch.setattr(ex.hybrid, "hybrid", fake_hybrid)

    result = asyncio.run(
        ex._run_hybrid(  # noqa: SLF001
            _task(0, "hybrid", "required_documents"), "câu", _FakeVector()
        )
    )
    assert result.items == []


class _FakeVector:
    async def get(self) -> list[float]:
        return [0.1]


def test_graph_clarify_becomes_outcome_clarify(monkeypatch) -> None:
    _patch_execution(
        monkeypatch,
        executor.Execution(
            coverage=[executor.RequestCoverage(0, "ambiguous", facet="legal_basis")],
            clarifies=[
                (
                    0,
                    {
                        "question": "Bạn muốn hỏi văn bản nào?",
                        "options": [{"value": "A", "label": "Văn bản A"}],
                    },
                )
            ],
        ),
    )
    monkeypatch.setattr(graph, "_plan_from_state", lambda state: _plan_with_tasks())
    patch = asyncio.run(graph.node_thuc_thi(_state()))
    assert patch["outcome"] == "clarify"
    assert patch["clarify"]["options"][0]["value"] == "A"


def test_router_sends_unsupported_only_plan_to_executor() -> None:
    state = {
        "branch": "hybrid",
        "plan": {
            "tasks": [],
            "unsupported": [{"request_index": 0, "reason": "UNSUPPORTED_CONSTRAINT"}],
        },
    }
    assert graph.sau_khi_router(state) == graph.THUC_THI


def test_router_keeps_old_branch_when_no_plan() -> None:
    state = {"branch": "hybrid", "plan": {}, "vector_hash": "x"}
    assert graph.sau_khi_router(state) == "hybrid"


def test_executor_passes_intent_to_graph(monkeypatch) -> None:
    captured: dict = {}

    async def fake_answer(question, **kwargs):
        captured.update(kwargs)
        return type(
            "EV",
            (),
            {
                "clarify": False,
                "rows": [{"vai_tro": "BAN_HANH_BOI", "gia_tri": "UBND"}],
                "parts": [],
                "intent": "AGENCY",
                "title": "Cơ quan",
                "subject": "",
                "total": 1,
                "truncated": False,
                "template": "AGENCY",
                "columns": (),
                "empty": "",
                "note": "",
            },
        )()

    monkeypatch.setattr(executor.graph_query, "answer", fake_answer)
    monkeypatch.setattr(executor, "from_graph", lambda ev: [{"kind": "graph"}])

    task = Task(
        request_index=0,
        tool="graph",
        facet="issuing_agency",
        operation="get",
        intent="AGENCY",
        expected_types=("BAN_HANH_BOI",),
        procedure_codes=("1.001699",),
    )
    asyncio.run(executor._run_graph(task, "câu", _FakeVector()))  # noqa: SLF001
    assert captured["intent"] == "AGENCY"
    assert captured["expected_types"] == ("BAN_HANH_BOI",)


# ── lỗi hạ tầng không được thành "không có dữ liệu" ──────────────────────


def test_section_db_error_is_failed(monkeypatch) -> None:
    async def fake_checked(codes, needs):
        return [], "OperationalError: connection refused"

    monkeypatch.setattr(executor.sections, "theo_khia_canh_checked", fake_checked)
    monkeypatch.setattr(executor, "_run_hybrid", lambda task, q, v: _empty())

    execution = asyncio.run(
        executor.execute_plan(_state(), Plan(tasks=[_task(0, "section_lookup", "fee")]))
    )
    coverage = execution.coverage[0]
    assert coverage.status == "failed"
    assert "connection refused" in coverage.note


async def _empty() -> executor.ToolResult:
    return executor.ToolResult([])


def test_fact_db_error_is_failed(monkeypatch) -> None:
    async def fake_checked(codes):
        return [], "OperationalError: timeout"

    monkeypatch.setattr(executor.fact_lookup, "get_facts_checked", fake_checked)

    execution = asyncio.run(
        executor.execute_plan(_state(), Plan(tasks=[_task(0, "fact_lookup", "general_info")]))
    )
    assert execution.coverage[0].status == "failed"


def test_graph_infra_error_is_failed(monkeypatch) -> None:
    async def fake_answer(question, **kwargs):
        return type(
            "EV",
            (),
            {
                "clarify": False,
                "rows": [],
                "parts": [],
                "note": "Không kết nối được Neo4j",
                "failed": True,
            },
        )()

    monkeypatch.setattr(executor.graph_query, "answer", fake_answer)
    execution = asyncio.run(
        executor.execute_plan(_state(), Plan(tasks=[_task(0, "graph", "field")]))
    )
    coverage = execution.coverage[0]
    assert coverage.status == "failed"
    assert "Neo4j" in coverage.note


def test_hybrid_branch_errors_are_failed(monkeypatch) -> None:
    async def fake_hybrid(question, *, vector, codes=None, use_gate=True):
        return type(
            "KQ",
            (),
            {
                "candidates": [],
                "errors": ["Elasticsearch: ConnectionError", "Qdrant: ConnectionError"],
            },
        )()

    monkeypatch.setattr(executor.hybrid, "hybrid", fake_hybrid)
    execution = asyncio.run(
        executor.execute_plan(_state(), Plan(tasks=[_task(0, "hybrid", "fee", codes=())]))
    )
    coverage = execution.coverage[0]
    assert coverage.status == "failed"
    assert "Elasticsearch" in coverage.note


# ── constraint không ground được: không được bỏ im lặng ──────────────────


def test_constraint_without_vocabulary_is_unsupported(monkeypatch) -> None:
    async def hong():
        raise RuntimeError("Neo4j down")

    monkeypatch.setattr(executor.graph_query, "vocabulary", hong)
    task = _task(0, "graph", "field", codes=())
    task.constraints = ({"type": "field", "text": "Y tế"},)
    result = asyncio.run(executor._run_graph(task, "câu", _FakeVector()))  # noqa: SLF001
    assert result.status == "unsupported"
    assert "từ điển" in result.error


def test_constraint_value_not_found_is_unsupported(monkeypatch) -> None:
    async def empty_vocab():
        return type("V", (), {"cap": (), "linh_vuc": (), "co_quan": ()})()

    monkeypatch.setattr(executor.graph_query, "vocabulary", empty_vocab)
    def no_match(text, vocabulary):
        return None, []

    monkeypatch.setattr(executor.graph_query, "match_entities", no_match)
    task = _task(0, "graph", "field", codes=())
    task.constraints = ({"type": "field", "text": "Không tồn tại"},)
    result = asyncio.run(executor._run_graph(task, "câu", _FakeVector()))  # noqa: SLF001
    assert result.status == "unsupported"


# ── vector single-flight ─────────────────────────────────────────────────


def test_vector_source_embeds_once(monkeypatch) -> None:
    dem = {"n": 0}

    async def fake_embed(_question):
        dem["n"] += 1
        await asyncio.sleep(0.01)
        return [0.1]

    monkeypatch.setattr(executor.embeddings, "embed", fake_embed)
    nguon = executor._VectorSource({"question": "x", "vector_hash": ""})  # noqa: SLF001

    async def hai_lan():
        return await asyncio.gather(nguon.get(), nguon.get())

    a, b = asyncio.run(hai_lan())
    assert dem["n"] == 1
    assert a == b == [0.1]
