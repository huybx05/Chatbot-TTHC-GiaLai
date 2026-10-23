"""Giai đoạn 3 — nhóm thủ tục (theme) sinh từ **tên** thủ tục trong dữ liệu.

Vì sao cần: câu chung như *"đăng ký biến động đất đai"* khớp nhiều thủ tục là biến thể của
nhau (đổi tên, chuyển mục đích, chia tách…). Không có khái niệm "nhóm" thì hệ thống chỉ có hai
lựa chọn: chọn bừa một thủ tục hoặc hỏi lại — cả hai đều không tốt.

Cách gom: chuẩn hoá tên (bỏ dấu, lowercase, ``đ`` → ``d``), lấy **4 từ đầu** làm khoá. Bốn từ
đủ tách ``đăng ký biến động`` khỏi ``đăng ký biện pháp`` (ba từ thì trùng), nhưng vẫn gom đúng
6 thủ tục ``đăng ký biến động …``.

Không có danh sách từ khoá nào trong mã. Nhóm do tên thủ tục trong CSDL quyết định.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from backend.app.text_norm import strip_accents

logger = logging.getLogger(__name__)

#: Số từ đầu dùng làm khoá nhóm. Bốn từ là mức đã đo trên 49 thủ tục hiện có.
THEME_KEY_TOKENS = 4
#: Nhóm phải có ít nhất hai thủ tục; nhóm một thủ tục không có ý nghĩa.
THEME_MIN_MEMBERS = 2


@dataclass(frozen=True, slots=True)
class Theme:
    theme_id: str
    label: str
    canonical_code: str
    members: tuple[str, ...]


class ThemeIndex:
    """Ảnh chụp bảng nhóm trong bộ nhớ. Rỗng nếu bảng chưa được tạo."""

    def __init__(self, themes: Iterable[Theme] = ()) -> None:
        self._by_id: dict[str, Theme] = {item.theme_id: item for item in themes}
        self._by_code: dict[str, Theme] = {}
        for theme in self._by_id.values():
            for code in theme.members:
                self._by_code[code] = theme

    def __bool__(self) -> bool:
        return bool(self._by_id)

    def get(self, theme_id: str) -> Theme | None:
        return self._by_id.get(theme_id)

    def theme_of(self, code: str) -> Theme | None:
        return self._by_code.get(str(code))

    def common_theme(self, codes: Sequence[str]) -> Theme | None:
        """Nhóm chung của **tất cả** mã; ``None`` nếu chúng khác nhóm hoặc thiếu mã."""
        themes = [self.theme_of(code) for code in codes]
        if not themes or any(item is None for item in themes):
            return None
        first = themes[0]
        if any(item.theme_id != first.theme_id for item in themes if item is not None):
            return None
        return first

    def dominant_theme(self, codes: Sequence[str]) -> Theme | None:
        """Nhóm chiếm **đa số** trong các ứng viên (>= một nửa), nếu có.

        Dùng khi resolver trả về vài ứng viên thuộc một nhóm và một ứng viên ngoài nhóm:
        câu chung vẫn nên trả lời theo nhóm chiếm đa số thay vì hỏi lại.
        """
        counts: dict[str, int] = {}
        for code in codes:
            theme = self.theme_of(code)
            if theme is not None:
                counts[theme.theme_id] = counts.get(theme.theme_id, 0) + 1
        if not counts:
            return None
        best_id, best_count = max(counts.items(), key=lambda item: item[1])
        if best_count < 2 or best_count * 2 < len(codes):
            return None
        return self._by_id.get(best_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "themes": [
                {
                    "theme_id": item.theme_id,
                    "label": item.label,
                    "canonical_code": item.canonical_code,
                    "members": list(item.members),
                }
                for item in sorted(self._by_id.values(), key=lambda x: x.theme_id)
            ]
        }


def normalize_name(text: str) -> str:
    """Bỏ dấu, lowercase, bỏ dấu câu — để ``đăng ký, cấp`` và ``đăng ký cấp`` cùng khoá."""
    value = strip_accents(str(text or "")).lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def theme_key(name: str, *, tokens: int = THEME_KEY_TOKENS) -> str:
    """Khoá nhóm: ``tokens`` từ đầu của tên đã chuẩn hoá."""
    words = normalize_name(name).split()
    return " ".join(words[:tokens])


def _label(names: Sequence[str], key: str) -> str:
    """Nhãn đọc được: tiền tố chung của các tên gốc, nếu không có thì dùng khoá."""
    words = [str(name or "").split() for name in names]
    if not words:
        return key
    common: list[str] = []
    for index in range(min(len(item) for item in words)):
        value = words[0][index]
        if all(item[index].lower() == value.lower() for item in words):
            common.append(value)
        else:
            break
    return " ".join(common).strip(" ,") or key


def group_procedures(
    rows: Sequence[tuple[str, str]],
    *,
    tokens: int = THEME_KEY_TOKENS,
    min_members: int = THEME_MIN_MEMBERS,
) -> dict[str, list[tuple[str, str]]]:
    """``(code, name)`` → ``{khoá nhóm: [(code, name), …]}``, chỉ giữ nhóm đủ thành viên."""
    groups: dict[str, list[tuple[str, str]]] = {}
    for code, name in rows:
        key = theme_key(name, tokens=tokens)
        if not key:
            continue
        groups.setdefault(key, []).append((code, name))
    return {key: items for key, items in groups.items() if len(items) >= min_members}


def to_themes(groups: dict[str, list[tuple[str, str]]], canonical: dict[str, str]) -> list[Theme]:
    """Nhóm thô → ``Theme`` với ``theme_id`` ổn định và nhãn đọc được."""
    result: list[Theme] = []
    for key, items in sorted(groups.items()):
        # Khoá có dấu câu từ tên gốc ("đăng ký, cấp...") → chỉ giữ chữ/số và gạch dưới.
        theme_id = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
        result.append(
            Theme(
                theme_id=theme_id,
                label=_label([name for _, name in items], key),
                canonical_code=str(canonical.get(theme_id) or ""),
                members=tuple(code for code, _ in items),
            )
        )
    return result


_cache: ThemeIndex | None = None


def clear_cache() -> None:
    global _cache
    _cache = None


async def load(*, force: bool = False) -> ThemeIndex:
    """Đọc bảng nhóm từ PostgreSQL, cache lại. Bảng chưa có → index rỗng, không lỗi."""
    global _cache
    if _cache is not None and not force:
        return _cache
    try:
        from sqlalchemy import text

        from backend.app.db.postgres import engine

        def _read() -> ThemeIndex:
            themes: dict[str, dict[str, Any]] = {}
            with engine.connect() as conn:
                for row in conn.execute(
                    text("SELECT theme_id, label, canonical_code FROM procedure_themes")
                ):
                    themes[str(row[0])] = {
                        "label": str(row[1] or ""),
                        "canonical": str(row[2] or ""),
                        "members": [],
                    }
                for row in conn.execute(
                    text(
                        "SELECT procedure_code, theme_id FROM procedures "
                        "WHERE theme_id IS NOT NULL"
                    )
                ):
                    theme = themes.get(str(row[1]))
                    if theme is not None:
                        theme["members"].append(str(row[0]))
            return ThemeIndex(
                Theme(
                    theme_id=theme_id,
                    label=str(item["label"]),
                    canonical_code=str(item["canonical"]),
                    members=tuple(item["members"]),
                )
                for theme_id, item in themes.items()
                if item["members"]
            )

        _cache = await asyncio.to_thread(_read)
    except Exception as exc:  # noqa: BLE001 — bảng chưa tạo không được làm hỏng lượt
        logger.warning("Không đọc được bảng nhóm thủ tục: %s", exc)
        _cache = ThemeIndex()
    return _cache


__all__ = [
    "THEME_KEY_TOKENS",
    "THEME_MIN_MEMBERS",
    "Theme",
    "ThemeIndex",
    "clear_cache",
    "group_procedures",
    "load",
    "normalize_name",
    "theme_key",
    "to_themes",
]
