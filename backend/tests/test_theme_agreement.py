"""Giai đoạn 3 — quyết định khi cả nhóm thủ tục trả lời được.

Dùng hàm thuần + dữ liệu giả, không gọi mô hình, không chạm DB thật.
"""

from __future__ import annotations

import asyncio

from backend.app.rag import grounding, theme_agreement, themes


def _theme(canonical: str = "1.115362") -> themes.Theme:
    return themes.Theme(
        theme_id="dang_ky_bien_dong",
        label="Đăng ký biến động",
        canonical_code=canonical,
        members=("1.115348", "1.115362", "1.115366"),
    )


def _index(theme: themes.Theme) -> themes.ThemeIndex:
    return themes.ThemeIndex([theme])


def _rows(value_by_code: dict[str, str]) -> list[dict]:
    return [
        {
            "procedure_code": code,
            "content": f"Tên thủ tục: … Lĩnh vực: Đất đai --- {value}",
        }
        for code, value in value_by_code.items()
    ]


def _patch(monkeypatch, theme: themes.Theme, rows: list[dict]) -> None:
    async def fake_load(*_args, **_kwargs):
        return _index(theme)

    async def fake_sections(codes, facet):
        return rows, ""

    monkeypatch.setattr(theme_agreement.themes, "load", fake_load)
    monkeypatch.setattr(theme_agreement.sections, "theo_khia_canh_checked", fake_sections)


def test_dong_thuan_thi_tra_loi_mot_lan(monkeypatch) -> None:
    theme = _theme()
    _patch(
        monkeypatch,
        theme,
        _rows({code: "Giấy chứng nhận quyền sử dụng đất" for code in theme.members}),
    )
    decision = asyncio.run(
        theme_agreement.resolve_theme(["1.115362", "1.115366"], "result")
    )
    assert decision is not None
    assert decision.reason == "agreement"
    assert decision.code == "1.115362"
    assert decision.members == 3


def test_khac_nhau_thi_dung_dai_dien(monkeypatch) -> None:
    theme = _theme()
    _patch(
        monkeypatch,
        theme,
        _rows({"1.115348": "6,5 ngày", "1.115362": "17,5 ngày", "1.115366": "14 ngày"}),
    )
    decision = asyncio.run(
        theme_agreement.resolve_theme(["1.115362", "1.115366"], "processing_time")
    )
    assert decision is not None
    assert decision.reason == "canonical"
    assert decision.code == "1.115362"


def test_khac_nhau_va_khong_co_dai_dien_thi_khong_quyet_dinh(monkeypatch) -> None:
    theme = _theme(canonical="")
    _patch(
        monkeypatch,
        theme,
        _rows({"1.115348": "a", "1.115362": "b", "1.115366": "c"}),
    )
    assert (
        asyncio.run(theme_agreement.resolve_theme(["1.115362", "1.115366"], "processing_time"))
        is None
    )


def test_thieu_noi_dung_thi_khong_dong_thuan(monkeypatch) -> None:
    theme = _theme(canonical="")
    _patch(monkeypatch, theme, _rows({"1.115362": "x"}))
    assert asyncio.run(theme_agreement.resolve_theme(["1.115362", "1.115366"], "result")) is None


def test_facet_khong_so_sanh_duoc_thi_bo_qua(monkeypatch) -> None:
    _patch(monkeypatch, _theme(), _rows({}))
    assert (
        asyncio.run(theme_agreement.resolve_theme(["1.115362", "1.115366"], "issuing_agency"))
        is None
    )


def test_hai_ma_khac_nhom_thi_khong_quyet_dinh(monkeypatch) -> None:
    _patch(monkeypatch, _theme(), _rows({}))
    assert asyncio.run(theme_agreement.resolve_theme(["1.115362", "1.115342"], "result")) is None


# ── nối vào grounding ─────────────────────────────────────────────────────


def _item() -> grounding.SubjectGrounding:
    return grounding.SubjectGrounding(
        index=0,
        status="ambiguous",
        type="procedure",
        mention="đăng ký biến động đất đai",
        alternatives=[{"code": "1.115362"}, {"code": "1.115366"}],
    )


def test_grounding_resolved_khi_nhom_quyet_dinh(monkeypatch) -> None:
    async def fake(_codes, _facet):
        return theme_agreement.ThemeDecision(
            code="1.115362",
            name="Đăng ký biến động",
            reason="agreement",
            theme_id="dang_ky_bien_dong",
            theme_label="Đăng ký biến động",
            members=6,
            note="nhóm đồng thuận",
        )

    monkeypatch.setattr(grounding.theme_agreement, "resolve_theme", fake)
    item = _item()
    frame = {"requests": [{"facet": "result", "subject_ref": 0}]}
    asyncio.run(grounding._apply_theme_agreement([item], frame))  # noqa: SLF001
    assert item.status == "resolved"
    assert item.code == "1.115362"
    assert item.method == "theme"


def test_grounding_giu_ambiguous_khi_nhom_khong_quyet_dinh(monkeypatch) -> None:
    async def fake(_codes, _facet):
        return None

    monkeypatch.setattr(grounding.theme_agreement, "resolve_theme", fake)
    item = _item()
    frame = {"requests": [{"facet": "result", "subject_ref": 0}]}
    asyncio.run(grounding._apply_theme_agreement([item], frame))  # noqa: SLF001
    assert item.status == "ambiguous"
