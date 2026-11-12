"""Toàn bộ hồ sơ phải được trả từ evidence, không tóm tắt theo case."""

from __future__ import annotations

from backend.app.workflow import answer


def _item(case_order: int, case_name: str, content: str) -> dict:
    return {
        "kind": "section",
        "procedure_code": "1.004873",
        "procedure_name": "Thủ tục cấp Giấy xác nhận tình trạng hôn nhân",
        "content": content,
        "title": "Thành phần hồ sơ",
        "section_type": "REQUIRED_DOCUMENTS",
        "facet": "required_documents",
        "request_index": 0,
        "metadata": {
            "case_order": case_order,
            "case_name": case_name,
        },
    }


def test_hien_du_cac_case_va_luu_y() -> None:
    evidence = [
        _item(
            1,
            "* Giấy tờ phải nộp:",
            "Trường hợp: * Giấy tờ phải nộp: - - Nội dung nộp một",
        ),
        _item(2, "* Giấy tờ phải xuất trình:", "Nội dung xuất trình một"),
        _item(3, "* Lưu ý:", "Lưu ý một"),
        _item(4, "", "Nội dung chung"),
    ]

    text = answer.build_required_documents_answer(
        evidence,
        requests=[{"facet": "required_documents", "operation": "get"}],
        coverage=[{"request_index": 0, "status": "covered"}],
    )

    assert "Giấy tờ phải nộp" in text
    assert "Giấy tờ phải xuất trình" in text
    assert "Lưu ý" in text
    assert "Nội dung nộp một" in text
    assert "Trường hợp: * Giấy tờ phải nộp:" not in text
    assert "Nội dung xuất trình một" in text
    assert "Lưu ý một" in text
    assert "Nội dung chung" in text


def test_khong_lap_nhan_case_va_khong_lap_ma_thu_tuc() -> None:
    label = "Đối với trường hợp xác định lại khuyết tật"
    content = (
        f"**{label}** - {label} - + Đơn đề nghị theo Mẫu số 01 "
        "(1 bản chính)"
    )

    text = answer.build_required_documents_answer(
        [_item(1, label, content)],
        requests=[{"facet": "required_documents", "operation": "get"}],
        coverage=[{"request_index": 0, "status": "covered"}],
    )

    assert text.count(label) == 1
    assert f"**{label}** -" not in text
    assert "Đơn đề nghị theo Mẫu số 01" in text
    assert "Thành phần hồ sơ" not in text
    assert "Thủ tục 1.004873" in text


def test_khong_cat_noi_dung_dai() -> None:
    content = "Một câu rất dài " * 40

    text = answer.build_required_documents_answer(
        [_item(1, "* Lưu ý:", content)],
        requests=[{"facet": "notes", "operation": "get"}],
        coverage=[{"request_index": 0, "status": "covered"}],
    )

    assert content.strip() in text
