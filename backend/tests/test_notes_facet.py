"""Facet 'notes' chỉ trả phần Lưu ý của hồ sơ."""

from __future__ import annotations

import json

from backend.app.workflow import executor
from backend.app.workflow.case_resolver import select_case
from backend.app.workflow.planner import Task, plan_retrieval
from backend.app.workflow.question_frame import Facet
from backend.app.workflow.question_parser import parse_frame


def _frame(facet: str) -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "scope": "tthc",
            "subject_mentions": [{"type": "procedure", "text": "thủ tục 1.004873"}],
            "requests": [
                {
                    "text": "lưu ý của thủ tục này",
                    "facet": facet,
                    "operation": "get",
                    "subject_ref": 0,
                    "constraints": [],
                }
            ],
            "ambiguity": {"present": False, "kind": "none", "reason": ""},
        },
        ensure_ascii=False,
    )


def test_facet_notes_ton_tai_va_parse_duoc() -> None:
    assert Facet.NOTES.value == "notes"
    frame = parse_frame(_frame("notes"))
    assert frame["requests"][0]["facet"] is Facet.NOTES


def test_planner_notes_dung_section_lookup() -> None:
    from backend.app.rag.grounding import SubjectGrounding

    frame = parse_frame(_frame("notes"))
    plan = plan_retrieval(
        frame,
        [
            SubjectGrounding(
                index=0,
                status="resolved",
                type="procedure",
                mention="1.004873",
                code="1.004873",
            )
        ],
    )

    assert not plan.unsupported
    assert plan.tasks[0].tool == "section_lookup"
    assert plan.tasks[0].facet == "notes"


def test_select_case_luu_y() -> None:
    rows = [
        {"metadata": {"case_order": 1, "case_name": "* Giấy tờ phải nộp:"}},
        {"metadata": {"case_order": 2, "case_name": "* Giấy tờ phải xuất trình:"}},
        {"metadata": {"case_order": 3, "case_name": "* Lưu ý:"}},
    ]

    case = select_case("Lưu ý của thủ tục này là gì?", rows)

    assert case is not None
    assert case["case_order"] == 3


def test_run_section_notes_chi_tra_case_luu_y(monkeypatch) -> None:
    import asyncio

    rows = [
        {
            "procedure_code": "1.004873",
            "procedure_name": "Thủ tục cấp Giấy xác nhận tình trạng hôn nhân",
            "section_type": "REQUIRED_DOCUMENTS",
            "title": "Hồ sơ",
            "content": f"nội dung {case}",
            "detail_url": "https://example.test",
            "metadata": {"case_order": case, "case_name": name},
        }
        for case, name in (
            (1, "* Giấy tờ phải nộp:"),
            (2, "* Giấy tờ phải xuất trình:"),
            (3, "* Lưu ý:"),
        )
    ]

    async def fake_section(_codes, _sections):
        return rows, ""

    monkeypatch.setattr(executor.sections, "theo_khia_canh_checked", fake_section)
    task = Task(
        request_index=0,
        tool="section_lookup",
        facet="notes",
        operation="get",
        procedure_codes=("1.004873",),
    )

    result = asyncio.run(executor._run_section(task, "Lưu ý của thủ tục này là gì?"))

    assert [item["metadata"]["case_order"] for item in result.items] == [3]
