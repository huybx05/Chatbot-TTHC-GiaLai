"""Khoá hành vi tầng định danh thủ tục. Không cần Neo4j/Qdrant/PostgreSQL."""

from __future__ import annotations

import asyncio

import pytest
from backend.app.rag import resolver
from backend.app.rag.types import Candidate


def _chunk(ma: str, ten: str, diem: float, section: str = "GENERAL_INFO") -> Candidate:
    return Candidate(
        chunk_id=f"{ma}-{section}-{diem}",
        procedure_code=ma,
        procedure_name=ten,
        section_type=section,
        title=section,
        content="nội dung",
        detail_url="",
        score=diem,
        source="vector",
    )


def _run(question: str, hits: list[Candidate], codes: list[str] | None = None, names=None):
    """Chạy resolver với tên và vector giả — không gọi mạng."""

    async def fake_names() -> dict[str, str]:
        return names if names is not None else {c.procedure_code: c.procedure_name for c in hits}

    async def fake_vector_only(vector, *, top_k=10, codes=None):  # noqa: A002
        return hits

    goi = {"n": 0}

    async def get_vector() -> list[float]:
        goi["n"] += 1
        return [0.0] * 8

    doi_names = resolver.procedure_names
    doi_vector = resolver.hybrid.vector_only
    resolver.procedure_names = fake_names
    resolver.hybrid.vector_only = fake_vector_only
    try:
        ket_qua = asyncio.run(
            resolver.resolve_procedure(question, codes=codes, get_vector=get_vector)
        )
        return ket_qua, goi["n"]
    finally:
        resolver.procedure_names = doi_names
        resolver.hybrid.vector_only = doi_vector


# ── Đường rẻ: không được nhúng ───────────────────────────────────────────


def test_co_ma_thi_khong_nhung() -> None:
    kq, so_lan = _run("thủ tục 1.115374 do cơ quan nào ban hành", [], codes=["1.115374"])
    assert kq.code == "1.115374"
    assert kq.method == "code"
    assert kq.confidence == 1.0
    assert so_lan == 0, "có mã rồi thì không được nhúng câu hỏi"


def test_khop_nguyen_ten_thi_khong_nhung() -> None:
    ten = "Thủ tục cấp Giấy xác nhận tình trạng hôn nhân"
    kq, so_lan = _run(
        "Tôi muốn hỏi về thủ tục cấp Giấy xác nhận tình trạng hôn nhân",
        [],
        names={"1.004873": ten},
    )
    assert kq.code == "1.004873"
    assert kq.method == "exact_name"
    assert so_lan == 0, "khớp nguyên tên thì không được nhúng"


def test_ten_khop_khong_dau_va_khac_hoa_thuong() -> None:
    kq, so_lan = _run(
        "thu tuc cap giay xac nhan tinh trang hon nhan",
        [],
        names={"1.004873": "Thủ tục cấp Giấy xác nhận tình trạng hôn nhân"},
    )
    assert kq.code == "1.004873"
    assert so_lan == 0


# ── Đường vector: chính sách "1 thủ tục ở top-5" + hai ngưỡng ────────────


def test_vector_mot_thu_tuc_diem_cao_thi_nhan() -> None:
    hits = [
        _chunk("1.004873", "Giấy xác nhận tình trạng hôn nhân", 0.72 - 0.01 * i) for i in range(5)
    ]
    kq, so_lan = _run("giấy xác nhận độc thân", hits)
    assert so_lan == 1, "phải nhúng đúng một lần"
    assert kq.code == "1.004873"
    assert kq.method == "vector"
    assert not kq.ambiguous


def test_diem_duoi_nguong_nhan_thi_khong_moi_chon() -> None:
    """0,57 nằm giữa sàn 0,55 và ngưỡng nhận 0,60 → **không nhận**, và **không mời chọn**.

    Trước đây trường hợp này bị gọi là "mơ hồ" nên hệ thống mời người dùng chọn trong vài thủ
    tục — trong khi không thủ tục nào đủ khớp. Đo được hai ca thật bị lỗi này: *"Hồ sơ làm
    giấy khai sinh gồm những gì"* (0,5779) và *"Thủ tục cấp phép bán rượu cần gì"* (0,5583) —
    cả hai mời chọn 3 thủ tục **không liên quan**.

    Mời chọn một danh sách mình không tin là tệ hơn nói "chưa xác định được".
    """
    hits = [_chunk("1.115350", "Cấp lại Giấy chứng nhận", 0.57 - 0.01 * i) for i in range(5)]
    kq, _ = _run("sổ đỏ bị rách", hits)
    assert kq.code is None
    assert not kq.ambiguous, "chưa đủ chắc thì không được mời chọn"
    assert not kq.alternatives, "không đưa lựa chọn mà mình không tin"
    assert "ngưỡng" in kq.note


