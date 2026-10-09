"""Đọc cấu hình crawler từ ``config/crawler.yaml``."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "crawler.yaml"

# Cấu hình mặc định, dùng khi file yaml thiếu khóa.
DEFAULTS: dict[str, Any] = {
    "base_url": "https://dichvucong.gov.vn",
    "delay_seconds": 1.5,
    "limit": None,
    "code_filter": None,
    "cookie": "",
    "catalog_excel": "danh_sach_tthc_bo_tinh_xa_edit.xlsx",
    "catalog_sheet": "TTHC",
    "legal_sheet": "CCPL",
    "paths": {
        "raw": "data/raw/api",
        "normalized": "data/json",
        "failed": "data/failed",
        "manifest": "data/processed/procedure_manifest.csv",
    },
}


@dataclass(frozen=True)
class CrawlerPaths:
    raw: Path
    normalized: Path
    failed: Path
    manifest: Path


@dataclass(frozen=True)
class CrawlerConfig:
    base_url: str
    delay_seconds: float
    limit: int | None
    code_filter: list[str] | None
    cookie: str
    catalog_excel: Path
    catalog_sheet: str
    legal_sheet: str
    paths: CrawlerPaths = field(default_factory=lambda: _paths(DEFAULTS["paths"]))


def _paths(raw: dict[str, str]) -> CrawlerPaths:
    return CrawlerPaths(
        raw=REPO_ROOT / raw["raw"],
        normalized=REPO_ROOT / raw["normalized"],
        failed=REPO_ROOT / raw["failed"],
        manifest=REPO_ROOT / raw["manifest"],
    )


def _env_override(key: str, value: Any) -> Any:
    """Cho phép ghi đè bằng biến môi trường CRAWLER_<KEY>."""
    env_name = f"CRAWLER_{key.upper()}"
    override = os.getenv(env_name)
    if override is None:
        return value

    if key in {"limit"}:
        return int(override) if override.strip() else None
    if key == "delay_seconds":
        return float(override)
    return override


@lru_cache
def load_config() -> CrawlerConfig:
    """Đọc cấu hình một lần cho cả tiến trình."""
    merged: dict[str, Any] = dict(DEFAULTS)

    if CONFIG_PATH.exists():
        with CONFIG_PATH.open(encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
        merged.update(loaded)
        if "paths" in loaded:
            merged["paths"] = {**DEFAULTS["paths"], **loaded["paths"]}

    cookie = os.getenv("DVC_COOKIE") or _env_override("cookie", merged.get("cookie", ""))
    code_filter = merged.get("code_filter") or None
    limit = _env_override("limit", merged.get("limit"))

    return CrawlerConfig(
        base_url=_env_override("base_url", merged["base_url"]),
        delay_seconds=float(_env_override("delay_seconds", merged["delay_seconds"])),
        limit=int(limit) if limit is not None else None,
        code_filter=list(code_filter) if code_filter else None,
        cookie=str(cookie or ""),
        catalog_excel=REPO_ROOT / str(_env_override("catalog_excel", merged["catalog_excel"])),
        catalog_sheet=str(merged["catalog_sheet"]),
        legal_sheet=str(merged["legal_sheet"]),
        paths=_paths(merged["paths"]),
    )
