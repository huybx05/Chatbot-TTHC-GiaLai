"""Khoá chuỗi "câu nhiều ý": router tách ý → bù mục còn thiếu → nói thiếu đúng chỗ.

Bốn bất biến, mỗi cái ứng với một lỗi đã đo được trên câu thật:

① **Khía cạnh đã hỏi mà chưa có dữ liệu thì phải đi lấy**, không được bỏ qua. Câu ba ý về
   thủ tục 1.001699 từng nhận câu trả lời một ý, rồi nói "chưa ghi nhận thời hạn" trong khi
   `PROCESSING_TIME` có 345 ký tự trong PostgreSQL.
② **Chỉ câu nhiều ý mới bù.** Câu một ý giữ nguyên đường chạy rẻ hiện tại.
③ **"Thiếu" do mã tính, không do mô hình suy.** Danh sách `thieu` truyền vào lời dẫn là kết
   luận của hệ thống sau khi đã tìm.
④ **Bước bù không đổi kết cục** — nó chỉ làm ngữ cảnh đầy hơn.
"""

from __future__ import annotations

import asyncio

import pytest
from backend.app.rag import sections
from backend.app.workflow import answer, graph, nodes
from backend.app.workflow.state import new_state


def _state(**ghi_de: object):
    s = new_state("câu hỏi nhiều ý")
    s.update(ghi_de)
    return s


def _muc(section_type: str, **ghi_de: object) -> dict:
    goc: dict = {
        "kind": "chunk",
        "procedure_code": "1.001699",
        "section_type": section_type,
        "title": section_type,
        "content": f"nội dung {section_type}",
    }
    goc.update(ghi_de)
    return goc


# ── ①/② Tính khía cạnh còn thiếu ────────────────────────────────────────


def test_cau_mot_y_van_doi_bu_khi_thieu_muc() -> None:
    """Câu **một ý** hỏi một mục mà bằng chứng không có thì vẫn phải bù.

    Đây là lỗi thật đã đo được:

        "cho tôi biết **trình tự thực hiện** của thủ tục cấp giấy xác nhận tình trạng hôn nhân"

    Câu trúng kho đệm, mà kho đệm chỉ có mục hồ sơ. Cổng cũ (theo số ý) chặn bước bù, nên
    ``STEPS`` — dài 4 375 ký tự trong PostgreSQL — không vào ngữ cảnh, và mô hình viết "dữ liệu
    chưa ghi nhận trình tự thực hiện".
    """
    state = _state(
        parts=[{"text": "trình tự thực hiện", "need": ("steps",)}],
        evidence=[_muc("REQUIRED_DOCUMENTS")],
    )
    assert nodes.khia_canh_con_thieu(state) == ["steps"]


def test_cau_mot_y_da_co_muc_thi_khong_doi_bu() -> None:
    """Điều kiện là **mục đã có hay chưa**, không phải số ý — có rồi thì không tốn truy vấn."""
    state = _state(
        parts=[{"text": "nộp ở đâu", "need": ("submission_method",)}],
        evidence=[_muc("SUBMISSION_METHOD")],
    )
    assert nodes.khia_canh_con_thieu(state) == []


def test_cau_nhieu_y_thieu_muc_thi_bao_thieu() -> None:
    state = _state(
        parts=[
            {"text": "nộp ở đâu", "need": ("submission_method",)},
            {"text": "bao lâu", "need": ("processing_time",)},
            {"text": "lệ phí", "need": ("fee",)},
        ],
        evidence=[_muc("FEE")],
    )
    assert nodes.khia_canh_con_thieu(state) == ["submission_method", "processing_time"]


def test_da_du_thi_khong_bao_thieu() -> None:
    state = _state(
        parts=[
            {"text": "nộp ở đâu", "need": ("submission_method",)},
            {"text": "lệ phí", "need": ("fee",)},
        ],
        evidence=[_muc("FEE"), _muc("SUBMISSION_METHOD")],
    )
    assert nodes.khia_canh_con_thieu(state) == []


def test_khia_canh_doc_duoc_ca_hai_cach_viet() -> None:
    """Dữ liệu cũ dùng ``phi``, dữ liệu mới dùng ``FEE`` — cả hai phải nhận ra."""
    assert sections.khia_canh_cua("FEE") == "fee"
    assert sections.khia_canh_cua("phi") == "fee"
    assert sections.khia_canh_cua("PROCESSING_TIME") == "processing_time"
    assert sections.khia_canh_cua("khong_biet") is None


# ── Bước bù ─────────────────────────────────────────────────────────────


