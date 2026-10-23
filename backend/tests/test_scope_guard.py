"""Hai lớp chặn **sớm** ở bước ``neo``: tỉnh khác và mã thủ tục không tồn tại.

Cả hai từng được trả lời như thật vì chúng không phải câu "lộ liễu" ngoài phạm vi — chúng
**trông giống hệt** câu hợp lệ. Cổng nội dung không cứu được:

* *"thủ tục cấp GCN QSDĐ ở Đắk Lắk"* — nội dung trùng với thủ tục Gia Lai (cùng biểu mẫu);
* *"thủ tục 1.999999 nộp ở đâu"* — mã khớp hình dạng; muốn biết sai phải tra bảng.

Điều đúng ở đây là **kết luận bằng dữ liệu đóng**, không bằng điểm liên quan.

Các bài kiểm chạy **không cần dịch vụ ngoài**: ``resolve`` và ``scope`` được thay bằng hàm giả.
"""

from __future__ import annotations

import asyncio

import pytest
from backend.app.rag import resolve, scope
from backend.app.workflow import graph
from backend.app.workflow.state import BranchSignal, Outcome, new_state

# ── Mô-đun phạm vi ──────────────────────────────────────────────────────


def test_phat_hien_tinh_khac() -> None:
    assert scope.tinh_khac("thủ tục cấp sổ đỏ ở Đắk Lắk cần gì") == "Đắk Lắk"
    assert scope.tinh_khac("đăng ký khai sinh ở Hà Nội") == "Hà Nội"


def test_khong_bao_gia_lai_la_tinh_khac() -> None:
    """Câu hỏi về Gia Lai là **trong** phạm vi — không được chặn."""
    assert scope.tinh_khac("thủ tục cấp sổ đỏ ở Gia Lai cần gì") is None
    assert scope.tinh_khac("lệ phí cấp giấy chứng nhận an toàn thực phẩm") is None


def test_khop_tinh_khong_phu_thuoc_dau() -> None:
    """Người dùng gõ không dấu vẫn phải nhận ra."""
    assert scope.tinh_khac("thu tuc o dak lak") == "Đắk Lắk"


def test_cau_tu_choi_ma_hien_dung_dang_co_dau_cham() -> None:
    """Mã trong câu từ chối phải giống mã người dùng gõ, không phải chuỗi số trần."""
    cau = scope.cau_tu_choi_ma(["1999999"])
    assert "1.999999" in cau
    assert "1999999 " not in cau


# ── Chặn sớm ở ``neo`` ──────────────────────────────────────────────────


def _gia_neo(monkeypatch: pytest.MonkeyPatch, ket_qua: resolve.Resolution) -> dict:
    rong = dict(ket_qua.state_patch())

    async def fake_resolve(_cau: str, *, only_anchors: bool = False, **kwargs):  # noqa: ANN001, ANN202
        assert only_anchors is True, "neo chỉ được tra neo, không nhúng"
        return ket_qua

    monkeypatch.setattr(resolve, "resolve", fake_resolve)
    return rong


def test_neo_chan_ma_khong_ton_tai(monkeypatch: pytest.MonkeyPatch) -> None:
    r = resolve.Resolution(question="thủ tục 1.999999 nộp ở đâu")
    r.asked_codes = ["1999999"]
    _gia_neo(monkeypatch, r)

    patch = asyncio.run(graph.node_neo(new_state("thủ tục 1.999999 nộp ở đâu")))

    assert patch["outcome"] == Outcome.ABSTAINED.value
    assert patch["branch_signal"] == BranchSignal.EMPTY.value
    assert "1.999999" in patch["refusal"]


def test_neo_khong_chan_khi_ma_ton_tai(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mã có thật thì đi tiếp bình thường — đây là câu hợp lệ."""
    r = resolve.Resolution(question="thủ tục 1.001699 cần gì")
    r.codes = ["1.001699"]
    r.asked_codes = ["1001699"]
    _gia_neo(monkeypatch, r)

    patch = asyncio.run(graph.node_neo(new_state("thủ tục 1.001699 cần gì")))

    assert "outcome" not in patch
    assert patch["codes"] == ["1.001699"]


def test_neo_chan_tinh_khac(monkeypatch: pytest.MonkeyPatch) -> None:
    r = resolve.Resolution(question="cấp sổ đỏ ở Đắk Lắk")
    _gia_neo(monkeypatch, r)

    patch = asyncio.run(graph.node_neo(new_state("cấp sổ đỏ ở Đắk Lắk")))

    assert patch["outcome"] == Outcome.ABSTAINED.value
    assert "Đắk Lắk" in patch["refusal"]
    # Không được nhắc tới số lượng thủ tục hay quy mô dữ liệu.
    assert "49" not in patch["refusal"]
    assert "thủ tục trong dữ liệu" not in patch["refusal"]


def test_sau_neo_da_ket_luan_thi_di_thang_tu_choi() -> None:
    state = new_state("câu gì đó")
    state["outcome"] = Outcome.ABSTAINED.value
    assert graph.sau_khi_neo(state) == graph.TU_CHOI


def test_tu_choi_giu_cau_dung_san() -> None:
    """``tu_choi`` không được ghi đè câu đã dựng đúng ở bước trước."""
    state = new_state("câu gì đó")
    state["refusal"] = "Không có mã thủ tục 1.999999. Bạn kiểm tra lại mã."
    state["branch_reason"] = "mã thủ tục không tồn tại"

    patch = asyncio.run(graph.node_tu_choi(state))

    assert patch["refusal"] == state["refusal"]
    assert patch["outcome"] == Outcome.ABSTAINED.value
