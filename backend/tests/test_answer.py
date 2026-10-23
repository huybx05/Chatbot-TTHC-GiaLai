"""Khoá bước sinh câu trả lời (việc 13.13).

Bốn bất biến:

① **Số hiệu `[n]` phải trỏ đúng mục thứ n** trong ngữ cảnh, và danh sách trích dẫn phải cùng
   thứ tự. Nếu hai bên lọc riêng, câu trả lời trích `[3]` có thể trỏ vào mục khác với mục thứ
   ba người đọc thấy — loại lỗi không ai phát hiện được khi đọc.
② **Mục rỗng không được chiếm số**, nếu không số hiệu bị nhảy và mô hình trích vào chỗ trống.
③ **Không bao giờ trả câu trả lời rỗng mà không nói lý do**: nơi gọi cần biết để hiện bằng
   chứng thay vì khung trống.
④ **Không có bằng chứng thì không gọi mô hình** — gọi chỉ tốn tiền để nhận về câu bịa.
"""

from __future__ import annotations

import asyncio

import pytest
from backend.app.workflow import answer as ans
from backend.app.workflow import graph
from backend.app.workflow.state import new_state


def _muc(**ghi_de: object) -> dict:
    goc: dict = {
        "kind": "chunk",
        "procedure_code": "1.001699",
        "procedure_name": "Cấp Giấy xác nhận khuyết tật",
        "title": "Hồ sơ",
        "content": "Giấy tờ gồm 3 loại.",
    }
    goc.update(ghi_de)
    return goc


# ── ① Ngữ cảnh đánh số ──────────────────────────────────────────────────


def test_ngu_canh_bo_muc_rong_va_khong_danh_so() -> None:
    """Mục rỗng không được vào ngữ cảnh, và ngữ cảnh **không** đánh số nguồn.

    Không đánh số vì mô hình có thói quen chép số hiệu vào câu trả lời, mà câu trả lời cho
    người dân thì không được có `[1]`.
    """
    evidence = [
        _muc(content="Mục một."),
        _muc(content="   "),
        _muc(content="Mục hai."),
    ]
    van_ban, nhan = ans.build_context(evidence)

    assert "Mục một." in van_ban and "Mục hai." in van_ban
    assert "[1]" not in van_ban and "[2]" not in van_ban
    assert len(nhan) == 2


def test_ngu_canh_ghi_ro_nguon() -> None:
    van_ban, _ = ans.build_context([_muc(kind="graph", title="Cơ quan liên quan")])
    assert "Nguồn: Neo4j" in van_ban
    assert "Cơ quan liên quan" in van_ban


def test_ngu_canh_gop_khoang_trang() -> None:
    van_ban, _ = ans.build_context([_muc(content="Giấy   tờ\n gồm   3 loại")])
    assert "Giấy tờ gồm 3 loại" in van_ban


# ── ② Trích dẫn cùng thứ tự với số hiệu ─────────────────────────────────


def test_trich_dan_cung_thu_tu_va_cung_bo_loc() -> None:
    evidence = [
        _muc(procedure_code="1.001699", content="Một."),
        _muc(procedure_code="", content="  "),
        _muc(procedure_code="1.004873", content="Hai."),
    ]
    _, nhan = ans.build_context(evidence)
    citations = ans.build_citations(evidence)

    assert [c["procedure_code"] for c in citations] == ["1.001699", "1.004873"]
    assert nhan == ("1.001699", "1.004873")
    assert len(citations) == len(nhan)


def test_trich_dan_giu_ten_va_url() -> None:
    citations = ans.build_citations(
        [_muc(procedure_name="Cấp GXN", detail_url="https://example.test/1")]
    )
    assert citations[0]["procedure_name"] == "Cấp GXN"
    assert citations[0]["detail_url"] == "https://example.test/1"


# ── ③/④ Lời dẫn và đường lỗi ────────────────────────────────────────────


def test_loi_dan_chua_luat_trung_thuc() -> None:
    """Lời dẫn là nơi đặt luật. Mất một luật là mất một ràng buộc."""
    for manh in ("chưa ghi nhận", "không có", "Không bịa số", "ngoài phạm vi"):
        assert manh.lower() in ans.SYSTEM_PROMPT.lower(), f"thiếu luật: {manh}"


def test_loi_dan_cam_danh_so_va_cam_in_url() -> None:
    """Hai thứ này lọt vào câu trả lời là hỏng đúng thứ người dùng đã phàn nàn."""
    van_ban = ans.SYSTEM_PROMPT.lower()
    assert "không đánh số" in van_ban
    assert "không in đường dẫn" in van_ban or "không chép đường dẫn" in van_ban


def test_loi_dan_cam_liet_ke_nhung_gi_khong_co() -> None:
    """Mô hình từng thêm đoạn "Dữ liệu chưa ghi nhận các nội dung người dân thường cần…".

    Đó là nội dung người dùng không hỏi — phải bị cấm rõ ràng, không chỉ "khuyến khích" bỏ.
    """
    van_ban = ans.SYSTEM_PROMPT.lower()
    assert "cấm liệt kê" in van_ban
    assert "người dân thường cần" in van_ban, "phải nêu đúng ví dụ sai để mô hình nhận ra"


