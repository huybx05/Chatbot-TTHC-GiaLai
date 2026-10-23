"""Khoá hai kết cục: hỏi lại và từ chối (việc 13.10).

Ba bất biến:

① **Hai kết cục phải khác nhau về nội dung**, không chỉ khác về nhãn: hỏi lại = *"tôi cần
   biết thêm"* kèm lựa chọn; từ chối = *"dữ liệu của tôi không có"* kèm lời giải thích.
② **Hỏi lại phải nêu đúng nguyên nhân** — thiếu tiền ngữ, nhiều thủ tục, nhiều văn bản, nhiều
   thực thể. Câu chung "bạn muốn hỏi thủ tục nào?" là câu trả lời tồi cho ba ca đầu.
③ **Từ chối phải nói thiếu cái gì** — dựa trên lý do router đưa ra, và nói được hệ thống làm
   gì, để người dùng biết hỏi lại cho đúng.
"""

from __future__ import annotations

import asyncio

import pytest
from backend.app.workflow import graph
from backend.app.workflow.state import AgentState, Outcome, new_state


def _state(cau: str, **ghi_de) -> AgentState:
    s = new_state(cau)
    s.update(ghi_de)
    return s


def _hoi_lai(**ghi_de) -> dict:
    return asyncio.run(graph.node_hoi_lai(_state("câu hỏi", **ghi_de)))


def _tu_choi(ly_do: str) -> dict:
    return asyncio.run(graph.node_tu_choi(_state("câu hỏi", branch_reason=ly_do)))


# ── ① Hỏi lại: câu hỏi theo đúng nguyên nhân ────────────────────────────


def test_thieu_tien_ngu_hoi_lai_dung_cach() -> None:
    ra = _hoi_lai(needs_antecedent=True)
    assert ra["outcome"] == Outcome.CLARIFY.value
    cau = ra["clarify"]["question"]
    assert "thủ tục nào" in cau.lower()
    assert "chưa nêu" in cau.lower(), "phải nói rõ vì sao chưa hiểu"


def test_nhieu_thu_tuc_hoi_lai_kem_lua_chon() -> None:
    ra = _hoi_lai(
        resolution={
            "code": "",
            "name": "",
            "method": "vector",
            "confidence": 0.61,
            "ambiguous": True,
            "alternatives": [
                {"code": "1.115350", "name": "Cấp lại Giấy chứng nhận do bị mất", "score": 0.63},
                {"code": "1.115345", "name": "Cấp đổi Giấy chứng nhận", "score": 0.62},
            ],
            "note": "",
        }
    )
    assert ra["outcome"] == Outcome.CLARIFY.value
    assert "2 thủ tục" in ra["clarify"]["question"]
    ma = [o["value"] for o in ra["clarify"]["options"]]
    assert ma == ["1.115350", "1.115345"]


def test_nhieu_van_ban_hoi_lai_ve_van_ban() -> None:
    ra = _hoi_lai(documents=["102/2024/ND CP", "04/2020/TT BTP"])
    assert "văn bản" in ra["clarify"]["question"].lower()
    ma = [o["value"] for o in ra["clarify"]["options"]]
    assert ma == ["102/2024/ND CP", "04/2020/TT BTP"]


def test_nhieu_thuc_the_hoi_lai_ve_gia_tri() -> None:
    ra = _hoi_lai(entity_ambiguous=True)
    assert "giá trị" in ra["clarify"]["question"].lower()


def test_khong_ro_nguyen_nhan_thi_hoi_chung() -> None:
    ra = _hoi_lai()
    assert ra["clarify"]["question"]
    assert ra["outcome"] == Outcome.CLARIFY.value


# ── ② Từ chối: lời giải thích theo nhóm lý do ───────────────────────────


@pytest.mark.parametrize(
    ("ly_do", "manh"),
    [
        ("dữ liệu không có thông tin người ký quyết định", "người ký"),
        ("dữ liệu không có thông tin ngày hiệu lực của văn bản", "hiệu lực"),
        ("hỏi về mức lệ phí cao nhất, cần so sánh", "so sánh"),
        ("không có thủ tục nào khớp tên 'bán rượu' trong dữ liệu", "không có thủ tục nào"),
    ],
)
def test_tu_choi_noi_thieu_cai_gi(ly_do: str, manh: str) -> None:
    ra = _tu_choi(ly_do)
    assert ra["outcome"] == Outcome.ABSTAINED.value
    assert manh.lower() in ra["refusal"].lower()


def test_tu_choi_ly_do_la_thi_van_noi_duoc_lam_gi() -> None:
    """Lý do lạ không được tạo ra lời từ chối rỗng — phải nói hệ thống làm được gì."""
    ra = _tu_choi("lý do nào đó không thuộc nhóm nào")
    assert ra["refusal"] == graph.TU_CHOI_CHUNG
    assert "hồ sơ" in ra["refusal"].lower()


