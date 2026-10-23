"""Ba lớp vừa làm: tách ngưỡng · bỏ cổng khi định danh được · phủ mục ngữ cảnh.

Test chạy **không cần dịch vụ ngoài**: mọi lời gọi Elasticsearch/Qdrant/rerank đều
được thay bằng hàm giả, nên kiểm được đúng logic cổng mà không tốn token.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest
from backend.app.api import admin
from backend.app.rag import hybrid, reranker
from backend.app.rag.fact_lookup import ProcedureFact
from backend.app.rag.types import Candidate, RetrievalOutcome

MA = "1.115374"


def _cand(chi_so: int, *, section: str = "PROCESSING_TIME", code: str = MA) -> Candidate:
    return Candidate(
        chunk_id=f"chunk-{chi_so}",
        procedure_code=code,
        procedure_name="Thẩm định, phê duyệt phương án sử dụng đất",
        section_type=section,
        title=f"mục {section}",
        content=f"nội dung {section}",
        detail_url="https://example.test",
        score=1.0 / (60 + chi_so),
        source="keyword",
    )


def _gia_nhanh(monkeypatch: pytest.MonkeyPatch, *, diem_rerank: float | None) -> list[int]:
    """Thay hai nhánh tìm kiếm và rerank. Trả list đếm số lần rerank bị gọi."""
    dem: list[int] = [0]

    async def keyword_only(question, *, top_k=None, codes=None, errors=None):  # noqa: ANN001, ANN202
        return [_cand(1, section="REQUIRED_DOCUMENTS"), _cand(3, section="RESULT")]

    async def vector_only(vector, *, top_k=None, codes=None, errors=None):  # noqa: ANN001, ANN202
        return [_cand(2, section="REQUIRED_DOCUMENTS"), _cand(4, section="STEPS")]

    async def rerank(question, candidates, *, top_n=None, chunk_filter_min_score=0.0):  # noqa: ANN001, ANN202
        dem[0] += 1
        assert chunk_filter_min_score == 0.0, "cổng phải truyền lọc chunk = 0.0"
        if diem_rerank is None:
            return RetrievalOutcome(candidates=list(candidates), rerank_used=False)
        # ``Candidate`` là frozen + slots nên phải dùng ``replace``, không sửa tại chỗ.
        return RetrievalOutcome(
            candidates=[replace(candidates[0], score=diem_rerank)], rerank_used=True
        )

    monkeypatch.setattr(hybrid, "keyword_only", keyword_only)
    monkeypatch.setattr(hybrid, "vector_only", vector_only)
    monkeypatch.setattr(reranker, "rerank", rerank)
    return dem


def test_co_ma_thi_bo_cong_khong_goi_rerank(monkeypatch: pytest.MonkeyPatch) -> None:
    """Câu hỏi đã nêu mã thủ tục tồn tại → mặc nhiên trong phạm vi, KHÔNG được gọi rerank."""
    dem = _gia_nhanh(monkeypatch, diem_rerank=0.10)

    ket_qua = asyncio.run(hybrid.hybrid("q", vector=[0.1], codes=[MA], use_gate=True))

    assert ket_qua.refused is False
    assert ket_qua.gate_skipped is True
    assert ket_qua.gate_score is None
    assert dem[0] == 0, "đã định danh được thì không được tốn một lượt gọi rerank"


def test_khong_co_ma_thi_cong_van_chay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Không định danh được → cổng phải chấm, và chặn khi điểm dưới ngưỡng."""
    dem = _gia_nhanh(monkeypatch, diem_rerank=0.10)

    ket_qua = asyncio.run(
        hybrid.hybrid("q", vector=[0.1], codes=[], use_gate=True, gate_min_score=0.60)
    )

    assert dem[0] == 1
    assert ket_qua.refused is True
    assert ket_qua.gate_skipped is False
    assert ket_qua.candidates == []
    assert ket_qua.gate_score == pytest.approx(0.10)


