"""Giai đoạn 4 — nối gỡ rối và fallback loại mention vào grounding."""

from __future__ import annotations

import asyncio

from backend.app.rag import disambiguation, grounding
from backend.app.rag.resolve import Resolution


def _frame() -> dict:
    return {
        "schema_version": "1.0",
        "scope": "tthc",
        "subject_mentions": [{"type": "procedure", "text": "đăng ký biến động đất đai"}],
        "requests": [
            {
                "text": "mất bao lâu",
                "facet": "processing_time",
                "operation": "get",
                "subject_ref": 0,
                "scenario": "cho thuê lại trong dự án",
                "constraints": [],
            }
        ],
        "ambiguity": {"present": False, "kind": "none", "reason": ""},
    }


def test_apply_disambiguation_ghi_de_ket_qua_resolved(monkeypatch) -> None:
    async def fake_rerank(*_args, **_kwargs):
        return disambiguation.DisambiguationDecision(
            code="1.115362",
            name="Đăng ký biến động",
            score=0.98,
            coverage=1.0,
            reason="case_condition",
            note="tình huống khớp",
        )

    monkeypatch.setattr(grounding.disambiguation, "rerank", fake_rerank)
    item = grounding.SubjectGrounding(
        index=0,
        status="resolved",
        type="procedure",
        mention="đăng ký biến động",
        code="1.115351",
        name="Xóa đăng ký thuê",
        candidates=[
            {"code": "1.115351", "name": "Xóa", "score": 0.81},
            {"code": "1.115362", "name": "Đăng ký", "score": 0.73},
        ],
    )
    asyncio.run(grounding._apply_disambiguation([item], _frame(), "câu hỏi"))  # noqa: SLF001
    assert item.status == "resolved"
    assert item.code == "1.115362"
    assert item.method == "disambiguation"


def test_mention_document_khong_khop_thi_thu_lai_nhu_thu_tuc(monkeypatch) -> None:
    def fake_document(*_args, **_kwargs):
        return grounding.SubjectGrounding(
            index=0, status="not_found", type="document", mention="Đơn đăng ký biến động"
        )

    async def fake_procedure(index, text, *_args):
        return grounding.SubjectGrounding(
            index=index,
            status="resolved",
            type="procedure",
            mention=text,
            code="1.115362",
            name="Đăng ký biến động",
        )

    async def noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(grounding, "_ground_document", fake_document)
    monkeypatch.setattr(grounding, "_ground_procedure", fake_procedure)
    monkeypatch.setattr(grounding, "_apply_disambiguation", noop)
    monkeypatch.setattr(grounding, "_apply_theme_agreement", noop)

    frame = {
        "schema_version": "1.0",
        "scope": "tthc",
        "subject_mentions": [{"type": "document", "text": "Đơn đăng ký biến động"}],
        "requests": [],
        "ambiguity": {"present": False, "kind": "none", "reason": ""},
    }
    items = asyncio.run(grounding.ground_frame(frame, Resolution(question="câu")))
    assert len(items) == 1
    assert items[0].type == "procedure"
    assert items[0].code == "1.115362"