def test_bu_muc_them_dung_khia_canh_con_thieu(monkeypatch: pytest.MonkeyPatch) -> None:
    goi: list[tuple[list[str], list[str]]] = []

    async def fake(codes, needs):
        goi.append((list(codes), list(needs)))
        return [
            {
                "procedure_code": "1.001699",
                "procedure_name": "Cấp GXN khuyết tật",
                "section_type": "PROCESSING_TIME",
                "title": "Thời hạn giải quyết",
                "content": "05 ngày làm việc",
                "detail_url": "https://x/1",
            }
        ]

    monkeypatch.setattr(sections, "theo_khia_canh", fake)

    state = _state(
        codes=["1.001699"],
        branch="hybrid",
        parts=[
            {"text": "nộp ở đâu", "need": ("submission_method",)},
            {"text": "bao lâu", "need": ("processing_time",)},
        ],
        evidence=[_muc("FEE")],
    )
    ra = asyncio.run(nodes.node_bo_sung_muc(state))

    assert goi == [(["1.001699"], ["submission_method", "processing_time"])]
    assert len(ra["evidence"]) == 2
    assert ra["evidence"][-1]["kind"] == "section"
    assert ra["evidence"][-1]["section_type"] == "PROCESSING_TIME"
    # Sau khi bù vẫn còn thiếu submission_method vì DB không có dòng đó
    assert ra["thieu"] == ["submission_method"]
    assert ra["branch_signal"] == "ok"
    assert ra["branch"] == "hybrid", "bước bù không được đổi nhánh"


def test_bu_muc_khong_co_ma_thi_ghi_thieu(monkeypatch: pytest.MonkeyPatch) -> None:
    state = _state(
        codes=[],
        resolution={"code": ""},
        parts=[
            {"text": "lệ phí", "need": ("fee",)},
            {"text": "thời hạn", "need": ("processing_time",)},
        ],
        evidence=[],
    )
    ra = asyncio.run(nodes.node_bo_sung_muc(state))
    assert ra["thieu"] == ["fee", "processing_time"]
    assert "evidence" not in ra


def test_bu_muc_db_loi_thi_khong_hong_luot(monkeypatch: pytest.MonkeyPatch) -> None:
    async def hong(codes, needs):
        raise RuntimeError("db down")

    monkeypatch.setattr(sections, "theo_khia_canh", hong)
    state = _state(
        codes=["1.001699"],
        parts=[
            {"text": "lệ phí", "need": ("fee",)},
            {"text": "thời hạn", "need": ("processing_time",)},
        ],
        evidence=[],
    )
    with pytest.raises(RuntimeError):
        asyncio.run(nodes.node_bo_sung_muc(state))


def test_theo_khia_canh_khong_bao_gio_nem(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hàm đọc DB tự nuốt lỗi: bước bổ sung không được làm hỏng lượt."""

    def hong(codes, sections_):
        raise RuntimeError("db down")

    monkeypatch.setattr(sections, "_doc", hong)
    assert asyncio.run(sections.theo_khia_canh(["1.001699"], ["fee"])) == []


# ── ③ Lời dẫn: danh sách thiếu ──────────────────────────────────────────


def test_loi_dan_co_khoi_muc_khong_co_du_lieu() -> None:
    tin_nhan = answer.build_messages("câu hỏi", [_muc("FEE")], thieu=["processing_time", "fee"])
    noi_dung = tin_nhan[1]["content"]
    assert "CÁC MỤC KHÔNG CÓ DỮ LIỆU" in noi_dung
    assert "thời hạn giải quyết" in noi_dung
    assert "phí, lệ phí" in noi_dung


def test_khong_co_thieu_thi_khong_co_khoi() -> None:
    tin_nhan = answer.build_messages("câu hỏi", [_muc("FEE")])
    assert "CÁC MỤC KHÔNG CÓ DỮ LIỆU" not in tin_nhan[1]["content"]


def test_loi_dan_noi_ro_quyen_ket_luan_thuoc_he_thong() -> None:
    van_ban = answer.SYSTEM_PROMPT.lower()
    assert "các mục không có dữ liệu" in van_ban
    assert "không tự nói" in van_ban


# ── ④ Nối trong đồ thị ─────────────────────────────────────────────────


def test_ket_thuc_roi_vao_bu_khi_con_thieu() -> None:
    state = _state(
        outcome="answered",
        parts=[
            {"text": "lệ phí", "need": ("fee",)},
            {"text": "thời hạn", "need": ("processing_time",)},
        ],
        evidence=[_muc("FEE")],
    )
    assert graph.sau_khi_ket_thuc(state) == graph.BO_SUNG_MUC


def test_ket_thuc_di_sinh_khi_du() -> None:
    state = _state(
        outcome="answered",
        parts=[
            {"text": "lệ phí", "need": ("fee",)},
            {"text": "nộp ở đâu", "need": ("submission_method",)},
        ],
        evidence=[_muc("FEE"), _muc("SUBMISSION_METHOD")],
    )
    assert graph.sau_khi_ket_thuc(state) == graph.SINH


@pytest.mark.parametrize("ket_cuc", ["clarify", "abstained", "need_identity", "error"])
def test_khong_tra_loi_duoc_thi_khong_bu(ket_cuc: str) -> None:
    state = _state(
        outcome=ket_cuc,
        parts=[
            {"text": "lệ phí", "need": ("fee",)},
            {"text": "thời hạn", "need": ("processing_time",)},
        ],
        evidence=[],
    )
    assert graph.sau_khi_ket_thuc(state) == graph.SINH


def test_do_thi_co_buoc_bu_va_van_toi_duoc_ket_thuc() -> None:
    """Bước mới phải nối vào đồ thị, và không được làm mất đường ra."""
    so_do = graph.mermaid()
    assert "bo_sung_muc" in so_do
    assert "bo_sung_muc --> sinh" in so_do