def test_hai_thu_tuc_sat_nhau_thi_that_su_mo_ho() -> None:
    """Trên ngưỡng nhưng chênh nhau < 0,02 → mơ hồ thật, phải hỏi lại."""
    hits = [
        _chunk("1.115350", "Cấp lại Giấy chứng nhận", 0.6075),
        _chunk("1.115345", "Cấp đổi Giấy chứng nhận", 0.6044),
    ]
    kq, _ = _run("đổi sổ đỏ bị rách", hits)
    assert kq.code is None
    assert kq.ambiguous
    assert len(kq.alternatives) == 2


def test_thu_tuc_dau_vuot_xa_thi_nhan_du_top5_co_nhieu_thu_tuc() -> None:
    """Câu nêu rõ tên thủ tục vẫn có 3–4 thủ tục khác trong top-5 vì chúng dùng chung từ.

    Thủ tục đầu vượt xa thì phải **nhận**, không được hỏi lại — đây là lỗi làm câu hỏi rõ
    ràng bị biến thành câu hỏi lại.
    """
    hits = [
        _chunk("1.115350", "Cấp lại Giấy chứng nhận do bị mất", 0.6627),
        _chunk("1.115345", "Cấp đổi Giấy chứng nhận", 0.6100),
        _chunk("1.115346", "Đăng ký, cấp Giấy chứng nhận", 0.6050),
    ]
    kq, _ = _run("mất sổ đỏ xin cấp lại", hits)
    assert kq.code == "1.115350"
    assert not kq.ambiguous
    assert "vượt" in kq.note


def test_duoi_san_thi_coi_nhu_ngoai_pham_vi() -> None:
    """0,50 < sàn 0,55 → không phải 'mơ hồ', mà là 'không nói về thủ tục nào'."""
    hits = [_chunk("1.115343", "Tách thửa hoặc hợp thửa đất", 0.50 - 0.01 * i) for i in range(5)]
    kq, _ = _run("thời tiết Gia Lai hôm nay thế nào", hits)
    assert kq.code is None
    assert not kq.ambiguous, "ngoài phạm vi thì không được mời chọn thủ tục"


def test_hai_thu_tuc_trong_top_5_thi_hoi_lai() -> None:
    hits = [
        _chunk("1.115350", "Cấp lại Giấy chứng nhận do bị mất", 0.78),
        _chunk("1.115345", "Cấp đổi Giấy chứng nhận", 0.77),
        _chunk("1.115350", "Cấp lại Giấy chứng nhận do bị mất", 0.70, "RESULT"),
    ]
    kq, _ = _run("đổi sổ đỏ bị rách cũ", hits)
    assert kq.code is None
    assert kq.ambiguous
    assert {ma for ma, _ten, _d in kq.alternatives} == {"1.115350", "1.115345"}


def test_hai_thu_tuc_nhung_thu_tu_hai_ben_top_5_van_nhan() -> None:
    """Thủ tục thứ hai chỉ xuất hiện ở đoạn thứ 6 → top-5 vẫn chỉ có một."""
    hits = [
        _chunk("1.004873", "Giấy xác nhận tình trạng hôn nhân", 0.70 - 0.01 * i) for i in range(5)
    ]
    hits.append(_chunk("1.001699", "Giấy xác nhận khuyết tật", 0.40, "GENERAL_INFO"))
    kq, _ = _run("giấy xác nhận độc thân", hits)
    assert kq.code == "1.004873"
    assert not kq.ambiguous


def test_vector_loi_thi_khong_nem() -> None:
    async def fake_names() -> dict[str, str]:
        return {}

    async def no_hong(vector, *, top_k=10, codes=None):  # noqa: A002
        raise RuntimeError("Qdrant sập")

    async def get_vector() -> list[float]:
        return [0.0] * 8

    doi_names, doi_vector = resolver.procedure_names, resolver.hybrid.vector_only
    resolver.procedure_names, resolver.hybrid.vector_only = fake_names, no_hong
    try:
        kq = asyncio.run(
            resolver.resolve_procedure("giấy xác nhận độc thân", get_vector=get_vector)
        )
    finally:
        resolver.procedure_names, resolver.hybrid.vector_only = doi_names, doi_vector

    assert kq.code is None
    assert not kq.ambiguous
    assert "lỗi" in kq.note.lower()


# ── LazyQuestionVector: một lần nhúng cho mỗi câu ────────────────────────


@pytest.mark.parametrize("so_lan_goi", [1, 2, 3])
def test_lazy_vector_chi_nhung_mot_lan(so_lan_goi: int, monkeypatch) -> None:
    dem = {"n": 0}

    async def fake_embed(text: str) -> list[float]:
        dem["n"] += 1
        return [float(len(text))] * 4

    monkeypatch.setattr(resolver.embeddings, "embed", fake_embed)

    lazy = resolver.LazyQuestionVector("câu hỏi thử")
    assert not lazy.used

    async def chay() -> None:
        for _ in range(so_lan_goi):
            await lazy.get()

    asyncio.run(chay())
    assert dem["n"] == 1, f"gọi get() {so_lan_goi} lần vẫn chỉ được nhúng 1 lần"
    assert lazy.used
