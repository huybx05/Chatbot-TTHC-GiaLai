"""Giai đoạn 3 — quyết định khi câu hỏi khớp **cả một nhóm** thủ tục.

Ba kết cục, theo đúng thứ tự:

1. **Đồng thuận** — mọi thủ tục trong nhóm có cùng nội dung cho khía cạnh được hỏi:
   trả lời một lần, ghi rõ "áp dụng cho N trường hợp".
2. **Đại diện** — nội dung khác nhau nhưng nhóm có ``canonical_code`` đã rà soát:
   trả lời theo thủ tục đại diện, ghi rõ đang trả lời theo nhóm.
3. **Không quyết định** — trả ``None`` để grounding giữ trạng thái ``ambiguous`` (hỏi lại).

Không gọi mô hình. Nội dung lấy từ PostgreSQL, so sánh sau khi bỏ tiền tố metadata mà bộ
chunking đã chép vào mỗi đoạn.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from backend.app.rag import sections, themes
from backend.app.text_norm import strip_accents

logger = logging.getLogger(__name__)

#: Chỉ các khía cạnh có nội dung trong `procedure_sections` mới so sánh được.
THEME_FACETS = frozenset(
    {
        "required_documents",
        "steps",
        "submission_method",
        "processing_time",
        "fee",
        "result",
        "requirements",
        "general_info",
        "legal_basis",
    }
)


@dataclass(frozen=True, slots=True)
class ThemeDecision:
    """Kết quả khi một nhóm thủ tục trả lời được thay cho hỏi lại."""

    code: str
    name: str
    reason: str  # "agreement" | "canonical"
    theme_id: str
    theme_label: str
    members: int
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "reason": self.reason,
            "theme_id": self.theme_id,
            "theme_label": self.theme_label,
            "members": self.members,
            "note": self.note,
        }


def _normalize_value(rows: Sequence[dict[str, Any]]) -> str:
    """Nội dung một khía cạnh, đã bỏ tiền tố metadata và chuẩn hoá để so sánh."""
    parts: list[str] = []
    for row in rows:
        text = " ".join(str(row.get("content") or "").split())
        if "---" in text:
            text = text.split("---", 1)[1]
        text = strip_accents(text).lower()
        if text:
            parts.append(text)
    return " | ".join(parts)


def _group_by_code(rows: Sequence[dict[str, Any]]) -> dict[str, str]:
    theo_ma: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        theo_ma.setdefault(str(row.get("procedure_code") or ""), []).append(row)
    return {code: _normalize_value(items) for code, items in theo_ma.items() if code}


async def resolve_theme(
    codes: Sequence[str], facet: str
) -> ThemeDecision | None:
    """Thử trả lời bằng nhóm thủ tục. ``None`` = để grounding hỏi lại như cũ."""
    unique = [str(code) for code in dict.fromkeys(codes) if str(code)]
    if len(unique) < 2 or facet not in THEME_FACETS:
        return None

    index = await themes.load()
    theme = index.common_theme(unique) or index.dominant_theme(unique)
    if theme is None or len(theme.members) < 2:
        return None

    rows, error = await sections.theo_khia_canh_checked(list(theme.members), [facet])
    if error:
        logger.warning("Không so sánh được nhóm %s: %s", theme.theme_id, error)
        return None

    values = _group_by_code(rows)
    co_gia_tri = [values.get(code, "") for code in theme.members]
    if all(co_gia_tri) and len(set(co_gia_tri)) == 1:
        representative = (
            theme.canonical_code if theme.canonical_code in theme.members else unique[0]
        )
        return ThemeDecision(
            code=representative,
            name=theme.label,
            reason="agreement",
            theme_id=theme.theme_id,
            theme_label=theme.label,
            members=len(theme.members),
            note=(
                f"nhóm «{theme.label}»: {len(theme.members)} thủ tục có cùng nội dung "
                "cho khía cạnh này"
            ),
        )

    if theme.canonical_code:
        return ThemeDecision(
            code=theme.canonical_code,
            name=theme.label,
            reason="canonical",
            theme_id=theme.theme_id,
            theme_label=theme.label,
            members=len(theme.members),
            note=(
                f"nhóm «{theme.label}»: các trường hợp có nội dung khác nhau; "
                f"trả lời theo thủ tục đại diện {theme.canonical_code}"
            ),
        )
    return None


__all__ = ["THEME_FACETS", "ThemeDecision", "resolve_theme"]
