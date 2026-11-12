from __future__ import annotations

from scripts.generate_faqs import (
    _clean_text,
    _display_name,
    _is_usable_section,
    ensure_answer_prefix,
    format_faq_answer,
    make_questions,
    select_procedures,
)


def _candidate(code: str, domain: str) -> dict:
    return {
        "procedure_code": code,
        "procedure_name": f"Thủ tục {code}",
        "domain_group": domain,
        "sections": {},
    }


def test_cau_hoi_ho_so_va_giu_dong_gach_dau_dong() -> None:
    questions = make_questions(
        {"procedure_code": "1.001699", "procedure_name": "Xác định khuyết tật"}
    )
    assert "required_documents" in questions
    assert "Thành phần hồ sơ" in questions["required_documents"]
    assert "1.001699" in questions["required_documents"]

    answer = ensure_answer_prefix(
        "- Giấy đề nghị.\n- Bản sao giấy tờ.",
        procedure_code="1.001699",
        procedure_name="Xác định khuyết tật",
        preserve_lines=True,
    )
    assert answer.startswith("Thủ tục 1.001699 (Xác định khuyết tật):")
    assert "\n- Bản sao giấy tờ." in answer


def test_format_faq_answer_co_nhan_in_dam_va_gach_dau_dong() -> None:
    basic = format_faq_answer(
        "Lệ phí: 50.000 đồng.",
        procedure_code="1.001699",
        procedure_name="Xác định khuyết tật",
        label="Lệ phí",
    )
    assert basic == (
        "Thủ tục 1.001699 (Xác định khuyết tật):\n\n"
        "**Lệ phí:** 50.000 đồng."
    )

    docs = format_faq_answer(
        "Thành phần hồ sơ:\n- Giấy đề nghị.\n- Bản sao giấy tờ.",
        procedure_code="1.001699",
        procedure_name="Xác định khuyết tật",
        label="Thành phần hồ sơ",
        preserve_lines=True,
    )
    assert docs.startswith(
        "Thủ tục 1.001699 (Xác định khuyết tật):\n\n"
        "**Thành phần hồ sơ:**\n"
    )
    assert "- Bản sao giấy tờ." in docs
    assert "**Thành phần hồ sơ:**" in docs


def test_clean_text_bo_metadata_va_giu_noi_dung() -> None:
    raw = (
        "Tên thủ tục: Cấp giấy phép\n"
        "Lĩnh vực: Đường bộ\n"
        "Nguồn: https://example.test\n"
        "---\n"
        "Lệ phí: 50.000 đồng."
    )

    assert _clean_text(raw) == "Lệ phí: 50.000 đồng."
    assert not _is_usable_section("Không có thông tin")
    assert _is_usable_section("Lệ phí: 50.000 đồng.")


def test_cau_hoi_ngan_gon_va_van_co_ma_thu_tuc() -> None:
    long_name = (
        "Xác định, xác định lại mức độ khuyết tật và cấp Giấy xác nhận "
        "khuyết tật cho người đã có kết luận của Hội đồng Giám định y khoa"
    )
    questions = make_questions(
        {"procedure_code": "1.001699", "procedure_name": long_name}
    )

    assert "1.001699" in questions["fee"]
    assert "1.001699" in questions["processing_time"]
    assert "1.001699" in questions["submission_method"]
    assert len(_display_name(long_name)) <= 95
    assert _display_name(long_name).endswith("…")


def test_cau_tra_loi_luon_bat_dau_bang_thu_tuc() -> None:
    answer = ensure_answer_prefix(
        "Lệ phí là 50.000 đồng.",
        procedure_code="1.001699",
        procedure_name="Xác định khuyết tật",
    )
    assert answer.startswith("Thủ tục 1.001699 (Xác định khuyết tật):")


def test_chon_300_thu_tuc_bao_quat_15_domain() -> None:
    candidates = [
        _candidate(f"{domain}-{index:03d}", domain)
        for domain in (f"D{number}" for number in range(1, 16))
        for index in range(1, 31)
    ]

    selected = select_procedures(candidates, limit=300, per_domain=20)

    assert len(selected) == 300
    assert len({item["domain_group"] for item in selected}) == 15
