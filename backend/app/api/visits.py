"""Đếm lượt mở trang người dân, lưu lịch sử trong audit_logs."""

from __future__ import annotations

import ipaddress

from fastapi import APIRouter, Request
from sqlalchemy import text

from backend.app.db.postgres import engine

router = APIRouter(prefix="/visits", tags=["visits"])


def _client_ip(request: Request) -> str | None:
    raw = request.client.host if request.client else None
    if not raw:
        return None
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


@router.post("")
def record_page_visit(request: Request) -> dict[str, bool]:
    """Ghi một lượt truy cập; gọi khi trang chat người dân được mở."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO audit_logs (action, entity, entity_id, ip_address, detail)
                VALUES ('page_view', 'client_chat', 'chat_page', :ip, '{}'::jsonb)
                """
            ),
            {"ip": _client_ip(request)},
        )
    return {"recorded": True}
