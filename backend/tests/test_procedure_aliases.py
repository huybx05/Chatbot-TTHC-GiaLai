"""Alias mã thành phần cũ → mã hiện hành."""

from __future__ import annotations

from backend.app.rag.procedure_aliases import (
    load_procedure_aliases,
    resolve_procedure_alias,
)


def test_alias_map_doc_tu_config() -> None:
    aliases = load_procedure_aliases()

    assert aliases["1.002535"] == "1.014137"
    assert aliases["1.004222"] == "1.116788"
    assert aliases["1.003197"] == "1.116788"


def test_ma_khong_co_alias_duoc_giu_nguyen() -> None:
    assert resolve_procedure_alias("2.002621") == "2.002621"
    assert resolve_procedure_alias("1.014137") == "1.014137"


def test_alias_chuan_hoa_dau_phay() -> None:
    assert resolve_procedure_alias("1,002535") == "1.014137"