def test_cong_khong_cham_duoc_thi_cho_di(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rerank lỗi (fail open): không chặn câu hỏi chỉ vì API ngoài hỏng."""
    _gia_nhanh(monkeypatch, diem_rerank=None)

    ket_qua = asyncio.run(
        hybrid.hybrid("q", vector=[0.1], codes=[], use_gate=True, gate_min_score=0.60)
    )

    assert ket_qua.refused is False
    assert ket_qua.gate_skipped is False
    assert ket_qua.gate_score is None
    assert ket_qua.candidates, "phải trả về danh sách thay vì chặn"


def test_hai_nguong_la_hai_bien_khac_nhau() -> None:
    """Cổng và lọc chunk phải là hai cấu hình riêng — không được dùng lẫn."""
    from backend.app.config import Settings

    ten = set(Settings.model_fields)
    assert "reranker_gate_min_score" in ten
    assert "chunk_filter_min_score" in ten
    assert "reranker_min_score" not in ten, "khoá cũ phải biến mất để không ai truyền nhầm"
    assert Settings.model_fields["chunk_filter_min_score"].default == 0.0


def test_coverage_liet_ke_muc_co_va_thieu(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ngữ cảnh có 1 mục, thủ tục có 3 mục → phải nói rõ còn thiếu 2."""

    async def get_facts(codes: list[str]) -> list[ProcedureFact]:
        return [
            ProcedureFact(
                ma_thu_tuc=MA,
                ten_thu_tuc="X",
                cap_thuc_hien=("Cấp tỉnh",),
                co_quan_ban_hanh="UBND tỉnh Gia Lai",
                so_quyet_dinh="2758/QĐ-UBND",
                detail_url="u",
                muc_co=("PROCESSING_TIME", "REQUIRED_DOCUMENTS", "RESULT"),
            )
        ]

    monkeypatch.setattr(admin.fact_lookup, "get_facts", get_facts)

    hien_co = [_cand(1, section="RESULT"), _cand(2, section="RESULT")]
    co, thieu = asyncio.run(admin._coverage([MA], hien_co))

    assert co == ["RESULT"]
    assert thieu == ["PROCESSING_TIME", "REQUIRED_DOCUMENTS"]


def test_coverage_bo_qua_doan_cua_thu_tuc_khac(monkeypatch: pytest.MonkeyPatch) -> None:
    """Đoạn của thủ tục khác không được tính là 'đã có mục' của thủ tục này."""

    async def get_facts(codes: list[str]) -> list[ProcedureFact]:
        return [
            ProcedureFact(
                ma_thu_tuc=MA,
                ten_thu_tuc="X",
                cap_thuc_hien=(),
                co_quan_ban_hanh="",
                so_quyet_dinh="",
                detail_url="",
                muc_co=("RESULT",),
            )
        ]

    monkeypatch.setattr(admin.fact_lookup, "get_facts", get_facts)

    co, thieu = asyncio.run(admin._coverage([MA], [_cand(1, section="RESULT", code="1.999999")]))

    assert co == []
    assert thieu == ["RESULT"]


def test_coverage_khong_co_ma_thi_rong() -> None:
    assert asyncio.run(admin._coverage([], [_cand(1)])) == ([], [])


def test_ma_sai_trong_cau_khong_duoc_bo_cong(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mã **không tồn tại** vẫn phải chấm cổng — lỗi đã đo được.

    ``hybrid`` từng tự ``extract_codes`` bằng regex rồi coi mã khớp hình dạng là "đã định
    danh", nên câu *"thủ tục 9.999999 cần gì"* **bỏ qua cổng**. Mã đúng/sai chỉ trả lời được
    bằng bảng ``procedures``, không bằng hình dạng chuỗi.
    """
    dem = _gia_nhanh(monkeypatch, diem_rerank=0.30)

    ket_qua = asyncio.run(
        hybrid.hybrid(
            "Thủ tục 9.999999 cần những giấy tờ gì?", vector=[0.1], codes=None, use_gate=True
        )
    )

    assert dem[0] == 1, "mã sai vẫn phải chấm cổng"
    assert ket_qua.gate_skipped is False
    assert ket_qua.gate_score == pytest.approx(0.30)
    assert ket_qua.refused is True


def test_ma_da_xac_thuc_thi_van_bo_cong(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mã có thật (tầng trên tra ra) → không tốn lượt rerank nào."""
    dem = _gia_nhanh(monkeypatch, diem_rerank=0.30)

    ket_qua = asyncio.run(
        hybrid.hybrid("Thủ tục 1.115374 cần gì?", vector=[0.1], codes=[MA], use_gate=True)
    )

    assert dem[0] == 0
    assert ket_qua.gate_skipped is True