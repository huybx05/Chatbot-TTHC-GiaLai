from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from backend.app.cost.pricing import (
    PriceVersion,
    calculate_cost,
    canonical_model_key,
    is_peak,
)
from backend.app.cost.service import _budget_status

TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def _deepseek() -> PriceVersion:
    return PriceVersion(
        id=1,
        model_key="deepseek-v4.1-flash",
        kind="llm",
        input_cache_hit_per_m=Decimal("0.003"),
        input_cache_miss_per_m=Decimal("0.15"),
        output_per_m=Decimal("0.60"),
        embedding_per_m=None,
        rerank_per_m=None,
        peak_multiplier=Decimal("2"),
        peak_timezone="Asia/Ho_Chi_Minh",
        peak_windows=(("07:30", "23:30"),),
        input_tiers=(),
    )


def _qwen() -> PriceVersion:
    return PriceVersion(
        id=2,
        model_key="qwen3.7-flash",
        kind="llm",
        input_cache_hit_per_m=None,
        input_cache_miss_per_m=None,
        output_per_m=None,
        embedding_per_m=None,
        rerank_per_m=None,
        peak_multiplier=Decimal("1"),
        peak_timezone="Asia/Ho_Chi_Minh",
        peak_windows=(),
        input_tiers=(
            {"max_input_tokens": 32000, "input_per_m": 0.03, "output_per_m": 0.13},
            {"max_input_tokens": 256000, "input_per_m": 0.10, "output_per_m": 0.40},
            {"max_input_tokens": 1000000, "input_per_m": 0.20, "output_per_m": 0.80},
        ),
    )


def test_deepseek_off_peak_uses_cache_hit_and_miss() -> None:
    result = calculate_cost(
        _deepseek(),
        input_tokens=2000,
        cached_tokens=1000,
        output_tokens=500,
        at=datetime(2026, 11, 1, 2, 0, tzinfo=TZ),
    )

    assert result.is_peak is False
    # 1000*0.15 + 1000*0.003 + 500*0.60 = 453 micro-USD
    assert result.cost_micro_usd == 453


def test_deepseek_peak_applies_multiplier() -> None:
    result = calculate_cost(
        _deepseek(),
        input_tokens=2000,
        cached_tokens=1000,
        output_tokens=500,
        at=datetime(2026, 11, 1, 8, 0, tzinfo=TZ),
    )

    assert result.is_peak is True
    assert result.cost_micro_usd == 906


def test_peak_boundaries() -> None:
    price = _deepseek()
    assert is_peak(datetime(2026, 11, 1, 7, 29, tzinfo=TZ), price) is False
    assert is_peak(datetime(2026, 11, 1, 7, 30, tzinfo=TZ), price) is True
    assert is_peak(datetime(2026, 11, 1, 23, 30, tzinfo=TZ), price) is False


def test_qwen_uses_input_length_tier() -> None:
    price = _qwen()

    first = calculate_cost(
        price,
        input_tokens=1000,
        output_tokens=100,
        at=datetime(2026, 11, 1, 8, 0, tzinfo=TZ),
    )
    second = calculate_cost(
        price,
        input_tokens=40000,
        output_tokens=100,
        at=datetime(2026, 11, 1, 8, 0, tzinfo=TZ),
    )

    assert first.cost_micro_usd == 43  # 30 + 13
    assert first.input_tier == "32000"
    assert second.cost_micro_usd == 4040  # 4000 + 40
    assert second.input_tier == "256000"


def test_embedding_and_rerank_prices() -> None:
    embedding = PriceVersion(
        id=3,
        model_key="qwen3.7-text-embedding",
        kind="embedding",
        input_cache_hit_per_m=None,
        input_cache_miss_per_m=None,
        output_per_m=None,
        embedding_per_m=Decimal("0.07"),
        rerank_per_m=None,
        peak_multiplier=Decimal("1"),
        peak_timezone="Asia/Ho_Chi_Minh",
        peak_windows=(),
        input_tiers=(),
    )
    rerank = PriceVersion(
        id=4,
        model_key="qwen3-rerank",
        kind="rerank",
        input_cache_hit_per_m=None,
        input_cache_miss_per_m=None,
        output_per_m=None,
        embedding_per_m=None,
        rerank_per_m=Decimal("0.10"),
        peak_multiplier=Decimal("1"),
        peak_timezone="Asia/Ho_Chi_Minh",
        peak_windows=(),
        input_tiers=(),
    )

    assert calculate_cost(
        embedding,
        embedding_tokens=5000,
        at=datetime(2026, 11, 1, 8, 0, tzinfo=TZ),
    ).cost_micro_usd == 350
    assert calculate_cost(
        rerank,
        rerank_tokens=3000,
        at=datetime(2026, 11, 1, 8, 0, tzinfo=TZ),
    ).cost_micro_usd == 300


def test_budget_thresholds_are_warning_only() -> None:
    assert _budget_status(0) == "normal"
    assert _budget_status(10) == "notice"
    assert _budget_status(16) == "warning"
    assert _budget_status(20) == "over"
    assert _budget_status(25) == "over"


def test_canonical_model_names() -> None:
    assert canonical_model_key("deepseek-ai/DeepSeek-V4.1-Flash-1017") == "deepseek-v4.1-flash"
    assert canonical_model_key("qwen3.7-flash") == "qwen3.7-flash"
    assert canonical_model_key("qwen3.7-text-embedding") == "qwen3.7-text-embedding"
    assert canonical_model_key("qwen3-rerank") == "qwen3-rerank"
