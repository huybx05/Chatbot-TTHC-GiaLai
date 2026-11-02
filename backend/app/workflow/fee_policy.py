"""Chuẩn hoá phí/lệ phí từ evidence trước khi sinh câu trả lời.

Nguồn portal có thể ghi ``Miễn phí`` kèm ghi chú nghĩa vụ nộp phí. Không để
mô hình tự chọn một vế; module này biến dữ liệu thành một trạng thái rõ ràng.
"""

from __future__ import annotations

import re
from typing import Any

from backend.app.text_norm import strip_accents

_AMOUNT = re.compile(r"(\d{1,3}(?:[.,]\d{3})+)\s*(?:đồng|vnđ|vnd)", re.IGNORECASE)


def _fee_items(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in evidence
        if str(item.get("facet") or "") == "fee"
        or str(item.get("section_type") or "").upper() == "FEE"
    ]


def fee_info(evidence: list[dict[str, Any]]) -> dict[str, Any] | None:
    items = _fee_items(evidence)
    if not items:
        return None
    text = " ".join(str(item.get("content") or "") for item in items)
    normalized = strip_accents(text).lower()
    amount_match = _AMOUNT.search(text)
    amount = amount_match.group(0).strip() if amount_match else ""
    is_free = "mien phi" in normalized
    mentions_payment = any(
        phrase in normalized
        for phrase in (
            "nop phi",
            "nop le phi",
            "muc thu",
            "tien su dung dat",
        )
    )
    if is_free and mentions_payment:
        status = "conditional"
    elif is_free:
        status = "free"
    elif amount:
        status = "paid"
    elif "theo quy dinh chung" in normalized or "khong neu so tien" in normalized:
        status = "conditional"
    else:
        status = "unknown"
    return {
        "status": status,
        "amount": amount,
        "contradictory": is_free and mentions_payment,
    }


def fee_prompt_note(evidence: list[dict[str, Any]]) -> str:
    info = fee_info(evidence)
    if info is None:
        return ""
    status = info["status"]
    if status == "free":
        return (
            "THÔNG TIN PHÍ ĐÃ CHUẨN HOÁ: thủ tục này miễn phí, lệ phí. "
            "Nói tự nhiên, không dùng cụm 'cổng ghi' hay 'dữ liệu ghi'."
        )
    if status == "paid" and info.get("amount"):
        return (
            "THÔNG TIN PHÍ ĐÃ CHUẨN HOÁ: mức phí/lệ phí là "
            f"{info['amount']}."
        )
    if status == "conditional" and info.get("contradictory"):
        return (
            "THÔNG TIN PHÍ ĐÃ CHUẨN HOÁ: nguồn ghi miễn phí nhưng kèm ghi chú "
            "nghĩa vụ nộp phí/lệ phí theo quy định. Không khẳng định chắc chắn; "
            "nêu đúng cả hai vế và khuyên kiểm tra cơ quan tiếp nhận."
        )
    if status == "conditional":
        return (
            "THÔNG TIN PHÍ ĐÃ CHUẨN HOÁ: có phí/lệ phí theo quy định nhưng "
            "nguồn chưa nêu số tiền cụ thể."
        )
    return "THÔNG TIN PHÍ ĐÃ CHUẨN HOÁ: nguồn chưa ghi nhận mức phí/lệ phí."
