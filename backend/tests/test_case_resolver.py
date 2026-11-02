from __future__ import annotations

import asyncio

from backend.app.workflow import executor
from backend.app.workflow.case_resolver import filter_items, select_case
from backend.app.workflow.planner import Task


def _items() -> list[dict]:
    return [
        {
            "content": "case 1",
            "metadata": {"case_order": 1, "case_name": "(1.1) Công trình theo tuyến"},
        },
        {
            "content": "case 2",
            "metadata": {"case_order": 2, "case_name": "(1.2) Công trình tôn giáo"},
        },
        {
            "content": "case 3",
            "metadata": {"case_order": 3, "case_name": "(1.3) Công trình tín ngưỡng"},
        },
        {
            "content": "case 4",
            "metadata": {"case_order": 4, "case_name": "(1.4) Công trình tượng đài"},
        },
    ]


def test_case_resolver_chon_theo_ngon_ngu() -> None:
    case = select_case("Công trình tôn giáo cần hồ sơ gì?", _items())
    assert case is not None
    assert case["case_order"] == 2


def test_case_resolver_tuong_dai() -> None:
    case = select_case("Tượng đài cần hồ sơ gì?", _items())
    assert case is not None
    assert case["case_order"] == 4


def test_case_resolver_hoi_chung_tra_tat_ca() -> None:
    assert select_case("Hồ sơ cần có những gì?", _items()) is None


def test_filter_items_theo_case() -> None:
    items = filter_items(_items(), {"case_order": 2, "case_name": "..."})
    assert [item["content"] for item in items] == ["case 2"]


def test_run_section_loc_case(monkeypatch) -> None:
    rows = [
        {
            "procedure_code": "1.013225",
            "procedure_name": "Cấp phép xây dựng",
            "section_type": "REQUIRED_DOCUMENTS",
            "title": "Hồ sơ",
            "content": item["content"],
            "detail_url": "https://example.test",
            "metadata": item["metadata"],
        }
        for item in _items()
    ]

    async def fake_section(_codes, _sections):
        return rows, ""

    monkeypatch.setattr(executor.sections, "theo_khia_canh_checked", fake_section)
    task = Task(
        request_index=0,
        tool="section_lookup",
        facet="required_documents",
        operation="get",
        procedure_codes=("1.013225",),
    )
    result = asyncio.run(executor._run_section(task, "Công trình tôn giáo cần hồ sơ gì?"))

    assert len(result.items) == 1
    assert result.items[0]["metadata"]["case_order"] == 2