def test_tin_nhan_chua_ngu_canh_va_cau_hoi() -> None:
    tin_nhan = ans.build_messages("Cần giấy tờ gì?", [_muc(content="Giấy tờ gồm 3 loại.")])
    assert tin_nhan[0]["role"] == "system"
    assert tin_nhan[1]["role"] == "user"
    assert "Giấy tờ gồm 3 loại." in tin_nhan[1]["content"]
    assert "Cần giấy tờ gì?" in tin_nhan[1]["content"]


def test_khong_co_bang_chung_thi_khong_goi_mo_hinh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANSWER_USE_LLM", "1")
    da_goi = False

    def fake_client():
        nonlocal da_goi
        da_goi = True
        return object()

    monkeypatch.setattr(ans, "_client", fake_client)
    with pytest.raises(ans.AnswerError):
        asyncio.run(ans.sinh("câu hỏi", []))
    assert not da_goi, "không có bằng chứng thì không được gọi mô hình"


def test_tat_bang_bien_moi_truong(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANSWER_USE_LLM", "0")
    assert ans.dang_bat() is False
    with pytest.raises(ans.AnswerError):
        asyncio.run(ans.sinh("câu hỏi", [_muc()]))


# ── Gọi mô hình: thành công và lỗi ──────────────────────────────────────


class _PhanHoi:
    def __init__(self, noi_dung: str) -> None:
        self.choices = [type("C", (), {"message": type("M", (), {"content": noi_dung})()})()]
        self.usage = type("U", (), {"prompt_tokens": 1200, "completion_tokens": 210})()


def _gia_lap(monkeypatch: pytest.MonkeyPatch, *, noi_dung: str, loi: Exception | None = None):
    monkeypatch.setenv("ANSWER_USE_LLM", "1")

    async def fake_create(**kwargs):
        if loi is not None:
            raise loi
        return _PhanHoi(noi_dung)

    # Gán lên **instance**, không lên class: hàm gán ở class sẽ thành bound method và nhận
    # thêm `self` — đúng lỗi đã gặp ở lần chạy đầu.
    completions = type("Completions", (), {})()
    completions.create = fake_create
    chat = type("Chat", (), {})()
    chat.completions = completions
    client = type("Client", (), {})()
    client.chat = chat
    monkeypatch.setattr(ans, "_client", lambda: client)


def test_sinh_thanh_cong_tra_cau_tra_loi_va_chi_phi(monkeypatch: pytest.MonkeyPatch) -> None:
    _gia_lap(monkeypatch, noi_dung="Thủ tục do Bộ Y tế ban hành [1].")
    ket_qua = asyncio.run(ans.sinh("câu hỏi", [_muc()]))

    assert ket_qua.ok
    assert ket_qua.text == "Thủ tục do Bộ Y tế ban hành [1]."
    assert ket_qua.citations[0]["procedure_code"] == "1.001699"
    assert (ket_qua.tokens_in, ket_qua.tokens_out) == (1200, 210)


def test_sinh_mo_hinh_tra_rong_thi_bao_loi(monkeypatch: pytest.MonkeyPatch) -> None:
    _gia_lap(monkeypatch, noi_dung="   ")
    with pytest.raises(ans.AnswerError):
        asyncio.run(ans.sinh("câu hỏi", [_muc()]))


def test_sinh_loi_api_thanh_loi_co_ly_do(monkeypatch: pytest.MonkeyPatch) -> None:
    _gia_lap(monkeypatch, noi_dung="", loi=RuntimeError("429 Too Many Requests"))
    with pytest.raises(ans.AnswerError) as loi:
        asyncio.run(ans.sinh("câu hỏi", [_muc()]))
    assert "429" in loi.value.reason


# ── Bước trong đồ thị ───────────────────────────────────────────────────


def _state(**ghi_de: object):
    s = new_state("Thủ tục 1.001699 cần gì?")
    s.update(ghi_de)
    return s


def test_khong_tra_loi_duoc_thi_khong_sinh() -> None:
    for ket_cuc in ("clarify", "abstained", "error"):
        ra = asyncio.run(graph.node_sinh(_state(outcome=ket_cuc, evidence=[_muc()])))
        assert ra == {}, f"kết cục {ket_cuc} không được sinh câu trả lời"


def test_khong_co_bang_chung_thi_khong_sinh() -> None:
    assert asyncio.run(graph.node_sinh(_state(outcome="answered", evidence=[]))) == {}


def test_tat_mo_hinh_thi_ghi_ly_do(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANSWER_USE_LLM", "0")
    ra = asyncio.run(graph.node_sinh(_state(outcome="answered", evidence=[_muc()])))
    assert "chưa cấu hình" in ra["answer_error"]


def test_sinh_loi_thi_giu_bang_chung_va_ghi_ly_do(monkeypatch: pytest.MonkeyPatch) -> None:
    _gia_lap(monkeypatch, noi_dung="", loi=RuntimeError("boom"))
    ra = asyncio.run(graph.node_sinh(_state(outcome="answered", evidence=[_muc()])))

    assert ra["answer_error"], "phải nói vì sao không sinh được"
    assert "answer" not in ra, "không được ghi câu trả lời rỗng đè lên trạng thái"


def test_sinh_thanh_cong_ghi_cau_tra_loi_va_cong_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _gia_lap(monkeypatch, noi_dung="Bộ Y tế ban hành [1].")
    ra = asyncio.run(
        graph.node_sinh(
            _state(
                outcome="answered",
                evidence=[_muc()],
                tokens={"input": 100, "output": 20},
            )
        )
    )

    assert ra["answer"] == "Bộ Y tế ban hành [1]."
    assert ra["citations"][0]["procedure_code"] == "1.001699"
    assert ra["tokens"] == {"input": 1300, "output": 230}, "token của bước sinh phải cộng dồn"
    assert ra["timings"]["generate_ms"] >= 0


# ── Trang kiểm thử truy xuất: sinh theo yêu cầu ─────────────────────────


def _request(**ghi_de: object):
    from backend.app.api.admin import RetrievalTestRequest

    goc = {"question": "câu hỏi", "mode": "hybrid", "top_k": 5, "generate_answer": True}
    goc.update(ghi_de)
    return RetrievalTestRequest(**goc)


def _candidate_dict() -> dict:
    return {
        "procedure_code": "1.004873",
        "procedure_name": "Cấp Giấy xác nhận tình trạng hôn nhân",
        "title": "Hồ sơ",
        "content": "Giấy tờ gồm 3 loại.",
    }


def test_khong_bat_thi_khong_sinh() -> None:
    from backend.app.api import admin

    ra = asyncio.run(admin._sinh_neu_duoc_hoi(_request(generate_answer=False), [_candidate_dict()]))
    assert ra == ("", [], "")


def test_khong_co_ung_vien_thi_khong_sinh() -> None:
    from backend.app.api import admin

    ra = asyncio.run(admin._sinh_neu_duoc_hoi(_request(), []))
    assert ra == ("", [], "")


def test_trang_kiem_thu_tat_mo_hinh_thi_ghi_ly_do(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.api import admin

    monkeypatch.setenv("ANSWER_USE_LLM", "0")
    cau, trich, loi = asyncio.run(admin._sinh_neu_duoc_hoi(_request(), [_candidate_dict()]))
    assert cau == "" and trich == []
    assert "chưa cấu hình" in loi


def test_sinh_loi_khong_lam_hong_ket_qua_truy_xuat(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.api import admin

    _gia_lap(monkeypatch, noi_dung="", loi=RuntimeError("boom"))
    cau, trich, loi = asyncio.run(admin._sinh_neu_duoc_hoi(_request(), [_candidate_dict()]))
    assert cau == "" and trich == []
    assert loi, "phải trả lý do thay vì ném lỗi ra ngoài"


def test_sinh_thanh_cong_tra_cau_tra_loi(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.api import admin

    _gia_lap(monkeypatch, noi_dung="Hồ sơ gồm 3 loại giấy tờ [1].")
    cau, trich, loi = asyncio.run(admin._sinh_neu_duoc_hoi(_request(), [_candidate_dict()]))
    assert cau == "Hồ sơ gồm 3 loại giấy tờ [1]."
    assert trich[0]["procedure_code"] == "1.004873"
    assert loi == ""


def test_mac_dinh_la_bat(monkeypatch: pytest.MonkeyPatch) -> None:
    """Không đặt biến môi trường nào thì bước sinh phải **bật**.

    Đây là hành vi thật của sản phẩm. Công tắc `ANSWER_USE_LLM` chỉ để bài kiểm không gọi API
    trả tiền — nếu nó lỡ đổi thành mặc định tắt thì sản phẩm sẽ im lặng không trả lời, và
    không ai phát hiện cho tới khi người dân hỏi.
    """
    monkeypatch.delenv("ANSWER_USE_LLM", raising=False)
    monkeypatch.setattr(ans.settings, "synthesizer_model_name", "deepseek-flash")
    monkeypatch.setattr(ans.settings, "deepseek_base_url", "https://api.deepseek.com")
    assert ans.dang_bat() is True


def test_chi_tat_khi_dat_bang_0(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ans.settings, "synthesizer_model_name", "deepseek-flash")
    monkeypatch.setattr(ans.settings, "deepseek_base_url", "https://api.deepseek.com")
    for gia_tri in ("0", "false", "off", "no"):
        monkeypatch.setenv("ANSWER_USE_LLM", gia_tri)
        assert ans.dang_bat() is False, f"{gia_tri} phải tắt"
    monkeypatch.setenv("ANSWER_USE_LLM", "1")
    assert ans.dang_bat() is True
