"""Dựng topic ledger từ metadata của message trợ lý.

Topic ledger chỉ chứa con trỏ (mã/tên/ID), không chứa nội dung đầy đủ.
Việc này để "thủ tục đầu tiên / thứ hai" vẫn xác định được dù cửa sổ
prompt chỉ còn vài lượt gần nhất.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

from backend.app.memory.types import TopicRef


def _as_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return value if isinstance(value, dict) else {}


def procedure_for_memory(metadata: Any) -> tuple[str, str] | None:
    """Procedure chỉ được vào memory khi lượt đó thực sự đã trả lời.

    ``memory_eligible`` là cờ server ghi khi answer có evidence. Các message
    cũ không có cờ này vẫn phải có ``status='answered'``; nhờ vậy procedure
    của lượt ``abstained``/``clarify`` không thể thành topic.
    """
    data = _as_metadata(metadata)
    if data.get("memory_eligible") is False:
        return None
    if str(data.get("status") or "").strip() != "answered":
        return None

    procedure = data.get("procedure")
    if not isinstance(procedure, dict):
        return None

    code = str(procedure.get("procedure_code") or "").strip()
    if not code:
        return None

    name = str(procedure.get("procedure_name") or "").strip()
    return code, name or code


def _procedure(metadata: Any) -> tuple[str, str] | None:
    return procedure_for_memory(metadata)


def derive_topics(messages: Iterable[Mapping[str, Any]]) -> list[TopicRef]:
    """Tạo topic ledger theo thứ tự xuất hiện; bỏ message không có thủ tục."""
    by_code: dict[str, TopicRef] = {}

    for message in messages:
        if str(message.get("role") or "") != "assistant":
            continue

        found = _procedure(message.get("metadata"))
        if found is None:
            continue

        code, name = found
        message_id = str(message.get("id") or "")
        if not message_id:
            continue

        existing = by_code.get(code)
        if existing is None:
            by_code[code] = TopicRef(
                order=len(by_code) + 1,
                procedure_code=code,
                procedure_name=name,
                first_message_id=message_id,
                last_message_id=message_id,
            )
        else:
            by_code[code] = TopicRef(
                order=existing.order,
                procedure_code=existing.procedure_code,
                procedure_name=name or existing.procedure_name,
                first_message_id=existing.first_message_id,
                last_message_id=message_id,
            )

    return sorted(by_code.values(), key=lambda topic: topic.order)


def merge_topics(
    existing: Iterable[TopicRef],
    discovered: Iterable[TopicRef],
) -> list[TopicRef]:
    """Gộp topic đã lưu với topic mới, giữ order cũ và cập nhật last_message."""
    merged: dict[str, TopicRef] = {
        topic.procedure_code: topic for topic in existing
    }
    next_order = max((topic.order for topic in merged.values()), default=0) + 1

    for topic in sorted(discovered, key=lambda item: item.order):
        current = merged.get(topic.procedure_code)
        if current is None:
            merged[topic.procedure_code] = TopicRef(
                order=next_order,
                procedure_code=topic.procedure_code,
                procedure_name=topic.procedure_name,
                first_message_id=topic.first_message_id,
                last_message_id=topic.last_message_id,
            )
            next_order += 1
            continue

        merged[topic.procedure_code] = TopicRef(
            order=current.order,
            procedure_code=current.procedure_code,
            procedure_name=topic.procedure_name or current.procedure_name,
            first_message_id=current.first_message_id,
            last_message_id=topic.last_message_id,
        )

    return sorted(merged.values(), key=lambda item: item.order)
