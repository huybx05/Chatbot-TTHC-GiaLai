"""Đọc bảng ``procedure_time_cases`` (Giai đoạn 4) — mốc thời hạn kèm điều kiện áp dụng."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_cache: dict[str, list[dict[str, Any]]] | None = None


def clear_cache() -> None:
    global _cache
    _cache = None


async def load(*, force: bool = False) -> dict[str, list[dict[str, Any]]]:
    """``{mã: [ {gia_tri, don_vi, dieu_kien}, … ]}``; bảng chưa có → rỗng."""
    global _cache
    if _cache is not None and not force:
        return _cache
    try:
        from sqlalchemy import text

        from backend.app.db.postgres import engine

        def _read() -> dict[str, list[dict[str, Any]]]:
            ra: dict[str, list[dict[str, Any]]] = {}
            with engine.connect() as conn:
                for row in conn.execute(
                    text(
                        "SELECT procedure_code, gia_tri, don_vi, dieu_kien "
                        "FROM procedure_time_cases ORDER BY id"
                    )
                ):
                    ra.setdefault(str(row[0]), []).append(
                        {
                            "gia_tri": float(row[1]) if row[1] is not None else None,
                            "don_vi": str(row[2] or ""),
                            "dieu_kien": str(row[3] or ""),
                        }
                    )
            return ra

        _cache = await asyncio.to_thread(_read)
    except Exception as exc:  # noqa: BLE001 — bảng chưa tạo không được làm hỏng lượt
        logger.warning("Không đọc được procedure_time_cases: %s", exc)
        _cache = {}
    return _cache


async def cases_for(code: str) -> list[dict[str, Any]]:
    data = await load()
    return list(data.get(str(code)) or ())


__all__ = ["cases_for", "clear_cache", "load"]
