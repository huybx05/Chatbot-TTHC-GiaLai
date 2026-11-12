"""Case resolver không được chọn case chỉ vì tên thủ tục xuất hiện trong heading."""

from __future__ import annotations

import asyncio

from backend.app.workflow import executor
from backend.app.workflow.case_resolver import filter_items, select_case
from backend.app.workflow.planner import Task


def _row(order: int, name: str, heading: str) -> dict:
    return {
        "metadata": {
            "case_order": order,
            "case_name": name,
            "block_heading": heading,
        }
    }


def _rows() -> list[dict]:
    return [
        _row(1, "Giấy tờ phải nộp", "Giấy tờ phải nộp"),
        _row(2, "Giấy tờ phải xuất trình", "Giấy tờ phải xuất trình"),
        _row(3, "Lưu ý", "Lưu ý"),
        # Case 4 của dữ liệu thật có case_name rỗng; heading chỉ nhắc tên thủ tục.
        _row(
            4,
            "",
            "Người có yêu cầu đăng ký khai sinh thực hiện việc nộp/xuất trình các giấy tờ sau",
        ),
    ]


def test_cau_hoi_ho_so_chung_khong_chon_case() -> None:
    question = "Vậy tôi cần chuẩn bị hồ sơ gì cho thủ tục đăng ký khai sinh?"

    assert select_case(question, _rows()) is None
    assert len(filter_items(_rows(), None)) == 4


def test_cau_hoi_neu_ro_case_van_chon_dung() -> None:
    question = "Tôi cần giấy tờ phải xuất trình cho thủ tục đăng ký khai sinh?"

    case = select_case(question, _rows())

    assert case is not None
    assert case["case_order"] == 2


def test_heading_chua_ten_thu_tuc_khong_phai_case() -> None:
    rows = [
        _row(
            1,
            "Giấy tờ phải nộp",
            "Người có yêu cầu cấp Giấy xác nhận tình trạng hôn nhân nộp các giấy tờ sau",
        ),
        _row(
            2,
            "Giấy tờ phải xuất trình",
            "Giấy tờ phải xuất trình",
        ),
        _row(3, "Lưu ý", "Lưu ý"),
        _row(4, "", "Người có yêu cầu cấp Giấy xác nhận tình trạng hôn nhân"),
    ]
    question = "Hồ sơ của thủ tục xác nhận tình trạng hôn nhân gồm những gì?"

    assert select_case(question, rows) is None
    assert len(filter_items(rows, None)) == 4


def test_run_section_dung_cau_goc_de_chon_case(monkeypatch) -> None:
    rows = [
        {
            "procedure_code": "1.001193",
            "procedure_name": "Thủ tục đăng ký khai sinh",
            "section_type": "REQUIRED_DOCUMENTS",
            "title": f"case {item['metadata']['case_order']}",
            "content": f"nội dung case {item['metadata']['case_order']}",
            "detail_url": "https://example.test",
            "metadata": item["metadata"],
        }
        for item in _rows()
    ]

    async def fake_section(_codes, _sections):
        return rows, ""

    monkeypatch.setattr(executor.sections, "theo_khia_canh_checked", fake_section)
    task = Task(
        request_index=0,
        tool="section_lookup",
        facet="required_documents",
        operation="get",
        procedure_codes=("1.001193",),
    )

    result = asyncio.run(
        executor._run_section(  # noqa: SLF001
            task,
            "Tôi cần hồ sơ gì cho thủ tục Thủ tục đăng ký khai sinh (mã 1.001193)?",
            case_question="Vậy tôi cần chuẩn bị hồ sơ gì cho thủ tục này?",
        )
    )

    assert len(result.items) == 4
