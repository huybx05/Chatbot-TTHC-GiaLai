from __future__ import annotations

import asyncio

import pytest
from backend.app.memory.resolver import apply_memory_antecedent
from backend.app.rag.resolve import Resolution
from backend.app.workflow import graph
from backend.app.workflow.question_frame import (
    AmbiguityKind,
    Facet,
    QuestionScope,
    RequestOperation,
    SubjectType,
)
from backend.app.workflow.state import new_state


def test_node_router_gan_resolution_khi_codes_da_co(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_chon_nhanh(*_args, **_kwargs):
        return (
            graph.RouterDecision(branch="executor", reason="plan: 1/1 ý có dữ liệu"),
            "",
            None,
            [
                graph.grounding.SubjectGrounding(
                    index=0,
                    status="resolved",
                    type="procedure",
                    mention="Thủ tục A",
                    code="1.001699",
                    name="Thủ tục A",
                    method="exact_name",
                    score=1.0,
                )
            ],
            1,
        )

    monkeypatch.setattr(graph, "_chon_nhanh", fake_chon_nhanh)

    state = new_state("Thủ tục 1.001699 cần gì?")
    state["codes"] = ["1.001699"]
    state["resolution"] = {"code": "", "name": ""}

    patch = asyncio.run(graph.node_router(state))

    assert patch["resolution"]["code"] == "1.001699"
    assert patch["resolution"]["name"] == "Thủ tục A"
    assert patch["resolution"]["method"] == "grounding:exact_name"
    assert patch["grounded_procedure"]["code"] == "1.001699"
    assert patch["candidate_procedures"][0]["code"] == "1.001699"


def test_node_ket_thuc_tao_answered_procedure_khi_co_evidence() -> None:
    state = new_state("Thủ tục 1.001699 cần gì?")
    state["branch_signal"] = "ok"
    state["evidence"] = [{"kind": "section", "procedure_code": "1.001699"}]
    state["resolution"] = {"code": "1.001699", "name": "Thủ tục A"}
    state["grounded_procedure"] = {
        "code": "1.001699",
        "name": "Thủ tục A",
        "source": "grounding",
    }

    patch = asyncio.run(graph.node_ket_thuc(state))

    assert patch["outcome"] == "answered"
    assert patch["answered_procedure"]["code"] == "1.001699"
    assert patch["answered_procedure"]["source"] == "grounded"


def test_sau_khi_router_tu_choi_khi_signal_empty() -> None:
    state = new_state("Tôi làm rơi chứng chỉ, xin lại thủ tục nào?")
    state["branch"] = ""
    state["branch_signal"] = "empty"
    state["plan"] = {
        "tasks": [
            {
                "request_index": 0,
                "facet": "general_info",
                "operation": "get",
                "procedure_codes": ["1.014100"],
            }
        ],
        "unsupported": [],
    }

    assert graph.sau_khi_router(state) == graph.TU_CHOI


def test_node_dinh_danh_gan_thu_tuc_tu_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_embed(_question: str) -> list[float]:
        return [0.1, 0.2]

    async def fake_resolve(_question: str, **_kwargs) -> Resolution:
        return Resolution(question="Thủ tục này cần gì?", needs_antecedent=True)

    monkeypatch.setattr(graph.embeddings, "embed", fake_embed)
    monkeypatch.setattr(graph.resolve, "remember_vector", lambda _vector: "hash")
    monkeypatch.setattr(graph.resolve, "resolve", fake_resolve)

    state = new_state("Thủ tục này cần gì?")
    state["memory"] = {
        "active_procedure": {
            "code": "1.001699",
            "name": "Thủ tục A",
        }
    }

    patch = asyncio.run(graph.node_dinh_danh(state))

    assert patch["codes"] == ["1.001699"]
    assert patch["needs_antecedent"] is False
    assert patch["resolution"]["code"] == "1.001699"
    assert patch["resolution"]["name"] == "Thủ tục A"
    assert patch["resolution"]["method"] == "memory"


def test_followup_hai_y_giu_ma_memory_thay_vi_candidate_vector(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = {
        "active_procedure": {
            "code": "1.001699",
            "name": "Xác định mức độ khuyết tật",
        }
    }
    resolution = Resolution(
        question="Lệ phí và thời hạn của thủ tục này là bao nhiêu?",
        needs_antecedent=True,
    )
    assert apply_memory_antecedent(resolution, memory)
    frame = {
        "schema_version": "1.0",
        "scope": QuestionScope.TTHC,
        "subject_mentions": [
            {"type": SubjectType.PROCEDURE, "text": "thủ tục này"}
        ],
        "requests": [
            {
                "text": "lệ phí",
                "facet": Facet.FEE,
                "operation": RequestOperation.GET,
                "subject_ref": 0,
                "constraints": [],
                "scenario": "",
            },
            {
                "text": "thời hạn",
                "facet": Facet.PROCESSING_TIME,
                "operation": RequestOperation.GET,
                "subject_ref": 0,
                "constraints": [],
                "scenario": "",
            },
        ],
        "ambiguity": {
            "present": False,
            "kind": AmbiguityKind.NONE,
            "reason": "",
        },
    }

    async def fake_parse(*_args, **_kwargs):
        return graph.question_parser.ParseResult(frame=frame)

    async def fake_ground(*_args, **_kwargs):
        return [
            graph.grounding.SubjectGrounding(
                index=0,
                status="ambiguous",
                type="procedure",
                mention="thủ tục này",
                method="vector",
                score=0.615,
                alternatives=[
                    {"code": "1.115345", "name": "Cấp đổi giấy chứng nhận"},
                    {"code": "1.115368", "name": "Đăng ký biến động đất đai"},
                ],
            )
        ]

    monkeypatch.setattr(graph.question_parser, "parse_question", fake_parse)
    monkeypatch.setattr(graph.question_parser, "enabled", lambda: True)
    monkeypatch.setattr(graph.grounding, "ground_frame", fake_ground)

    decision, _, parsed_frame, groundings, _ = asyncio.run(
        graph._chon_nhanh(
            resolution.question,
            resolution,
            memory=memory,
        )
    )

    assert decision.signal != "clarify"
    assert parsed_frame is frame
    assert groundings[0].status == "resolved"
    assert groundings[0].code == "1.001699"
    assert groundings[0].method == "memory"