def test_tu_choi_khong_hien_cau_hoi_lai() -> None:
    """Từ chối **không** kèm câu hỏi lại — người dùng đã nói rõ họ muốn gì."""
    ra = _tu_choi("dữ liệu không có thông tin người ký quyết định")
    assert not ra.get("clarify")


# ── ③ Bước kết thúc: không có lựa chọn thì đổi thành từ chối ────────────


def test_ket_thuc_doi_hoi_lai_rong_thanh_tu_choi() -> None:
    state = _state(
        "câu hỏi",
        outcome=Outcome.CLARIFY.value,
        branch_signal="clarify",
        clarify={"question": "", "options": []},
    )
    ra = asyncio.run(graph.node_ket_thuc(state))
    assert ra["outcome"] == Outcome.ABSTAINED.value
    assert ra["refusal"] == graph.HUONG_DAN_CHON
    assert not (ra.get("clarify") or {}).get("question")


def test_ket_thuc_giu_hoi_lai_co_lua_chon() -> None:
    state = _state(
        "câu hỏi",
        outcome=Outcome.CLARIFY.value,
        branch_signal="clarify",
        clarify={
            "question": "Bạn muốn hỏi thủ tục nào?",
            "options": [{"value": "1.115350", "label": "Cấp lại", "hint": ""}],
        },
    )
    ra = asyncio.run(graph.node_ket_thuc(state))
    assert ra["outcome"] == Outcome.CLARIFY.value
    assert "refusal" not in ra
    # Không vá gì cả: giữ nguyên câu hỏi và lựa chọn đã có trong trạng thái.
    assert "clarify" not in ra
    assert state["clarify"]["options"]


# ── ④ Lời từ chối phải đi ra ngoài được ─────────────────────────────────


def test_loi_tu_choi_vao_ket_qua_va_ban_in() -> None:
    """``to_dict`` và bản in phải mang lời từ chối, nếu không người dùng chỉ thấy "Không trả
    lời được" mà không biết vì sao."""
    from backend.app.workflow.run import RunResult, tom_tat

    state = new_state("câu hỏi")
    state["refusal"] = "Dữ liệu chưa có thông tin **người ký**."
    state["outcome"] = Outcome.ABSTAINED.value

    ket_qua = RunResult(question="câu hỏi", state=state, ms=1)
    assert ket_qua.to_dict()["refusal"]
    assert "người ký" in tom_tat(ket_qua)


# ── ⑤ Chốt lật "từ chối → hỏi lại" phải hẹp ─────────────────────────────


def _qd(branch: str, signal: str, reason: str):
    from backend.app.workflow.router_rules import RouterDecision

    return RouterDecision(branch=branch, signal=signal, reason=reason, source="llm")


def _res_co_ung_vien():
    from backend.app.rag.resolve import Resolution
    from backend.app.rag.resolver import ProcedureResolution

    r = Resolution(question="câu hỏi")
    r.procedure = ProcedureResolution(
        ambiguous=True,
        confidence=0.61,
        alternatives=[
            ("1.115350", "Cấp lại Giấy chứng nhận", 0.63),
            ("1.115345", "Cấp đổi Giấy chứng nhận", 0.62),
        ],
        note="2 thủ tục ngang nhau",
    )
    return r


def test_ly_do_mo_ho_thi_lat_thanh_hoi_lai() -> None:
    qd = _qd("", "empty", "nhiều thủ tục cùng khớp tên, cần làm rõ")
    ra = graph._abstain_khi_co_lua_chon(qd, _res_co_ung_vien())
    assert ra.signal == "clarify"


def test_ly_do_khong_mo_hinh_hoa_thi_giu_tu_choi() -> None:
    """Có ứng viên trong dữ liệu không biến câu "xếp hạng theo lệ phí" thành hỏi lại."""
    qd = _qd("", "empty", "hỏi về mức lệ phí cao nhất, cần so sánh")
    ra = graph._abstain_khi_co_lua_chon(qd, _res_co_ung_vien())
    assert ra.signal == "empty"


def test_khong_du_hai_ung_vien_thi_giu_tu_choi() -> None:
    from backend.app.rag.resolve import Resolution
    from backend.app.rag.resolver import ProcedureResolution

    r = Resolution(question="câu hỏi")
    r.procedure = ProcedureResolution(ambiguous=False, alternatives=[("1.115350", "Cấp lại", 0.7)])
    qd = _qd("", "empty", "nhiều thủ tục cùng khớp")
    assert graph._abstain_khi_co_lua_chon(qd, r).signal == "empty"
