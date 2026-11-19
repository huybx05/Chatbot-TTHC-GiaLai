"""Endpoint đánh giá offline cho Google Apps Script.

Không lưu hội thoại, không dùng session trình duyệt. Mỗi request là một
lượt hỏi độc lập; hội thoại nhiều lượt được truyền qua ``history``.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.app.api.chat import ChatRequest, HistoryTurn, chat
from backend.app.config import settings

router = APIRouter(tags=["evaluation"])


class EvaluationRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str = ""
    question: str = Field(min_length=1, max_length=1000)
    history: list[HistoryTurn] = Field(default_factory=list, max_length=8)
    faq_id: UUID | None = None


def _check_token(request: Request) -> None:
    expected = (settings.evaluation_api_token or "").strip()
    if not expected:
        return
    supplied = request.headers.get("x-eval-token", "").strip()
    if supplied != expected:
        raise HTTPException(status_code=401, detail="Sai token đánh giá.")


@router.post("/evaluation/run")
async def evaluation_run(
    payload: EvaluationRunRequest,
    request: Request,
) -> dict[str, Any]:
    _check_token(request)
    request.state.evaluation_mode = True
    started = time.perf_counter()
    trace_id = uuid4().hex

    try:
        response = await chat(
            ChatRequest(
                question=payload.question,
                history=payload.history,
                faq_id=payload.faq_id,
            ),
            request,
            None,
            BackgroundTasks(),
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"Không chạy được đánh giá: {exc}",
        ) from exc

    return {
        "case_id": payload.case_id,
        "trace_id": trace_id,
        "latency_ms": round((time.perf_counter() - started) * 1000),
        "status": response.status,
        "answer": response.answer,
        "procedure_code": (
            response.procedure.procedure_code if response.procedure else ""
        ),
        "procedure_name": (
            response.procedure.procedure_name if response.procedure else ""
        ),
        "faq_id": response.faq_id or "",
        "citations": [item.model_dump() for item in response.citations],
        "documents": [item.model_dump() for item in response.documents],
        "contexts": [item.model_dump() for item in response.contexts],
        "suggestions": [item.model_dump() for item in response.suggestions],
        "coverage": response.coverage,
    }
