from __future__ import annotations

from backend.app.memory.resolver import (
    apply_memory_anchor_to_groundings,
    apply_memory_antecedent,
    apply_memory_to_groundings,
)
from backend.app.rag.grounding import SubjectGrounding
from backend.app.rag.resolve import Resolution


def _memory(code: str = "1.001699", name: str = "Thủ tục A") -> dict:
    return {
        "active_procedure": {"code": code, "name": name},
        "topics": [
            {
                "order": 1,
                "procedure_code": code,
                "procedure_name": name,
            }
        ],
    }


def test_apply_memory_khi_cau_can_tien_ngu() -> None:
    resolution = Resolution(question="Thủ tục này cần gì?", needs_antecedent=True)

    changed = apply_memory_antecedent(resolution, _memory())

    assert changed is True
    assert resolution.codes == ["1.001699"]
    assert resolution.procedure.code == "1.001699"
    assert resolution.procedure.name == "Thủ tục A"
    assert resolution.procedure.method == "memory"
    assert resolution.needs_antecedent is False


def test_khong_doi_khi_khong_co_active_procedure() -> None:
    resolution = Resolution(question="Thủ tục này cần gì?", needs_antecedent=True)

    changed = apply_memory_antecedent(resolution, {"active_procedure": None})

    assert changed is False
    assert resolution.needs_antecedent is True
    assert resolution.codes == []


def test_khong_doi_khi_cau_khong_can_tien_ngu() -> None:
    resolution = Resolution(question="Thủ tục A cần gì?", needs_antecedent=False)

    changed = apply_memory_antecedent(resolution, _memory())

    assert changed is False
    assert resolution.needs_antecedent is False
    assert resolution.codes == []


def test_khong_ghi_de_ma_nguoi_dung_da_neu() -> None:
    resolution = Resolution(
        question="Thủ tục 1.014758 cần gì?",
        codes=["1.014758"],
        needs_antecedent=True,
    )

    changed = apply_memory_antecedent(resolution, _memory())

    assert changed is False
    assert resolution.codes == ["1.014758"]
    assert resolution.needs_antecedent is True


def test_cuu_grounding_resolved_sai_bang_active_procedure() -> None:
    resolution = Resolution(question="Thời hạn giải quyết bao lâu?")
    groundings = [
        SubjectGrounding(
            index=0,
            status="resolved",
            type="procedure",
            mention="Thủ tục A",
            code="1.115378",
            name="Thủ tục B",
            method="disambiguation",
            score=0.77,
        )
    ]

    changed = apply_memory_to_groundings(
        groundings,
        _memory("1.001699", "Thủ tục A"),
        resolution=resolution,
    )

    assert changed is True
    assert groundings[0].code == "1.001699"
    assert groundings[0].name == "Thủ tục A"
    assert groundings[0].method == "memory"


def test_cuu_grounding_ambiguous_bang_active_procedure() -> None:
    resolution = Resolution(question="Còn lệ phí thì sao?")
    groundings = [
        SubjectGrounding(
            index=0,
            status="ambiguous",
            type="procedure",
            mention="Thủ tục A",
            method="vector",
            score=0.64,
        )
    ]

    changed = apply_memory_to_groundings(
        groundings,
        _memory("1.001699", "Thủ tục A"),
        resolution=resolution,
    )

    assert changed is True
    assert groundings[0].status == "resolved"
    assert groundings[0].code == "1.001699"
    assert groundings[0].name == "Thủ tục A"
    assert groundings[0].method == "memory"
    assert groundings[0].score == 1.0


