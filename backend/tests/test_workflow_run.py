"""Khoá điểm vào duy nhất (việc 13.7).

Ba thứ được khoá:

① **Một dòng vết** cho mỗi câu — đúng một, đủ thông tin, và **luôn nằm trên một dòng** kể cả
   khi câu hỏi dài 900 ký tự.
② **Kết quả trả ra không bao giờ tự nhận là câu trả lời** ở mốc 1: ``has_answer`` luôn
   ``false``. Nếu cờ này thành ``true`` khi chưa có bước sinh, người đọc báo cáo sẽ tưởng hệ
   thống đã trả lời xong.
③ **Lỗi của đồ thị không bị nuốt**: ``ask`` bắt để ghi vết và trả ``outcome = error``, chứ
   không để ngoại lệ thoát ra làm sập API.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from backend.app.rag import retrieval
from backend.app.workflow import run
from backend.app.workflow.state import new_state


def _chay(coro):
    return asyncio.run(coro)


class _DoThiGia:
    """Đồ thị giả — trả đúng trạng thái mong muốn, không gọi mạng."""

    def __init__(self, **ghi_de) -> None:
        self.ghi_de = ghi_de
        self.loi: Exception | None = None
        self.so_lan = 0

    async def ainvoke(self, state):
        self.so_lan += 1
        if self.loi is not None:
            raise self.loi
        ra = dict(state)
        ra.update(
            {
                "branch": "graph",
                "branch_signal": "ok",
                "outcome": "answered",
                "branch_reason": "đồ thị trả **AGENCY**",
                "router_source": "rule",
                "evidence": [
                    {
                        "kind": "graph",
                        "title": "Cơ quan liên quan",
                        "content": "Vai trò: Cơ quan ban hành · Cơ quan: Bộ Y tế",
                        "part_index": 1,
                        "part_title": "Cơ quan liên quan",
                    }
                ],
                "timings": {"resolve_ms": 0, "router_ms": 0, "branch_ms": 7, "generate_ms": 0},
                "resolution": {"code": "1.001699", "name": "Cấp Giấy xác nhận khuyết tật"},
            }
        )
        ra.update(self.ghi_de)
        return ra


@pytest.fixture
def do_thi_gia(monkeypatch: pytest.MonkeyPatch) -> _DoThiGia:
    gia = _DoThiGia()
    monkeypatch.setattr(run, "WORKFLOW", gia)
    return gia


# ── Dòng vết ────────────────────────────────────────────────────────────


def test_ghi_dung_mot_dong_vet(do_thi_gia: _DoThiGia, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="backend.app.workflow"):
        _chay(run.ask("Thủ tục 1.001699 do cơ quan nào ban hành?"))

    dong = [r.getMessage() for r in caplog.records if r.getMessage().startswith("workflow q=")]
    assert len(dong) == 1, f"phải đúng 1 dòng vết, đang là {len(dong)}"
    vet = dong[0]
    for phan in ("branch=graph", "signal=ok", "outcome=answered", "ev=1", "nhung=0"):
        assert phan in vet, f"thiếu {phan} trong dòng vết: {vet}"


def test_ask_appends_diagnostic_trace(
    do_thi_gia: _DoThiGia, monkeypatch: pytest.MonkeyPatch
) -> None:
    written = []
    monkeypatch.setattr(run.trace_log, "append", lambda result, **_: written.append(result))

    result = _chay(run.ask("Thủ tục 1.001699 cần hồ sơ gì?"))

    assert written == [result]


def test_dong_vet_luon_mot_dong(do_thi_gia: _DoThiGia, caplog: pytest.LogCaptureFixture) -> None:
    """Câu hỏi 900 ký tự có xuống dòng vẫn phải ra **một** dòng vết."""
    cau = "Thủ tục 1.001699 " + ("do cơ quan nào ban hành " * 40) + "\n\nDòng thứ hai"
    with caplog.at_level(logging.INFO, logger="backend.app.workflow"):
        _chay(run.ask(cau))

    vet = [r.getMessage() for r in caplog.records if r.getMessage().startswith("workflow q=")][0]
    assert "\n" not in vet
    assert len(vet) < 500, "dòng vết phải ngắn; cắt câu hỏi là việc của bước ghi vết"


def test_van_ghi_vet_khi_loi(caplog: pytest.LogCaptureFixture, monkeypatch) -> None:
    gia = _DoThiGia()
    gia.loi = RuntimeError("đồ thị hỏng")
    monkeypatch.setattr(run, "WORKFLOW", gia)
    with caplog.at_level(logging.INFO, logger="backend.app.workflow"):
        _chay(run.ask("câu hỏi bất kỳ"))
    assert any(r.getMessage().startswith("workflow q=") for r in caplog.records)


# ── Kết quả ─────────────────────────────────────────────────────────────


def test_khong_bao_gio_tu_nhan_da_tra_loi(do_thi_gia: _DoThiGia) -> None:
    du_lieu = _chay(run.ask("Thủ tục 1.001699 do cơ quan nào ban hành?")).to_dict()
    assert du_lieu["has_answer"] is False, (
        "mốc 1 chưa có bước sinh nên không được nhận là đã trả lời"
    )
    assert du_lieu["answerable"] is True, "có bằng chứng thì vẫn phải nói là dùng được"


def test_tra_ra_du_truong_can_thiet(do_thi_gia: _DoThiGia) -> None:
    du_lieu = _chay(run.ask("Thủ tục 1.001699 do cơ quan nào ban hành?")).to_dict()
    can = {
        "question",
        "branch",
        "branch_signal",
        "outcome",
        "branch_reason",
        "router_source",
        "embedding_used",
        "evidence",
        "clarify",
        "codes",
        "documents",
        "resolution",
        "error",
        "timings",
        "ms",
        "answerable",
        "has_answer",
        "summary",
    }
    assert can - {"summary"} <= set(du_lieu), sorted(can - set(du_lieu))


def test_khong_do_toan_bo_trang_thai_ra_ngoai(do_thi_gia: _DoThiGia) -> None:
    """Chỉ trường cần thiết — trạng thái nội bộ sẽ đổi khi làm mốc 2."""
    du_lieu = _chay(run.ask("câu hỏi")).to_dict()
    assert "normalized_question" not in du_lieu
    assert "max_retry" not in du_lieu


def test_stream_citations_follow_the_prepared_answer_context(do_thi_gia: _DoThiGia) -> None:
    """Đường ``generate=False`` phải chọn nguồn như đúng context sẽ cấp cho model."""
    do_thi_gia.ghi_de = {
        "evidence": [
            {
                "kind": "section",
                "procedure_code": "1.001699",
                "title": "Hồ sơ",
                "content": "Giấy tờ cần nộp.",
                "request_index": 0,
            },
            {
                "kind": "section",
                "procedure_code": "1.001699",
                "title": "Thời hạn",
                "content": "25 ngày làm việc.",
                "request_index": 1,
            },
        ],
        "question_frame": {
            "requests": [
                {"facet": "required_documents"},
                {"facet": "processing_time"},
            ]
        },
        "coverage": [
            {"request_index": 0, "status": "covered"},
            {"request_index": 1, "status": "covered"},
        ],
    }

    citations = _chay(run.ask("câu hỏi", generate=False)).citations

    assert [citation["section"] for citation in citations] == ["Hồ sơ", "Thời hạn"]


def test_khong_co_bang_chung_thi_khong_dung_duoc(do_thi_gia: _DoThiGia) -> None:
    gia = do_thi_gia
    gia.ghi_de = {"evidence": [], "outcome": "abstained"}
    ket_qua = _chay(run.ask("cách nấu phở bò"))
    assert ket_qua.answerable is False
    assert ket_qua.outcome == "abstained"


# ── Lỗi đồ thị không được nuốt ──────────────────────────────────────────


def test_loi_do_thi_tra_ve_ket_cuc_loi(monkeypatch: pytest.MonkeyPatch) -> None:
    gia = _DoThiGia()
    gia.loi = RuntimeError("đồ thị hỏng")
    monkeypatch.setattr(run, "WORKFLOW", gia)

    ket_qua = _chay(run.ask("câu hỏi bất kỳ"))
    assert ket_qua.ran is False
    assert ket_qua.outcome == "error"
    assert ket_qua.ms >= 0


def test_loi_khong_lam_sap_loi_vao(monkeypatch: pytest.MonkeyPatch) -> None:
    """``retrieve`` phải trả từ điển kể cả khi đồ thị hỏng — API không được ném 500."""
    gia = _DoThiGia()
    gia.loi = RuntimeError("đồ thị hỏng")
    monkeypatch.setattr(run, "WORKFLOW", gia)
    du_lieu = _chay(retrieval.retrieve("câu hỏi"))
    assert isinstance(du_lieu, dict)
    assert du_lieu["outcome"] == "error"


# ── Bản đọc được ────────────────────────────────────────────────────────


def test_tom_tat_noi_ro_chua_sinh_duoc_cau_tra_loi(do_thi_gia: _DoThiGia) -> None:
    """Chưa sinh được câu trả lời thì phải nói rõ, không im lặng.

    Bài kiểm chạy với ``ANSWER_USE_LLM=0`` (xem ``conftest.py``), nên đây đúng là đường
    "không bật mô hình sinh" — đường mà giao diện cũng gặp khi thiếu cấu hình.
    """
    ban = run.tom_tat(_chay(run.ask("Thủ tục 1.001699 do cơ quan nào ban hành?")))
    assert "phần trên là bằng chứng" in ban.lower()
    assert "Neo4j" in ban, "phải hiện tên nguồn, không hiện mã `graph`"
    assert "Bộ Y tế" in ban, "phải hiện nội dung bằng chứng"


def test_tom_tat_in_cau_tra_loi_khi_co(do_thi_gia: _DoThiGia) -> None:
    """Có câu trả lời thì bản in đặt nó **trước** bằng chứng — người đọc cần câu trả lời trước."""
    do_thi_gia.ghi_de = {
        **do_thi_gia.ghi_de,
        "answer": "Thủ tục do Bộ Y tế ban hành [1].",
        "citations": [
            {
                "procedure_code": "1.001699",
                "procedure_name": "Cấp GXN khuyết tật",
                "detail_url": "",
                "document_code": "",
            }
        ],
    }
    ban = run.tom_tat(_chay(run.ask("Thủ tục 1.001699 do cơ quan nào ban hành?")))
    assert "Trả lời:" in ban
    assert "Bộ Y tế ban hành [1]" in ban
    assert ban.index("Trả lời:") < ban.index("Bằng chứng ("), "câu trả lời phải đứng trước ngữ cảnh"


def test_tom_tat_hien_cau_hoi_lai(do_thi_gia: _DoThiGia) -> None:
    do_thi_gia.ghi_de = {
        "branch": "",
        "branch_signal": "clarify",
        "outcome": "clarify",
        "evidence": [],
        "clarify": {
            "question": "Bạn muốn hỏi thủ tục nào?",
            "options": [{"value": "1.001699", "label": "Cấp Giấy xác nhận khuyết tật"}],
        },
    }
    ban = run.tom_tat(_chay(run.ask("đổi sổ đỏ bị rách")))
    assert "Bạn muốn hỏi thủ tục nào?" in ban
    assert "Cấp Giấy xác nhận khuyết tật" in ban


def test_tom_tat_cau_rong(do_thi_gia: _DoThiGia) -> None:
    do_thi_gia.ghi_de = {"evidence": [], "outcome": "abstained"}
    ban = run.tom_tat(_chay(run.ask("cách nấu phở bò")))
    assert "không có bằng chứng nào" in ban


# ── Lối vào của tầng RAG ────────────────────────────────────────────────


def test_retrieval_la_voi_mong(do_thi_gia: _DoThiGia) -> None:
    """``retrieval.retrieve`` chỉ chuyển tiếp — không tự dựng kết quả riêng."""
    du_lieu = _chay(retrieval.retrieve("Thủ tục 1.001699 do cơ quan nào ban hành?"))
    assert du_lieu["branch"] == "graph"
    assert du_lieu["has_answer"] is False


def test_retrieve_full_tra_doi_tuong(do_thi_gia: _DoThiGia) -> None:
    ket_qua = _chay(retrieval.retrieve_full("câu hỏi"))
    assert isinstance(ket_qua, run.RunResult)
    assert ket_qua.question == "câu hỏi"


class _GhiTurn(_DoThiGia):
    """Đồ thị giả có ghi lại ``turn_index`` nhận được."""

    def __init__(self) -> None:
        super().__init__()
        self.thay: dict = {}

    async def ainvoke(self, state):
        self.thay["turn_index"] = state["turn_index"]
        return await super().ainvoke(state)


def test_turn_index_duoc_chuyen_xuong(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lượt thứ mấy phải đi vào trạng thái — mốc 2 cần cho việc hỏi lại nhiều bước."""
    gia = _GhiTurn()
    monkeypatch.setattr(run, "WORKFLOW", gia)
    _chay(run.ask("câu hỏi", turn_index=3))
    assert gia.thay["turn_index"] == 3


def test_trang_thai_ban_dau_hop_le() -> None:
    """``new_state`` là thứ ``ask`` đưa vào đồ thị — phải đủ trường."""
    state = new_state("câu hỏi")
    assert state["question"] == "câu hỏi"
    assert state["outcome"] == "error"
