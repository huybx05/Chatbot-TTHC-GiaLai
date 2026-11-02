"""Admin cost dashboard endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response

from backend.app.auth.dependencies import AdminUser
from backend.app.cost.service import summary_sync

router = APIRouter(tags=["admin-costs"])


@router.get("/costs/summary")
def cost_summary(response: Response, _admin: AdminUser) -> dict:
    # Dữ liệu chi phí phải phản ánh ngay sau khi refresh trang.
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return summary_sync()
