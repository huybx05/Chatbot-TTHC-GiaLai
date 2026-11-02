from __future__ import annotations

from backend.app.workflow.fee_policy import fee_info, fee_prompt_note


def _fee(content: str) -> dict:
    return {
        "kind": "section",
        "section_type": "FEE",
        "facet": "fee",
        "content": content,
    }


def test_fee_mien_phi() -> None:
    info = fee_info([_fee("Loại: Miễn phí Cổng ghi thủ tục này miễn phí.")])

    assert info is not None
    assert info["status"] == "free"
    assert "miễn phí" in fee_prompt_note([_fee("Loại: Miễn phí")]).lower()


def test_fee_theo_quy_dinh_chung() -> None:
    info = fee_info(
        [
            _fee(
                "Loại: Theo quy định chung Cổng không nêu số tiền cụ thể. "
                "Người sử dụng đất nộp phí, lệ phí cho cơ quan giải quyết."
            )
        ]
    )

    assert info is not None
    assert info["status"] == "conditional"
    assert "chưa nêu số tiền" in fee_prompt_note(
        [_fee("Loại: Theo quy định chung")]
    )


def test_fee_so_tien() -> None:
    info = fee_info([_fee("Loại: Mức cụ thể Các mức cụ thể: - 500.000 đồng")])

    assert info is not None
    assert info["status"] == "paid"
    assert info["amount"] == "500.000 đồng"


def test_fee_mien_phi_nhung_co_ghi_chu_nop_phi() -> None:
    info = fee_info(
        [
            _fee(
                "Loại: Miễn phí. (nộp phí, lệ phí theo quy định của pháp luật; "
                "người sử dụng đất nộp phí, lệ phí cho cơ quan giải quyết)"
            )
        ]
    )

    assert info is not None
    assert info["status"] == "conditional"
    assert "miễn phí" in fee_prompt_note(
        [_fee("Loại: Miễn phí. nộp phí, lệ phí theo quy định")]
    ).lower()
