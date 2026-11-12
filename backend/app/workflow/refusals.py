"""Câu từ chối theo trạng thái dữ liệu.

Một câu chung "dữ liệu chưa đủ" không phân biệt được:

* chưa xác định thủ tục;
* thủ tục không tồn tại;
* thủ tục có thật nhưng khía cạnh chưa được ghi nhận;
* nguồn dữ liệu đang lỗi;
* hệ thống chưa hỗ trợ loại thông tin.

Các hàm ở đây chỉ tạo câu chữ; quyết định trạng thái nằm ở workflow.
"""

from __future__ import annotations

from collections.abc import Sequence

#: Nhãn đọc được của khía cạnh. Không chứa mã thủ tục hay từ khóa nhận diện.
FACET_LABELS: dict[str, str] = {
    "required_documents": "thành phần hồ sơ",
    "notes": "phần Lưu ý",
    "steps": "trình tự thực hiện",
    "submission_method": "cách thức nộp",
    "processing_time": "thời hạn giải quyết",
    "fee": "mức lệ phí",
    "result": "kết quả nhận được",
    "result_delivery": "cách nhận kết quả",
    "requirements": "điều kiện thực hiện",
    "legal_basis": "căn cứ pháp lý",
    "general_info": "thông tin chung",
    "procedure_relations": "quan hệ thủ tục",
    "components": "thủ tục thành phần",
    "parent_interlinked": "thủ tục cha",
}


def _facet_text(facets: Sequence[str]) -> str:
    labels = [FACET_LABELS.get(str(facet), str(facet)) for facet in facets if facet]
    if not labels:
        return "thông tin này"
    return " và ".join(dict.fromkeys(labels))


def facet_not_recorded(
    *,
    facets: Sequence[str],
    code: str = "",
    name: str = "",
) -> str:
    """Thủ tục đã biết nhưng dữ liệu nguồn chưa ghi nhận khía cạnh được hỏi."""
    subject = f"thủ tục {code}" if code else "thủ tục này"
    if name:
        subject += f" — {name}"
    return (
        f"Hiện dữ liệu tra cứu chưa ghi nhận {_facet_text(facets)} của {subject}. "
        "Bạn có thể xem trang nguồn để kiểm tra thông tin cập nhật."
    )


def source_failed() -> str:
    """Nguồn dữ liệu lỗi — tuyệt đối không được nói là dữ liệu không có."""
    return (
        "Nguồn dữ liệu đang tạm lỗi nên tôi chưa kết nối được để tra cứu. "
        "Đây chưa phải kết luận là thủ tục không có thông tin. "
        "Bạn vui lòng thử lại sau ít phút."
    )


def unsupported_facet() -> str:
    """Hệ thống chưa có công cụ cho loại thông tin này."""
    return (
        "Hiện tôi chưa hỗ trợ tra cứu loại thông tin này. "
        "Bạn có thể hỏi về hồ sơ, thời hạn, lệ phí, cơ quan hoặc căn cứ pháp lý."
    )


def insufficient_evidence() -> str:
    """Không xác định được vì sao không có kết quả; không đổ lỗi người dùng."""
    return (
        "Hiện tôi chưa tra được thông tin phù hợp cho câu hỏi này. "
        "Bạn có thể nêu rõ hơn thủ tục hoặc khía cạnh cần tra cứu."
    )


__all__ = [
    "FACET_LABELS",
    "facet_not_recorded",
    "insufficient_evidence",
    "source_failed",
    "unsupported_facet",
]