def test_resolution_memory_la_canonical_cho_dai_tu_thu_tuc_nay() -> None:
    resolution = Resolution(
        question="Lệ phí và thời hạn của thủ tục này là bao nhiêu?",
        needs_antecedent=True,
    )
    assert apply_memory_antecedent(
        resolution,
        _memory("1.001699", "Xác định mức độ khuyết tật"),
    )
    groundings = [
        SubjectGrounding(
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

    changed = apply_memory_to_groundings(
        groundings,
        _memory("1.001699", "Xác định mức độ khuyết tật"),
        resolution=resolution,
    )

    assert changed is True
    assert groundings[0].status == "resolved"
    assert groundings[0].code == "1.001699"
    assert groundings[0].name == "Xác định mức độ khuyết tật"
    assert groundings[0].method == "memory"
    assert groundings[0].alternatives == []


def test_khong_cuu_grounding_khi_nguoi_dung_neu_ma_moi() -> None:
    resolution = Resolution(question="Thủ tục 1.014758 cần gì?", codes=["1.014758"])
    groundings = [
        SubjectGrounding(
            index=0,
            status="ambiguous",
            type="procedure",
            mention="Thủ tục A",
            method="vector",
            score=0.64,
        )
    ]

    changed = apply_memory_to_groundings(
        groundings,
        _memory(),
        resolution=resolution,
    )

    assert changed is False
    assert groundings[0].status == "ambiguous"


def test_anchor_thay_grounding_resolved_sai() -> None:
    resolution = Resolution(
        question="Thời hạn giải quyết của thủ tục (mã 1.001699) là bao lâu?",
        codes=["1.001699"],
    )
    groundings = [
        SubjectGrounding(
            index=0,
            status="resolved",
            type="procedure",
            mention="Thủ tục A",
            code="1.115378",
            name="Thủ tục B",
            method="disambiguation",
            score=0.77,
        )
    ]

    changed = apply_memory_anchor_to_groundings(
        groundings,
        {"code": "1.001699", "name": "Thủ tục A"},
        resolution=resolution,
    )

    assert changed is True
    assert groundings[0].code == "1.001699"
    assert groundings[0].name == "Thủ tục A"
    assert groundings[0].method == "memory_anchor"


def test_anchor_cuu_grounding_ambiguous() -> None:
    resolution = Resolution(question="Còn lệ phí thì sao?")
    groundings = [
        SubjectGrounding(
            index=0,
            status="ambiguous",
            type="procedure",
            mention="Thủ tục A",
            method="vector",
            score=0.64,
        )
    ]

    changed = apply_memory_anchor_to_groundings(
        groundings,
        {"code": "1.001699", "name": "Thủ tục A"},
        resolution=resolution,
    )

    assert changed is True
    assert groundings[0].status == "resolved"
    assert groundings[0].code == "1.001699"
    assert groundings[0].method == "memory_anchor"


def test_anchor_khong_ghi_de_grounding_resolved_khi_khong_co_ma_nguoi_dung() -> None:
    resolution = Resolution(question="Tôi muốn làm thủ tục sửa chữa nhà.")
    groundings = [
        SubjectGrounding(
            index=0,
            status="resolved",
            type="procedure",
            mention="Cấp giấy phép xây dựng sửa chữa, cải tạo",
            code="1.013229",
            name="Cấp giấy phép xây dựng sửa chữa, cải tạo",
            method="exact_name",
            score=1.0,
        )
    ]

    changed = apply_memory_anchor_to_groundings(
        groundings,
        {"code": "1.013225", "name": "Cấp giấy phép xây dựng mới"},
        resolution=resolution,
        original_question="Tôi muốn làm thủ tục sửa chữa nhà.",
    )

    assert changed is False
    assert groundings[0].code == "1.013229"
    assert groundings[0].method == "exact_name"


def test_anchor_van_cuu_grounding_vector_sai_khi_khong_co_ma() -> None:
    resolution = Resolution(question="Còn thời hạn thì sao?")
    groundings = [
        SubjectGrounding(
            index=0,
            status="resolved",
            type="procedure",
            mention="thủ tục này",
            code="1.013229",
            name="Cấp giấy phép xây dựng sửa chữa, cải tạo",
            method="vector",
            score=0.8,
        )
    ]

    changed = apply_memory_anchor_to_groundings(
        groundings,
        {"code": "1.013225", "name": "Cấp giấy phép xây dựng mới"},
        resolution=resolution,
        original_question="Còn thời hạn thì sao?",
    )

    assert changed is True
    assert groundings[0].code == "1.013225"


def test_anchor_van_cuu_grounding_resolved_sai_khi_nguoi_dung_neu_ma() -> None:
    resolution = Resolution(
        question="Thời hạn của thủ tục 1.013225 là bao lâu?",
        codes=["1.013225"],
    )
    groundings = [
        SubjectGrounding(
            index=0,
            status="resolved",
            type="procedure",
            mention="Cấp giấy phép xây dựng",
            code="1.013229",
            name="Cấp giấy phép xây dựng sửa chữa, cải tạo",
            method="vector",
            score=0.8,
        )
    ]

    changed = apply_memory_anchor_to_groundings(
        groundings,
        {"code": "1.013225", "name": "Cấp giấy phép xây dựng mới"},
        resolution=resolution,
        original_question="Thời hạn của thủ tục 1.013225 là bao lâu?",
    )

    assert changed is True
    assert groundings[0].code == "1.013225"


def test_memory_khong_ghi_de_grounding_resolved_exact_name_moi() -> None:
    resolution = Resolution(question="Làm thủ tục sửa chữa nhà.")
    groundings = [
        SubjectGrounding(
            index=0,
            status="resolved",
            type="procedure",
            mention="Cấp giấy phép xây dựng sửa chữa, cải tạo",
            code="1.013229",
            name="Cấp giấy phép xây dựng sửa chữa, cải tạo",
            method="exact_name",
            score=1.0,
        )
    ]

    changed = apply_memory_to_groundings(
        groundings,
        _memory("1.013225", "Cấp giấy phép xây dựng"),
        resolution=resolution,
    )

    assert changed is False
    assert groundings[0].code == "1.013229"


def test_anchor_khong_ghi_de_ma_nguoi_dung() -> None:
    resolution = Resolution(question="Thủ tục 1.014758 cần gì?", codes=["1.014758"])
    groundings = [
        SubjectGrounding(
            index=0,
            status="ambiguous",
            type="procedure",
            mention="Thủ tục A",
            method="vector",
            score=0.64,
        )
    ]

    changed = apply_memory_anchor_to_groundings(
        groundings,
        {"code": "1.001699", "name": "Thủ tục A"},
        resolution=resolution,
    )

    assert changed is False
    assert groundings[0].status == "ambiguous"


def test_anchor_khong_ap_dung_khi_co_nhieu_mention() -> None:
    groundings = [
        SubjectGrounding(
            index=0,
            status="ambiguous",
            type="procedure",
            mention="Thủ tục A",
        ),
        SubjectGrounding(
            index=1,
            status="not_found",
            type="procedure",
            mention="Thủ tục B",
        ),
    ]

    changed = apply_memory_anchor_to_groundings(
        groundings,
        {"code": "1.001699", "name": "Thủ tục A"},
    )

    assert changed is False
    assert groundings[0].status == "ambiguous"
    assert groundings[1].status == "not_found"


def test_anchor_khong_ap_dung_khi_mention_co_ma() -> None:
    groundings = [
        SubjectGrounding(
            index=0,
            status="not_found",
            type="procedure",
            mention="Thủ tục 9.999999",
        )
    ]

    changed = apply_memory_anchor_to_groundings(
        groundings,
        {"code": "1.001699", "name": "Thủ tục A"},
    )

    assert changed is False
    assert groundings[0].status == "not_found"
