"""Khoá hợp đồng của endpoint công khai ``POST /chat``.

Bốn thứ dễ hỏng mà không ai thấy nếu chỉ nhìn mã:

① **Nguồn trùng** — bằng chứng là 10 đoạn của cùng một thủ tục, nên danh sách thô có 10 dòng y
   hệt. Giao diện hiện 10 dòng giống nhau là trông như lỗi.
② **Loại kết cục** — trả lời được / cần hỏi lại / từ chối là ba chuyện khác nhau; gộp cả ba vào
   một cờ là giao diện tô sai màu.
③ **Lựa chọn của câu hỏi lại** — phải giữ cấu trúc để giao diện vẽ nút, không nhét vào chuỗi.
④ **Chặn lạm dụng và lặp lại** — endpoint công khai, mỗi câu tốn hai lần gọi mô hình.
"""

from __future__ import annotations

import json

import pytest
from backend.app.api import chat as chat_api
from backend.app.main import app
from backend.app.rag import retrieval
from backend.app.workflow import answer as answer_module
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture(autouse=True)
def _sach_trang_thai():
    """Mỗi bài kiểm bắt đầu với bộ đếm và cache rỗng."""
    chat_api._luot_goi.clear()
    chat_api.xoa_cache()
    ban_sao_limit = chat_api.RATE_LIMIT
    ban_sao_ttl = chat_api.CACHE_TTL_S
    yield
    chat_api.RATE_LIMIT = ban_sao_limit
    chat_api.CACHE_TTL_S = ban_sao_ttl
    chat_api._luot_goi.clear()
    chat_api.xoa_cache()


def _ket_qua(**ghi_de: object) -> dict:
    goc: dict = {
        "outcome": "answered",
        "answer": "Hồ sơ gồm một tờ khai.",
        "citations": [],
        "resolution": {},
    }
    goc.update(ghi_de)
    return goc


def _gan(monkeypatch: pytest.MonkeyPatch, ket_qua: dict) -> None:
    async def fake(_question: str, **_kwargs) -> dict:
        return ket_qua

    monkeypatch.setattr(retrieval, "retrieve", fake)


# ── ① Nguồn: gộp trùng, cắt số lượng ────────────────────────────────────


