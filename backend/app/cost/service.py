"""Persist usage events and compute dashboard summaries."""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from backend.app.cost.pricing import (
    calculate_cost,
    canonical_model_key,
    to_price_version,
)
from backend.app.db.postgres import engine

logger = logging.getLogger(__name__)

MONTHLY_BUDGET_USD = 20.0
LOCAL_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "cost_trace_id", default=""
)


def set_trace_id(value: str):
    return _trace_id.set(str(value or ""))


def reset_trace_id(token: contextvars.Token) -> None:
    _trace_id.reset(token)


def _active_price(conn: Any, model_key: str, at: datetime) -> Any:
    row = conn.execute(
        text(
            """
            SELECT p.*, m.model_key, m.kind
            FROM ai_price_versions p
            JOIN ai_models m ON m.id = p.model_id
            WHERE m.model_key = :model_key
              AND p.effective_from <= :at
              AND (p.effective_to IS NULL OR p.effective_to > :at)
            ORDER BY p.effective_from DESC
            LIMIT 1
            """
        ),
        {"model_key": model_key, "at": at},
    ).mappings().first()
    return to_price_version(dict(row)) if row else None


def record_usage_sync(
    *,
    stage: str,
    model: str,
    input_tokens: int = 0,
    cached_tokens: int = 0,
    output_tokens: int = 0,
    embedding_tokens: int = 0,
    rerank_tokens: int = 0,
    success: bool = True,
    error: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Ghi một lần gọi model. Không bao giờ ném lỗi ra ngoài."""
    if not any((input_tokens, cached_tokens, output_tokens, embedding_tokens, rerank_tokens)):
        return
    model_key = canonical_model_key(model)
    at = datetime.now(UTC)
    try:
        with engine.begin() as conn:
            price = _active_price(conn, model_key, at)
            if price is None:
                cost_micro = 0
                price_id = None
                peak = False
                tier = ""
            else:
                result = calculate_cost(
                    price,
                    input_tokens=int(input_tokens),
                    cached_tokens=int(cached_tokens),
                    output_tokens=int(output_tokens),
                    embedding_tokens=int(embedding_tokens),
                    rerank_tokens=int(rerank_tokens),
                    at=at,
                )
                cost_micro = result.cost_micro_usd
                price_id = result.price_version_id
                peak = result.is_peak
                tier = result.input_tier
            conn.execute(
                text(
                    """
                    INSERT INTO ai_usage_events (
                        trace_id, stage, model_key, input_tokens, cached_tokens,
                        output_tokens, embedding_tokens, rerank_tokens, is_peak,
                        input_tier, price_version_id, cost_micro_usd, success,
                        error, metadata, occurred_at
                    ) VALUES (
                        :trace_id, :stage, :model_key, :input_tokens, :cached_tokens,
                        :output_tokens, :embedding_tokens, :rerank_tokens, :is_peak,
                        :input_tier, :price_version_id, :cost_micro, :success,
                        :error, CAST(:metadata AS JSONB), :occurred_at
                    )
                    """
                ),
                {
                    "trace_id": _trace_id.get(),
                    "stage": str(stage),
                    "model_key": model_key,
                    "input_tokens": int(input_tokens),
                    "cached_tokens": int(cached_tokens),
                    "output_tokens": int(output_tokens),
                    "embedding_tokens": int(embedding_tokens),
                    "rerank_tokens": int(rerank_tokens),
                    "is_peak": bool(peak),
                    "input_tier": tier,
                    "price_version_id": price_id,
                    "cost_micro": int(cost_micro),
                    "success": bool(success),
                    "error": str(error or "")[:500],
                    "metadata": json.dumps(metadata or {}, ensure_ascii=False),
                    "occurred_at": at,
                },
            )
    except Exception as exc:  # noqa: BLE001 — cost không được làm hỏng câu trả lời
        logger.warning("Không ghi được usage cost: %s", exc)


async def record_usage(**kwargs: Any) -> None:
    await asyncio.to_thread(record_usage_sync, **kwargs)


def _month_bounds(now: datetime) -> tuple[datetime, datetime]:
    local = now.astimezone(LOCAL_TIMEZONE)
    start_local = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if local.month == 12:
        end_local = start_local.replace(year=local.year + 1, month=1)
    else:
        end_local = start_local.replace(month=local.month + 1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def _usd(micro: int) -> float:
    return round(int(micro) / 1_000_000, 6)


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (Decimal,)):
        return float(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


def _budget_status(spent: float) -> str:
    ratio = spent / MONTHLY_BUDGET_USD if MONTHLY_BUDGET_USD else 0
    if ratio >= 1:
        return "over"
    if ratio >= 0.8:
        return "warning"
    if ratio >= 0.5:
        return "notice"
    return "normal"


def summary_sync() -> dict[str, Any]:
    now = datetime.now(UTC)
    month_start, month_end = _month_bounds(now)
    day_start = now.astimezone(LOCAL_TIMEZONE).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).astimezone(UTC)

    with engine.connect() as conn:
        month_row = conn.execute(
            text(
                """
                SELECT COALESCE(SUM(cost_micro_usd), 0) AS cost,
                       COUNT(*) AS calls,
                       COALESCE(SUM(input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(cached_tokens), 0) AS cached_tokens,
                       COALESCE(SUM(output_tokens), 0) AS output_tokens
                FROM ai_usage_events
                WHERE occurred_at >= :start AND occurred_at < :end
                  AND model_key IN (SELECT model_key FROM ai_models WHERE active)
                """
            ),
            {"start": month_start, "end": month_end},
        ).mappings().one()
        day_row = conn.execute(
            text(
                """
                SELECT COALESCE(SUM(cost_micro_usd), 0) AS cost, COUNT(*) AS calls
                FROM ai_usage_events
                WHERE occurred_at >= :start AND occurred_at < :end
                  AND model_key IN (SELECT model_key FROM ai_models WHERE active)
                """
            ),
            {"start": day_start, "end": now},
        ).mappings().one()
        by_model = conn.execute(
            text(
                """
                SELECT m.model_key,
                       COUNT(e.id) AS calls,
                       COALESCE(SUM(e.input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(e.output_tokens), 0) AS output_tokens,
                       COALESCE(SUM(e.embedding_tokens), 0) AS embedding_tokens,
                       COALESCE(SUM(e.rerank_tokens), 0) AS rerank_tokens,
                       COALESCE(SUM(e.cost_micro_usd), 0) AS cost
                FROM ai_models m
                LEFT JOIN ai_usage_events e
                  ON e.model_key = m.model_key
                 AND e.occurred_at >= :start AND e.occurred_at < :end
                WHERE m.active = TRUE
                GROUP BY m.model_key
                ORDER BY cost DESC, m.model_key
                """
            ),
            {"start": month_start, "end": month_end},
        ).mappings().all()
        by_stage = conn.execute(
            text(
                """
                SELECT stage,
                       COUNT(*) AS calls,
                       COALESCE(SUM(cost_micro_usd), 0) AS cost
                FROM ai_usage_events
                WHERE occurred_at >= :start AND occurred_at < :end
                  AND model_key IN (SELECT model_key FROM ai_models WHERE active)
                GROUP BY stage
                ORDER BY cost DESC, stage
                """
            ),
            {"start": month_start, "end": month_end},
        ).mappings().all()
        recent = conn.execute(
            text(
                """
                SELECT occurred_at, stage, model_key, input_tokens, output_tokens,
                       cost_micro_usd, is_peak, input_tier
                FROM ai_usage_events
                WHERE model_key IN (SELECT model_key FROM ai_models WHERE active)
                ORDER BY occurred_at DESC
                LIMIT 30
                """
            )
        ).mappings().all()
        prices = conn.execute(
            text(
                """
                SELECT m.model_key, m.display_name, m.provider, m.kind,
                       p.input_cache_hit_per_m, p.input_cache_miss_per_m,
                       p.output_per_m, p.embedding_per_m, p.rerank_per_m,
                       p.peak_multiplier, p.peak_timezone, p.peak_windows,
                       p.input_tiers, p.effective_from
                FROM ai_models m
                LEFT JOIN ai_price_versions p
                  ON p.model_id = m.id AND p.effective_to IS NULL
                WHERE m.active = TRUE
                ORDER BY m.kind, m.model_key
                """
            )
        ).mappings().all()

    spent = _usd(month_row["cost"])
    return {
        "budget_usd": MONTHLY_BUDGET_USD,
        "spent_usd": spent,
        "remaining_usd": round(max(0.0, MONTHLY_BUDGET_USD - spent), 6),
        "percent": round((spent / MONTHLY_BUDGET_USD) * 100, 2)
        if MONTHLY_BUDGET_USD
        else 0,
        "status": _budget_status(spent),
        "month_start": month_start.isoformat(),
        "month_end": month_end.isoformat(),
        "today_usd": _usd(day_row["cost"]),
        "today_calls": int(day_row["calls"]),
        "month_calls": int(month_row["calls"]),
        "tokens": {
            "input": int(month_row["input_tokens"]),
            "cached": int(month_row["cached_tokens"]),
            "output": int(month_row["output_tokens"]),
        },
        "by_model": [
            {
                "model": row["model_key"],
                "calls": int(row["calls"]),
                "input_tokens": int(row["input_tokens"]),
                "output_tokens": int(row["output_tokens"]),
                "embedding_tokens": int(row["embedding_tokens"]),
                "rerank_tokens": int(row["rerank_tokens"]),
                "cost_usd": _usd(row["cost"]),
            }
            for row in by_model
        ],
        "by_stage": [
            {"stage": row["stage"], "calls": int(row["calls"]), "cost_usd": _usd(row["cost"])}
            for row in by_stage
        ],
        "recent": [
            {
                "occurred_at": row["occurred_at"].isoformat(),
                "stage": row["stage"],
                "model": row["model_key"],
                "input_tokens": int(row["input_tokens"]),
                "output_tokens": int(row["output_tokens"]),
                "cost_usd": _usd(row["cost_micro_usd"]),
                "is_peak": bool(row["is_peak"]),
                "input_tier": row["input_tier"],
            }
            for row in recent
        ],
        "pricing": [_json_value(dict(row)) for row in prices],
    }
