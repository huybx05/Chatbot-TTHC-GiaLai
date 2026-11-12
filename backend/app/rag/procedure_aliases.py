"""Alias mã thủ tục thành phần (mã cũ → mã hiện hành).

Mapping nằm trong ``config/interlinked_components.json`` vì đây là dữ liệu
nghiệp vụ của cổng DVC, không phải quy tắc từ khóa của ứng dụng. Module này chỉ
đọc mapping và chuẩn hóa mã; không hardcode danh sách mã.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
MAPPING_PATH = REPO / "config" / "interlinked_components.json"


def _normalize(code: str) -> str:
    return str(code or "").strip().replace(",", ".")


@lru_cache(maxsize=1)
def load_procedure_aliases() -> dict[str, str]:
    """Trả về ``mã cũ → mã hiện hành`` từ mọi component trong mapping."""
    if not MAPPING_PATH.exists():
        return {}

    raw = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    aliases: dict[str, str] = {}
    for payload in raw.values():
        if not isinstance(payload, dict):
            continue
        for component in payload.get("components", []):
            if not isinstance(component, dict):
                continue
            current = _normalize(component.get("code"))
            source = _normalize(component.get("source_code") or current)
            if current and source and source != current:
                aliases[source] = current
    return aliases


def resolve_procedure_alias(code: str) -> str:
    """Đổi mã cũ sang mã hiện hành; mã không có alias được giữ nguyên."""
    normalized = _normalize(code)
    return load_procedure_aliases().get(normalized, normalized)
