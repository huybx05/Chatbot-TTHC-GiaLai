"""Giai đoạn 0 — hợp đồng hai lớp: giả thuyết (discovery) và bằng chứng đã kiểm.

Mục tiêu của bộ test này là chặn đúng lỗi đã đo được: một kết quả tìm kiếm gần nghĩa bị dùng
như bằng chứng của thủ tục sai. Không có mô hình nào chạy ở đây.
"""

from __future__ import annotations

import asyncio

from backend.app.rag import contracts, evidence
from backend.app.rag.types import Candidate
from backend.app.workflow import answer, executor
from backend.app.workflow.planner import Plan, Task
from backend.app.workflow.state import new_state


class _Grounding:
    def __init__(self, **kwargs) -> None:
        self.status = kwargs.get("status", "resolved")
        self.type = kwargs.get("type", "procedure")
        self.mention = kwargs.get("mention", "thủ tục X")
        self.code = kwargs.get("code", "")
        self.name = kwargs.get("name", "")
        self.method = kwargs.get("method", "vector")
        self.score = kwargs.get("score", 0.0)
        self.alternatives = kwargs.get("alternatives", [])


# ── ứng viên, không phải bằng chứng ──────────────────────────────────────


def test_resolved_grounding_becomes_one_discovery_candidate() -> None:
    candidates = contracts.from_groundings(
        [_Grounding(status="resolved", code="1.115362", name="Đăng ký biến động", score=0.9)]
    )
    assert len(candidates) == 1
    assert candidates[0].value == "1.115362"
    assert candidates[0].to_dict()["result_kind"] == "discovery"


def test_ambiguous_grounding_keeps_all_alternatives() -> None:
    candidates = contracts.from_groundings(
        [
            _Grounding(
                status="ambiguous",
                alternatives=[
                    {"code": "1.115362", "name": "A", "score": 0.84},
                    {"code": "1.115366", "name": "B", "score": 0.83},
                ],
            )
        ]
    )
    assert [c.value for c in candidates] == ["1.115362", "1.115366"]
    assert all(c.reason.startswith("alternative:") for c in candidates)


def test_unresolved_grounding_records_the_mention() -> None:
    candidates = contracts.from_groundings(
        [_Grounding(status="not_found", mention="chuyển nhượng hoặc tặng cho")]
    )
    assert candidates[0].value == "chuyển nhượng hoặc tặng cho"
    assert candidates[0].reason == "unresolved"


def test_resolution_is_used_when_no_grounding() -> None:
    class _Resolution:
        code = "1.001699"
        name = "Cấp GXN"
        confidence = 0.8
        alternatives = [("1.000001", "Khác", 0.7)]

    candidates = contracts.from_groundings([], _Resolution())
    assert {c.value for c in candidates} == {"1.001699", "1.000001"}


def test_candidate_objects_are_never_evidence() -> None:
    assert contracts.is_discovery_object({"kind": "candidate"})
    assert not contracts.is_discovery_object({"kind": "section"})


# ── bằng chứng: converter đánh dấu đúng lớp ─────────────────────────────


def test_section_evidence_is_verified() -> None:
    items = evidence.from_sections(
        [
            {
                "procedure_code": "1.115362",
                "procedure_name": "X",
                "section_type": "FEE",
                "title": "Phí",
                "content": "Miễn phí",
            }
        ]
    )
    assert items[0]["verified"] is True
    assert items[0]["result_kind"] == "verified_evidence"


def test_chunk_evidence_starts_as_discovery() -> None:
    items = evidence.from_chunks(
        [
            Candidate(
                chunk_id="c1",
                procedure_code="1.115362",
                procedure_name="X",
                section_type="FEE",
                title="Phí",
                content="Miễn phí",
                detail_url="https://example.test/1",
            )
        ]
    )
    assert items[0]["verified"] is False
    assert items[0]["result_kind"] == "discovery"


def test_mark_verified_upgrades_and_verified_only_filters() -> None:
    items = [{"kind": "chunk", "content": "x"}]
    upgraded = contracts.mark_verified(items, "hybrid_with_verified_code")
    assert upgraded[0]["verified"] is True
    assert contracts.verified_only([*upgraded, {"kind": "chunk"}]) == upgraded


# ── ngữ cảnh trả lời tuyệt đối không nhận ứng viên ──────────────────────


def test_answer_context_skips_candidate_objects() -> None:
    text, _ = answer.build_context(
        [
            {"kind": "candidate", "content": "1.115362 — ứng viên"},
            {
                "kind": "section",
                "content": "Hồ sơ gồm đơn đề nghị",
                "procedure_code": "1.115362",
            },
        ]
    )
    assert "ứng viên" not in text
    assert "đơn đề nghị" in text


# ── executor nâng chunk lên verified khi có mã đã xác thực ───────────────


def _fake_hybrid(candidates: list[dict]) -> None:
    async def fake(question, *, vector, codes=None, use_gate=True):
        return type("KQ", (), {"candidates": [], "errors": []})()

    return fake


def test_hybrid_with_code_is_marked_verified(monkeypatch) -> None:
    monkeypatch.setattr(executor.hybrid, "hybrid", _fake_hybrid([]))
    monkeypatch.setattr(
        executor,
        "from_chunks",
        lambda _c: [{"kind": "chunk", "section_type": "FEE", "content": "Miễn phí"}],
    )

    task = Task(
        request_index=0,
        tool="hybrid",
        facet="fee",
        operation="get",
        procedure_codes=("1.115362",),
    )
    result = asyncio.run(executor._run_hybrid(task, "phí?", _FakeVector()))  # noqa: SLF001
    assert result.items[0]["verified"] is True


def test_hybrid_without_code_stays_discovery(monkeypatch) -> None:
    monkeypatch.setattr(executor.hybrid, "hybrid", _fake_hybrid([]))
    monkeypatch.setattr(
        executor,
        "from_chunks",
        lambda _c: [{"kind": "chunk", "section_type": "FEE", "content": "Miễn phí"}],
    )

    task = Task(
        request_index=0,
        tool="hybrid",
        facet="fee",
        operation="get",
        procedure_codes=(),
    )
    result = asyncio.run(executor._run_hybrid(task, "phí?", _FakeVector()))  # noqa: SLF001
    assert result.items[0].get("verified") is not True


class _FakeVector:
    async def get(self) -> list[float]:
        return [0.1]


# ── trạng thái và trace ─────────────────────────────────────────────────


def test_state_has_discovery_slot() -> None:
    assert new_state("câu hỏi")["discovery"] == []


def test_plan_is_not_evidence() -> None:
    """Plan chỉ là kế hoạch; không có mục nào được đánh dấu verified khi chưa chạy."""
    plan = Plan(tasks=[])
    assert plan.to_dict()["tasks"] == []
