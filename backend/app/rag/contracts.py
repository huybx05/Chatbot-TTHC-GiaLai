"""Hợp đồng hai lớp kết quả: **giả thuyết tìm được** và **bằng chứng đã kiểm**.

## Vì sao phải tách

Một kết quả tìm kiếm gần nghĩa **chưa phải** bằng chứng. Nếu để nó đi thẳng vào bước sinh
câu trả lời, hệ thống có thể trả lời đúng câu chữ nhưng sai thủ tục — lỗi đã đo được ở câu
A2 (chọn "Xóa đăng ký thuê" thay vì thủ tục đăng ký biến động).

Hai lớp được định nghĩa ở đây:

* ``DISCOVERY`` — ứng viên kèm điểm và lý do tìm thấy. Đây là **giả thuyết**: dùng để quyết
  định đi định vị tiếp, **không** dùng để trả lời.
* ``VERIFIED`` — bằng chứng chỉ sinh ra sau khi ứng viên đã được định vị vào một mã thủ tục
  hoặc thực thể thật, rồi truy xuất bằng truy vấn có ràng buộc (section theo mã, Graph theo
  mã/thực thể, fact theo mã).

Nguyên tắc lấy từ *Deterministic Legal Agents* (SAT-Graph API): tìm kiếm chỉ là **hạt giống**
để đi định vị, không phải chân lý cuối cùng.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ResultKind(StrEnum):
    """Hai lớp kết quả. Không có lớp thứ ba."""

    DISCOVERY = "discovery"
    VERIFIED = "verified_evidence"


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    """Một ứng viên **chưa** phải bằng chứng.

    ``value`` là mã thủ tục hoặc chuỗi thực thể; ``reason`` nói vì sao nó xuất hiện (vector,
    khớp tên chính xác, từ điển văn bản, thực thể đóng…). Nhờ vậy bước sau có thể quyết định
    mà không phải đoán lại.
    """

    kind: str
    value: str
    label: str = ""
    score: float = 0.0
    reason: str = ""
    source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "result_kind": ResultKind.DISCOVERY.value,
            "kind": self.kind,
            "value": self.value,
            "label": self.label,
            "score": round(float(self.score), 4),
            "reason": self.reason,
            "source": self.source,
        }


def from_groundings(
    groundings: Sequence[Any], resolution: Any | None = None
) -> list[DiscoveryCandidate]:
    """Grounding (và resolution) → danh sách ứng viên, **không** phải bằng chứng.

    Mỗi mention có thể đã resolved hoặc còn mơ hồ. Cả hai trường hợp đều sinh ứng viên để
    trace thấy hệ thống đã cân nhắc những gì; bước grounded mới là nơi chuyển thành bằng chứng.
    """
    ra: list[DiscoveryCandidate] = []
    for item in groundings:
        alternatives = list(getattr(item, "alternatives", ()) or ())
        if getattr(item, "status", "") == "resolved" and getattr(item, "code", ""):
            ra.append(
                DiscoveryCandidate(
                    kind=str(getattr(item, "type", "") or "procedure"),
                    value=str(item.code),
                    label=str(getattr(item, "name", "") or getattr(item, "mention", "")),
                    score=float(getattr(item, "score", 0.0) or 0.0),
                    reason=f"grounding:{getattr(item, 'method', '')}",
                    source="grounding",
                )
            )
            continue
        for alt in alternatives:
            ma = str(alt.get("code") or "")
            ten = str(alt.get("name") or "")
            if not ma and not ten:
                continue
            ra.append(
                DiscoveryCandidate(
                    kind=str(getattr(item, "type", "") or "procedure"),
                    value=ma or ten,
                    label=ten,
                    score=float(alt.get("score") or 0.0),
                    reason=f"alternative:{getattr(item, 'method', '')}",
                    source="grounding",
                )
            )
        if not alternatives:
            ra.append(
                DiscoveryCandidate(
                    kind=str(getattr(item, "type", "") or "procedure"),
                    value=str(getattr(item, "mention", "")),
                    label=str(getattr(item, "mention", "")),
                    reason="unresolved",
                    source="grounding",
                )
            )

    if not ra and resolution is not None:
        ma = str(getattr(resolution, "code", "") or "")
        if ma:
            ra.append(
                DiscoveryCandidate(
                    kind="procedure",
                    value=ma,
                    label=str(getattr(resolution, "name", "") or ""),
                    score=float(getattr(resolution, "confidence", 0.0) or 0.0),
                    reason="resolution",
                    source="resolver",
                )
            )
        for code, name, score in list(getattr(resolution, "alternatives", ()) or ()):
            ra.append(
                DiscoveryCandidate(
                    kind="procedure",
                    value=str(code),
                    label=str(name),
                    score=float(score or 0.0),
                    reason="resolution_alternative",
                    source="resolver",
                )
            )
    return ra


def is_discovery_object(item: dict[str, Any]) -> bool:
    """True nếu mục này là **ứng viên**, không phải bằng chứng (không được vào ngữ cảnh)."""
    return str(item.get("kind") or "") == "candidate"


def mark_verified(items: Iterable[dict[str, Any]], reason: str) -> list[dict[str, Any]]:
    """Nâng bằng chứng lên ``VERIFIED`` sau khi đã neo vào mã/thực thể thật."""
    ra: list[dict[str, Any]] = []
    for item in items:
        item["result_kind"] = ResultKind.VERIFIED.value
        item["verified"] = True
        item["verification"] = reason
        ra.append(item)
    return ra


def verified_only(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chỉ giữ bằng chứng đã kiểm — dùng ở nơi tuyệt đối không nhận giả thuyết."""
    return [item for item in items if bool(item.get("verified"))]


__all__ = [
    "DiscoveryCandidate",
    "ResultKind",
    "from_groundings",
    "is_discovery_object",
    "mark_verified",
    "verified_only",
]
