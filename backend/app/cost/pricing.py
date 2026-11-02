"""Pricing and cost calculation for third-party AI models."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class PriceVersion:
    id: int
    model_key: str
    kind: str
    input_cache_hit_per_m: Decimal | None
    input_cache_miss_per_m: Decimal | None
    output_per_m: Decimal | None
    embedding_per_m: Decimal | None
    rerank_per_m: Decimal | None
    peak_multiplier: Decimal
    peak_timezone: str
    peak_windows: tuple[tuple[str, str], ...]
    input_tiers: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class CostResult:
    cost_micro_usd: int
    price_version_id: int | None
    is_peak: bool
    input_tier: str


def canonical_model_key(model: str) -> str:
    """Map tên model thực tế từ provider về khóa giá nội bộ."""
    value = (model or "").strip().lower()
    if "deepseek" in value:
        return "deepseek-v4.1-flash"
    if "embedding" in value:
        return "qwen3.7-text-embedding"
    if "rerank" in value:
        return "qwen3-rerank"
    if "qwen" in value and "flash" in value:
        return "qwen3.7-flash"
    return value


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _parse_windows(value: Any) -> tuple[tuple[str, str], ...]:
    windows: list[tuple[str, str]] = []
    for item in _json_list(value):
        if not isinstance(item, dict):
            continue
        start = str(item.get("start") or "").strip()
        end = str(item.get("end") or "").strip()
        if start and end:
            windows.append((start, end))
    return tuple(windows)


def to_price_version(row: dict[str, Any]) -> PriceVersion:
    return PriceVersion(
        id=int(row["id"]),
        model_key=str(row["model_key"]),
        kind=str(row["kind"]),
        input_cache_hit_per_m=_decimal(row.get("input_cache_hit_per_m")),
        input_cache_miss_per_m=_decimal(row.get("input_cache_miss_per_m")),
        output_per_m=_decimal(row.get("output_per_m")),
        embedding_per_m=_decimal(row.get("embedding_per_m")),
        rerank_per_m=_decimal(row.get("rerank_per_m")),
        peak_multiplier=_decimal(row.get("peak_multiplier")) or Decimal("1"),
        peak_timezone=str(row.get("peak_timezone") or "Asia/Ho_Chi_Minh"),
        peak_windows=_parse_windows(row.get("peak_windows")),
        input_tiers=tuple(
            item for item in _json_list(row.get("input_tiers")) if isinstance(item, dict)
        ),
    )


def is_peak(at: datetime, price: PriceVersion) -> bool:
    if not price.peak_windows or price.peak_multiplier == Decimal("1"):
        return False
    local = at.astimezone(ZoneInfo(price.peak_timezone))
    minute = local.hour * 60 + local.minute

    def parse_clock(value: str) -> int:
        hour, minute_text = value.split(":", 1)
        return int(hour) * 60 + int(minute_text)

    for start_text, end_text in price.peak_windows:
        start = parse_clock(start_text)
        end = parse_clock(end_text)
        if start <= end:
            if start <= minute < end:
                return True
        elif minute >= start or minute < end:
            return True
    return False


def _micro(tokens: int, price: Decimal | None) -> int:
    if tokens <= 0 or price is None:
        return 0
    # price là USD / 1M token; tokens × price = micro-USD.
    return int(
        (Decimal(tokens) * price).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )


def calculate_cost(
    price: PriceVersion,
    *,
    input_tokens: int = 0,
    cached_tokens: int = 0,
    output_tokens: int = 0,
    embedding_tokens: int = 0,
    rerank_tokens: int = 0,
    at: datetime,
) -> CostResult:
    peak = is_peak(at, price)
    multiplier = price.peak_multiplier if peak else Decimal("1")
    input_tier = ""

    if price.kind == "embedding":
        cost = _micro(embedding_tokens or input_tokens, price.embedding_per_m)
    elif price.kind == "rerank":
        cost = _micro(rerank_tokens or input_tokens, price.rerank_per_m)
    elif price.input_tiers:
        tier: dict[str, Any] | None = None
        for item in price.input_tiers:
            max_input = item.get("max_input_tokens")
            if max_input is None or input_tokens <= int(max_input):
                tier = item
                break
        if tier is None:
            tier = price.input_tiers[-1]
        input_tier = str(tier.get("max_input_tokens") or "unlimited")
        cost = _micro(input_tokens, _decimal(tier.get("input_per_m"))) + _micro(
            output_tokens, _decimal(tier.get("output_per_m"))
        )
    else:
        cached = max(0, min(cached_tokens, input_tokens))
        uncached = max(0, input_tokens - cached)
        cost = (
            _micro(cached, price.input_cache_hit_per_m)
            + _micro(uncached, price.input_cache_miss_per_m)
            + _micro(output_tokens, price.output_per_m)
        )

    if peak:
        cost = int(
            (Decimal(cost) * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    return CostResult(
        cost_micro_usd=cost,
        price_version_id=price.id,
        is_peak=peak,
        input_tier=input_tier,
    )