def test_gop_nguon_trung_va_cat_con_ba(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mười đoạn của cùng một thủ tục → **một** nguồn, không phải mười."""
    chung = {
        "procedure_code": "1.001699",
        "procedure_name": "Cấp GXN khuyết tật",
        "detail_url": "https://example.test/1",
        "document_code": "",
        "section": "Phí, lệ phí",
    }
    khac = [
        {
            "procedure_code": f"1.00000{i}",
            "procedure_name": f"Thủ tục {i}",
            "detail_url": f"https://example.test/{i}",
            "document_code": "",
        }
        for i in range(2, 6)
    ]
    _gan(monkeypatch, _ket_qua(citations=[chung] * 10 + khac))

    du_lieu = client.post("/chat", json={"question": "lệ phí bao nhiêu?"}).json()
    tieu_de = [c["title"] for c in du_lieu["citations"]]

    assert len(tieu_de) == chat_api.MAX_CITATIONS
    assert tieu_de[0] == "Cấp GXN khuyết tật (Mã TTHC: 1.001699)"
    assert du_lieu["citations"][0]["section"] == "Phí, lệ phí"
    assert len(set(tieu_de)) == len(tieu_de), "không được còn nguồn trùng"


def test_nguon_giu_duong_dan_va_ma_thu_tuc(monkeypatch: pytest.MonkeyPatch) -> None:
    _gan(
        monkeypatch,
        _ket_qua(
            citations=[
                {
                    "procedure_code": "1.001699",
                    "procedure_name": "Cấp GXN khuyết tật",
                    "detail_url": "https://example.test/1",
                    "document_code": "",
                }
            ]
        ),
    )
    du_lieu = client.post("/chat", json={"question": "hồ sơ gì?"}).json()
    assert du_lieu["citations"][0]["url"] == "https://example.test/1"
    assert du_lieu["citations"][0]["title"].endswith("(Mã TTHC: 1.001699)")


# ── ② Loại kết cục ──────────────────────────────────────────────────────


def test_tra_loi_duoc_thi_status_answered(monkeypatch: pytest.MonkeyPatch) -> None:
    _gan(monkeypatch, _ket_qua(resolution={"code": "1.001699", "name": "Cấp GXN"}))
    du_lieu = client.post("/chat", json={"question": "cần gì?"}).json()
    assert du_lieu["status"] == "answered"
    assert du_lieu["abstained"] is False
    assert du_lieu["procedure"] == {
        "procedure_code": "1.001699",
        "procedure_name": "Cấp GXN",
    }


def test_hoi_lai_thi_status_clarify_khong_phai_abstained(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hỏi lại **không** phải từ chối — giao diện phải tô khác nhau."""
    _gan(
        monkeypatch,
        _ket_qua(
            outcome="clarify",
            answer="",
            clarify={"question": "Bạn muốn hỏi thủ tục nào?", "options": []},
        ),
    )
    du_lieu = client.post("/chat", json={"question": "thời hạn bao lâu?"}).json()
    assert du_lieu["status"] == "clarify"
    assert du_lieu["abstained"] is True  # giữ cho client cũ
    assert du_lieu["answer"] == "Bạn muốn hỏi thủ tục nào?"


def test_tu_choi_thi_status_abstained(monkeypatch: pytest.MonkeyPatch) -> None:
    _gan(
        monkeypatch,
        _ket_qua(
            outcome="abstained",
            answer="",
            refusal="Dữ liệu chưa có thông tin người ký.",
        ),
    )
    du_lieu = client.post("/chat", json={"question": "ai ký?"}).json()
    assert du_lieu["status"] == "abstained"
    assert du_lieu["answer"] == "Dữ liệu chưa có thông tin người ký."


def test_khong_co_cau_tra_loi_nao_thi_van_noi_duoc_lam_gi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Không được trả chuỗi rỗng — người dùng sẽ thấy khung trống."""
    _gan(monkeypatch, _ket_qua(outcome="abstained", answer="", refusal=""))
    du_lieu = client.post("/chat", json={"question": "abc"}).json()
    assert du_lieu["answer"].strip()
    assert "hồ sơ" in du_lieu["answer"].lower()


# ── ③ Lựa chọn giữ cấu trúc ─────────────────────────────────────────────


def test_lua_chon_tra_ve_dang_mang(monkeypatch: pytest.MonkeyPatch) -> None:
    _gan(
        monkeypatch,
        _ket_qua(
            outcome="clarify",
            answer="",
            clarify={
                "question": "Có 3 thủ tục cùng khớp tên.",
                "options": [
                    {"value": "1.115350", "label": "Cấp lại", "hint": "mã 1.115350"},
                    {"value": "1.115345", "label": "Cấp đổi", "hint": "mã 1.115345"},
                ],
            },
        ),
    )
    du_lieu = client.post("/chat", json={"question": "đổi sổ đỏ"}).json()

    assert [o["value"] for o in du_lieu["options"]] == ["1.115350", "1.115345"]
    assert [o["label"] for o in du_lieu["options"]] == ["Cấp lại", "Cấp đổi"]
    # Văn bản vẫn kèm lựa chọn, cho giao diện không đọc `options`.
    assert "Cấp lại" in du_lieu["answer"]


def test_cau_tra_loi_duoc_thi_khong_co_lua_chon(monkeypatch: pytest.MonkeyPatch) -> None:
    _gan(monkeypatch, _ket_qua())
    du_lieu = client.post("/chat", json={"question": "cần gì?"}).json()
    assert du_lieu["options"] == []


# ── ④ Chặn lạm dụng và lặp lại ──────────────────────────────────────────


def test_cau_lap_lai_dung_cache_khong_goi_lai(monkeypatch: pytest.MonkeyPatch) -> None:
    dem = {"lan": 0}

    async def fake(_question: str, **_kwargs) -> dict:
        dem["lan"] += 1
        return _ket_qua()

    monkeypatch.setattr(retrieval, "retrieve", fake)

    client.post("/chat", json={"question": "Cần hồ sơ gì?"})
    client.post("/chat", json={"question": "  cần   HỒ SƠ gì?  "})

    assert dem["lan"] == 1, "câu lặp lại (khác hoa/thường, khoảng trắng) phải dùng cache"


def test_tat_cache_bang_bien_moi_truong(monkeypatch: pytest.MonkeyPatch) -> None:
    dem = {"lan": 0}

    async def fake(_question: str, **_kwargs) -> dict:
        dem["lan"] += 1
        return _ket_qua()

    monkeypatch.setattr(retrieval, "retrieve", fake)
    monkeypatch.setattr(chat_api, "CACHE_TTL_S", 0)

    client.post("/chat", json={"question": "a"})
    client.post("/chat", json={"question": "a"})
    assert dem["lan"] == 2


def test_qua_so_lan_thi_bi_chan(monkeypatch: pytest.MonkeyPatch) -> None:
    _gan(monkeypatch, _ket_qua())
    monkeypatch.setattr(chat_api, "RATE_LIMIT", 2)

    assert client.post("/chat", json={"question": "câu 1"}).status_code == 200
    assert client.post("/chat", json={"question": "câu 2"}).status_code == 200
    bi_chan = client.post("/chat", json={"question": "câu 3"})

    assert bi_chan.status_code == 429
    assert "thử lại sau" in bi_chan.json()["detail"]
    assert int(bi_chan.headers["retry-after"]) >= 1


def test_cau_rong_bi_tu_choi_o_tang_schema() -> None:
    assert client.post("/chat", json={"question": "   "}).status_code == 422
    assert client.post("/chat", json={"question": ""}).status_code == 422


def test_outcome_error_thi_bao_503(monkeypatch: pytest.MonkeyPatch) -> None:
    _gan(monkeypatch, _ket_qua(outcome="error"))
    assert client.post("/chat", json={"question": "abc"}).status_code == 503


def test_chi_giu_nguon_cua_thu_tuc_da_tra_loi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nguồn phải là **căn cứ của câu trả lời**, không phải mọi thứ nhánh lai lấy về.

    Đo được: câu về an toàn thực phẩm trả 3 nguồn, trong đó 2 nguồn thuộc thủ tục đất đai —
    vì nhánh lai lấy cả lĩnh vực lân cận.
    """
    _gan(
        monkeypatch,
        _ket_qua(
            resolution={"code": "1.013855", "name": "Cấp GCN ATTP"},
            citations=[
                {
                    "procedure_code": "1.013855",
                    "procedure_name": "Cấp GCN ATTP",
                    "detail_url": "https://example.test/attp",
                    "document_code": "",
                    "section": "Phí, lệ phí",
                },
                {
                    "procedure_code": "1.115342",
                    "procedure_name": "Đăng ký cấp GCN đất",
                    "detail_url": "https://example.test/dat",
                    "document_code": "",
                },
            ],
        ),
    )
    du_lieu = client.post("/chat", json={"question": "phí bao nhiêu?"}).json()

    ma = [c["title"] for c in du_lieu["citations"]]
    assert len(ma) == 1
    assert "Cấp GCN ATTP" in ma[0]


def test_khong_ro_thu_tuc_thi_giu_moi_nguon_khac_nhau(monkeypatch: pytest.MonkeyPatch) -> None:
    _gan(
        monkeypatch,
        _ket_qua(
            outcome="answered",
            resolution={"code": "", "name": ""},
            citations=[
                {
                    "procedure_code": "1.000001",
                    "procedure_name": "A",
                    "detail_url": "https://example.test/a",
                    "document_code": "",
                },
                {
                    "procedure_code": "1.000002",
                    "procedure_name": "B",
                    "detail_url": "https://example.test/b",
                    "document_code": "",
                },
            ],
        ),
    )
    du_lieu = client.post("/chat", json={"question": "câu hỏi?"}).json()
    assert len(du_lieu["citations"]) == 2

# ══════════════════════════════════════════════════════════════════════════
# STREAMING (SSE) — đường dành cho giao diện người dân
# ══════════════════════════════════════════════════════════════════════════


def _doc_sse(duong_dan: str, cau: str) -> list[tuple[str, dict]]:
    """Đọc toàn bộ khung SSE thành ``[(event, data)]``."""
    su_kien: list[tuple[str, dict]] = []
    with client.stream("POST", duong_dan, json={"question": cau}) as phan_hoi:
        assert phan_hoi.status_code == 200
        assert phan_hoi.headers["content-type"].startswith("text/event-stream")
        ten = ""
        for dong in phan_hoi.iter_lines():
            if dong.startswith("event: "):
                ten = dong.removeprefix("event: ")
            elif dong.startswith("data: "):
                su_kien.append((ten, json.loads(dong.removeprefix("data: "))))
    return su_kien


def _gan_stream(monkeypatch: pytest.MonkeyPatch, mau: list[str] | None = None) -> dict:
    dem: dict = {}

    async def fake_retrieve(
        _question: str,
        *,
        turn_index: int = 1,
        generate: bool = True,
        log_trace: bool = True,
        source: str = "api",
    ) -> dict:
        return _ket_qua(
            resolution={"code": "1.001699", "name": "Cấp GXN"},
            evidence=[{"kind": "chunk", "procedure_code": "1.001699", "content": "Miễn phí."}],
            citations=[
                {
                    "procedure_code": "1.001699",
                    "procedure_name": "Cấp GXN",
                    "detail_url": "https://example.test/1",
                    "document_code": "",
                    "section": "Phí, lệ phí",
                }
            ],
            coverage=[{"request_index": 0, "status": "covered", "facet": "fee"}],
        )

    async def fake_stream(_q, _e, *, thieu=(), requests=(), coverage=(), timeout=0.0):
        dem["coverage"] = list(coverage)
        dem["requests"] = list(requests)
        for manh in mau or ["Thủ tục ", "**miễn phí**", "."]:
            yield manh

    monkeypatch.setattr(retrieval, "retrieve", fake_retrieve)
    monkeypatch.setattr(answer_module, "sinh_stream", fake_stream)
    return dem


def test_sse_phat_meta_roi_tung_mau_roi_done(monkeypatch: pytest.MonkeyPatch) -> None:
    _gan_stream(monkeypatch)
    su_kien = _doc_sse("/chat/stream", "phí bao nhiêu?")

    assert su_kien[0][0] == "start", "phải mở luồng ngay, trước khi tra cứu"
    assert su_kien[1][0] == "meta"
    assert su_kien[1][1]["status"] == "answered"
    assert su_kien[1][1]["procedure"]["procedure_code"] == "1.001699"
    assert su_kien[1][1]["citations"][0]["section"] == "Phí, lệ phí"

    ten = [ten for ten, _ in su_kien]
    assert ten.count("delta") == 3, "mỗi mẩu của mô hình phải thành một sự kiện delta"
    assert ten[-1] == "done"

    ghep = "".join(d["text"] for t, d in su_kien if t == "delta")
    assert ghep == "Thủ tục **miễn phí**."
    assert su_kien[-1][1] == {"answer": ghep, "streamed": True}


def test_sse_cau_hoi_lai_khong_co_delta(monkeypatch: pytest.MonkeyPatch) -> None:
    """Câu hỏi lại do hệ thống dựng, không do mô hình viết → không giả vờ stream."""

    async def fake_retrieve(
        _question: str,
        *,
        turn_index: int = 1,
        generate: bool = True,
        log_trace: bool = True,
        source: str = "api",
    ) -> dict:
        return _ket_qua(
            outcome="clarify",
            answer="",
            clarify={
                "question": "Bạn muốn hỏi thủ tục nào?",
                "options": [{"value": "1.115350", "label": "Cấp lại"}],
            },
        )

    monkeypatch.setattr(retrieval, "retrieve", fake_retrieve)
    su_kien = _doc_sse("/chat/stream", "đổi sổ đỏ")

    assert [t for t, _ in su_kien] == ["start", "meta", "done"]
    assert su_kien[1][1]["status"] == "clarify"
    assert su_kien[1][1]["options"][0]["value"] == "1.115350"
    assert su_kien[2][1]["streamed"] is False
    assert "Bạn muốn hỏi thủ tục nào?" in su_kien[2][1]["answer"]


def test_sse_loi_truoc_khi_phat_thi_tra_cau_du_phong(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mô hình chết trước khi phát mẩu nào → phải có câu trả lời, không phải khung trống."""

    async def fake_retrieve(
        _question: str,
        *,
        turn_index: int = 1,
        generate: bool = True,
        log_trace: bool = True,
        source: str = "api",
    ) -> dict:
        return _ket_qua(
            resolution={"code": "1.001699", "name": "Cấp GXN"},
            evidence=[{"kind": "chunk", "procedure_code": "1.001699", "content": "Miễn phí."}],
            refusal="Dữ liệu chưa ghi nhận.",
            citations=[],
        )

    async def hong(_q, _e, *, thieu=(), requests=(), coverage=(), timeout=0.0):
        raise answer_module.AnswerError("403 quota")
        yield ""  # pragma: no cover — để hàm là generator

    monkeypatch.setattr(retrieval, "retrieve", fake_retrieve)
    monkeypatch.setattr(answer_module, "sinh_stream", hong)

    su_kien = _doc_sse("/chat/stream", "phí bao nhiêu?")
    assert [t for t, _ in su_kien] == ["start", "meta", "done"]
    assert su_kien[-1][1]["streamed"] is False
    assert su_kien[-1][1]["answer"].strip()


def test_sse_cau_lap_lai_phat_lai_thanh_tung_mau(monkeypatch: pytest.MonkeyPatch) -> None:
    dem = {"lan": 0}

    async def fake_retrieve(
        _question: str,
        *,
        turn_index: int = 1,
        generate: bool = True,
        log_trace: bool = True,
        source: str = "api",
    ) -> dict:
        dem["lan"] += 1
        return _ket_qua(
            resolution={"code": "1.001699", "name": "Cấp GXN"},
            evidence=[{"kind": "chunk", "procedure_code": "1.001699", "content": "Miễn phí."}],
        )

    async def fake_stream(_q, _e, *, thieu=(), requests=(), coverage=(), timeout=0.0):
        yield "Miễn phí."

    monkeypatch.setattr(retrieval, "retrieve", fake_retrieve)
    monkeypatch.setattr(answer_module, "sinh_stream", fake_stream)

    _doc_sse("/chat/stream", "phí?")
    su_kien = _doc_sse("/chat/stream", "phí?")

    assert dem["lan"] == 1, "câu lặp lại phải dùng cache"
    ten = [t for t, _ in su_kien]
    assert ten[0] == "start"
    assert ten[1] == "meta"
    assert ten[-1] == "done"

    # Câu cache phải **trông** giống câu mới: có delta, không phải một cục.
    assert "delta" in ten, "câu cache phải được phát lại thành từng mẩu"
    assert su_kien[1][1]["cached"] is True
    ghep = "".join(d["text"] for t, d in su_kien if t == "delta")
    assert ghep.strip() == "Miễn phí."
    assert su_kien[-1][1] == {"answer": "Miễn phí.", "streamed": True}


def test_sse_cau_moi_khong_bi_danh_dau_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    _gan_stream(monkeypatch)
    su_kien = _doc_sse("/chat/stream", "phí bao nhiêu?")
    assert su_kien[1][1]["cached"] is False


def test_cat_mau_khong_che_doi_tu() -> None:
    """Cắt theo ranh giới từ — không để một từ bị chẻ đôi giữa hai mẩu."""
    mau = chat_api._cat_mau("Thủ tục cấp Giấy xác nhận tình trạng hôn nhân", co=20)
    assert "".join(mau).split() == "Thủ tục cấp Giấy xác nhận tình trạng hôn nhân".split()
    assert all(len(m) <= 21 for m in mau), "mỗi mẩu không vượt quá cỡ đã đặt"

def test_nguon_co_ngay_ca_khi_khong_sinh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Đường streaming chạy đồ thị **không sinh**, nhưng nguồn vẫn phải có.

    Nguồn là thứ thuộc về **bằng chứng**, không phải thứ chỉ ra đời sau khi mô hình viết xong.
    Đo được: bản đầu tiên trả `meta.citations = []` vì chỉ bước sinh mới dựng citations.
    """
    from backend.app.workflow import run as run_module

    ket_qua = run_module.RunResult(
        question="phí bao nhiêu?",
        state={
            "evidence": [
                {
                    "kind": "chunk",
                    "procedure_code": "1.001699",
                    "procedure_name": "Cấp GXN",
                    "detail_url": "https://example.test/1",
                    "title": "Phí, lệ phí",
                    "content": "Miễn phí.",
                }
            ],
            "citations": [],
        },
        ms=1,
    )
    assert ket_qua.to_dict()["citations"], "phải dựng được nguồn từ bằng chứng"
    assert ket_qua.to_dict()["citations"][0]["procedure_code"] == "1.001699"


def test_sse_truyen_coverage_vao_buoc_sinh(monkeypatch: pytest.MonkeyPatch) -> None:
    dem = _gan_stream(monkeypatch)
    _doc_sse("/chat/stream", "phí bao nhiêu?")
    assert dem["coverage"] == [
        {"request_index": 0, "status": "covered", "facet": "fee"}
    ]
