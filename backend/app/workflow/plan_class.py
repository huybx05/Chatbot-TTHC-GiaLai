"""Giai đoạn 2 — phân loại mức độ kế hoạch truy xuất bằng **mã nguồn**.

Nhãn ``plan_class`` KHÔNG phải nhãn nhánh cũ của router LLM. Nó trả lời một câu hỏi khác:
"lượt này cần loại nguồn lực nào?" — và được suy từ ``QuestionFrame`` + grounding, không gọi
mô hình.

Sáu nhãn (đóng):

```text
out_of_scope  ngoài TTHC / smalltalk → không truy xuất
unsupported   operation/facet chưa có công cụ, hoặc câu điều kiện pháp lý
              mà dữ liệu TTHC không trả lời được
clarify       có ý trỏ tới mention mà grounding báo mơ hồ / cần tiền ngữ
composed      ≥ 2 ý, tất cả đều xử lý được
discovery     chưa xác định thủ tục và không có mention để hỏi lại
direct        1 ý, đã xác định thủ tục/thực thể
```

Thứ tự ưu tiên khi gán nhãn cho cả lượt:
``out_of_scope > unsupported > clarify > composed > discovery > direct``.

Ngoài nhãn lượt, mỗi ý có **nhãn riêng** (cùng bộ giá trị) để không mất chi tiết khi câu có
nhiều ý bị trộn trạng thái.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from backend.app.workflow.question_frame import (
    Facet,
    QuestionFrame,
    QuestionScope,
    RequestOperation,
)


class PlanClass(StrEnum):
    OUT_OF_SCOPE = "out_of_scope"
    UNSUPPORTED = "unsupported"
    CLARIFY = "clarify"
    COMPOSED = "composed"
    DISCOVERY = "discovery"
    DIRECT = "direct"


#: Operation chưa có primitive tương ứng.
UNSUPPORTED_OPERATIONS = frozenset(
    {RequestOperation.COMPARE.value, RequestOperation.RANK.value}
)
#: Facet chưa có primitive tương ứng.
UNSUPPORTED_FACETS = frozenset({Facet.RELATED_PROCEDURES.value, Facet.UNKNOWN.value})
CONTENT_FACETS = frozenset(
    {
        Facet.REQUIRED_DOCUMENTS.value,
        Facet.STEPS.value,
        Facet.SUBMISSION_METHOD.value,
        Facet.PROCESSING_TIME.value,
        Facet.FEE.value,
        Facet.RESULT.value,
        Facet.REQUIREMENTS.value,
        Facet.GENERAL_INFO.value,
        Facet.LEGAL_BASIS.value,
    }
)


@dataclass(frozen=True, slots=True)
class RequestPlan:
    request_index: int
    plan_class: PlanClass
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_index": self.request_index,
            "plan_class": self.plan_class.value,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PlanClassResult:
    plan_class: PlanClass
    reason: str
    requests: tuple[RequestPlan, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_class": self.plan_class.value,
            "reason": self.reason,
            "requests": [item.to_dict() for item in self.requests],
        }


def _grounding_status(groundings: Sequence[Any], index: int | None) -> str:
    if index is None:
        return ""
    for item in groundings:
        if int(getattr(item, "index", -1)) == int(index):
            return str(getattr(item, "status", "") or "")
    return ""


def classify_request(
    request: dict[str, Any], groundings: Sequence[Any]
) -> tuple[PlanClass, str]:
    """Nhãn cho **một** ý. Không phụ thuộc nhãn của ý khác."""
    operation = str(request.get("operation") or RequestOperation.GET.value)
    facet = str(request.get("facet") or Facet.UNKNOWN.value)

    if operation in UNSUPPORTED_OPERATIONS:
        return PlanClass.UNSUPPORTED, f"operation chưa hỗ trợ: {operation}"
    if facet in UNSUPPORTED_FACETS:
        return PlanClass.UNSUPPORTED, f"facet chưa hỗ trợ: {facet}"

    ref = request.get("subject_ref")
    status = _grounding_status(groundings, ref)

    # Câu hỏi điều kiện pháp lý (có/không) mà chưa neo được thủ tục: dữ liệu TTHC chỉ mô tả
    # thủ tục, không trả lời quyền/nghĩa vụ pháp lý. Đây là "không hỗ trợ", không phải "hỏi lại".
    if (
        operation == RequestOperation.CHECK.value
        and facet == Facet.REQUIREMENTS.value
        and status != "resolved"
    ):
        return PlanClass.UNSUPPORTED, "điều kiện pháp lý chưa có nguồn trả lời"

    if ref is None:
        return PlanClass.DISCOVERY, "chưa có chủ thể, cần tìm thủ tục trước"

    if status == "resolved":
        return PlanClass.DIRECT, "chủ thể đã xác định"
    if status == "ambiguous":
        return PlanClass.CLARIFY, "chủ thể mơ hồ"
    if status == "context_required":
        return PlanClass.CLARIFY, "chủ thể cần tiền ngữ"
    if status == "not_found":
        return PlanClass.CLARIFY, "không định vị được chủ thể"
    return PlanClass.CLARIFY, "chưa xác định chủ thể"


def classify_turn(frame: QuestionFrame, groundings: Sequence[Any]) -> PlanClassResult:
    """Nhãn cho cả lượt + nhãn từng ý. Tất định, không gọi mô hình.

    Thứ tự ưu tiên: ``out_of_scope > unsupported > clarify > composed > discovery >
    direct``. Nhãn lượt nói **nguồn lực chính** cần dùng; nhãn từng ý giữ chi tiết.
    """
    scope = frame.get("scope")
    if scope in {QuestionScope.OUT_OF_SCOPE, QuestionScope.SMALLTALK}:
        scope_value = scope.value if isinstance(scope, QuestionScope) else str(scope)
        return PlanClassResult(PlanClass.OUT_OF_SCOPE, f"scope={scope_value}")

    requests = list(frame.get("requests") or [])
    if not requests:
        return PlanClassResult(PlanClass.OUT_OF_SCOPE, "frame không có ý hỏi")

    per_request: list[RequestPlan] = []
    for index, request in enumerate(requests):
        plan_class, reason = classify_request(request, groundings)
        per_request.append(
            RequestPlan(request_index=index, plan_class=plan_class, reason=reason)
        )
    classes = [item.plan_class for item in per_request]

    if PlanClass.UNSUPPORTED in classes:
        first = next(item for item in per_request if item.plan_class is PlanClass.UNSUPPORTED)
        return PlanClassResult(PlanClass.UNSUPPORTED, first.reason, tuple(per_request))
    if PlanClass.CLARIFY in classes:
        first = next(item for item in per_request if item.plan_class is PlanClass.CLARIFY)
        return PlanClassResult(PlanClass.CLARIFY, first.reason, tuple(per_request))
    if len(requests) > 1:
        return PlanClassResult(
            PlanClass.COMPOSED, f"{len(requests)} ý xử lý được", tuple(per_request)
        )
    if classes[0] is PlanClass.DISCOVERY:
        return PlanClassResult(PlanClass.DISCOVERY, per_request[0].reason, tuple(per_request))
    return PlanClassResult(PlanClass.DIRECT, per_request[0].reason, tuple(per_request))


__all__ = [
    "CONTENT_FACETS",
    "PlanClass",
    "PlanClassResult",
    "RequestPlan",
    "UNSUPPORTED_FACETS",
    "UNSUPPORTED_OPERATIONS",
    "classify_request",
    "classify_turn",
]
