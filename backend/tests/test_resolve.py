"""Khoá bộ định danh thống nhất (việc 13.3).

Hai điều quan trọng nhất cần khoá:

① **Mỗi câu nhúng tối đa một lần.** Đây là quyết định chi phí của cả dự án; nhúng hai lần
   nghĩa là trả tiền hai lần và chậm gấp đôi cho cùng một câu.
② **Định danh chạy một lần cho mỗi bước.** Mỗi bước gọi lại là mỗi cơ hội để hai bước ra hai
   kết quả khác nhau.

Bài kiểm chạy **không cần mạng**: bốn nguồn định danh đều được thay bằng hàm giả. Dùng
``asyncio.run`` thay vì plugin asyncio để không phải thêm phụ thuộc chỉ cho việc kiểm thử.
"""

from __future__ import annotations

import asyncio

import pytest
from backend.app.rag import fact_lookup, graph_query, resolve, resolver
from backend.app.rag.graph_query import (
    DocumentMatch,
    DocumentResolution,
    EntityMatch,
)


class _Dem:
    """Đếm số lần gọi từng nguồn — để khẳng định "chạy đúng một lần"."""

    def __init__(self) -> None:
        self.ma = 0
        self.nhung = 0


def _chay(coro):
    """Chạy một coroutine trong bài kiểm đồng bộ."""
    return asyncio.run(coro)


def _rong_doc() -> DocumentResolution:
    return DocumentResolution()



@pytest.fixture
def gia(monkeypatch: pytest.MonkeyPatch) -> _Dem:
    """Thay cả bốn nguồn định danh bằng hàm giả, và đếm số lần gọi."""
    dem = _Dem()

    async def fake_resolve_codes(question: str):
        dem.ma += 1
        return fact_lookup.CodeLookup(asked=("1004873",), matched=("1.004873",))

    async def fake_vocabulary():
        return graph_query.Vocabulary(run_id="test")

    async def fake_resolve_procedure(question: str, *, codes=None, get_vector=None):
        if codes:
            return resolver.ProcedureResolution(code=codes[0], method="code", confidence=1.0)
        vector = await get_vector()
        assert vector, "phải có vector trước khi định danh theo tên"
        return resolver.ProcedureResolution(
            code="1.001699",
            name="Cấp Giấy xác nhận khuyết tật",
            method="vector",
            confidence=0.85,
            note="top-5 chỉ có một thủ tục",
        )

    async def fake_embed(text: str) -> list[float]:
        dem.nhung += 1
        return [0.11, 0.22, 0.33]

    monkeypatch.setattr(fact_lookup, "resolve_codes", fake_resolve_codes)
    monkeypatch.setattr(graph_query, "vocabulary", fake_vocabulary)
    monkeypatch.setattr(graph_query, "match_documents", lambda q, v: _rong_doc())
    monkeypatch.setattr(graph_query, "match_entities", lambda q, v: (None, []))
    monkeypatch.setattr(resolver, "resolve_procedure", fake_resolve_procedure)
    monkeypatch.setattr(resolver.embeddings, "embed", fake_embed)
    resolve.reset_vector_cache()
    return dem


@pytest.fixture
def gia_khong_ma(monkeypatch: pytest.MonkeyPatch, gia: _Dem) -> _Dem:
    """Như ``gia`` nhưng câu **không nêu mã** — để kiểm đường định danh theo tên."""

    async def fake_resolve_codes(question: str):
        gia.ma += 1
        return fact_lookup.CodeLookup()

    monkeypatch.setattr(fact_lookup, "resolve_codes", fake_resolve_codes)
    return gia


# ── Số lần nhúng: 0 hoặc 1 ───────────────────────────────────────────────


def test_co_ma_thi_khong_nhung(gia: _Dem) -> None:
    """Câu đã có mã thủ tục: dừng ở bước ①, không tốn một lần nhúng nào."""
    kq = _chay(resolve.resolve("Thủ tục 1.004873 là gì?"))
    assert kq.codes == ["1.004873"]
    assert kq.ma == "1.004873"
    assert kq.embedding_used is False
    assert kq.dau_vet_vector == ""
    assert gia.nhung == 0, "có mã rồi thì không được nhúng"


def test_khong_co_ma_thi_nhung_dung_mot_lan(gia_khong_ma: _Dem) -> None:
    kq = _chay(resolve.resolve("giấy xác nhận khuyết tật do cơ quan nào ban hành"))
    assert kq.embedding_used is True
    assert kq.dau_vet_vector, "phải có dấu vết vector"
    assert kq.ma == "1.001699"
    assert kq.ten == "Cấp Giấy xác nhận khuyết tật"
    assert kq.procedure.method == "vector"
    assert gia_khong_ma.nhung == 1, f"phải nhúng đúng 1 lần, đang là {gia_khong_ma.nhung}"


def test_dinh_danh_ma_chi_chay_mot_lan(gia_khong_ma: _Dem) -> None:
    _chay(resolve.resolve("giấy xác nhận khuyết tật"))
    assert gia_khong_ma.ma == 1


def test_vector_duoc_cat_va_tra_lai_duoc(gia_khong_ma: _Dem) -> None:
    """Trạng thái chỉ giữ dấu vết; vector thật phải tra lại được để nhánh lai dùng."""
    kq = _chay(resolve.resolve("giấy xác nhận khuyết tật"))
    assert resolve.get_vector(kq.dau_vet_vector) == [0.11, 0.22, 0.33]
    assert resolve.get_vector("khong-ton-tai") is None


# ── Ánh xạ sang trạng thái ───────────────────────────────────────────────


def test_state_patch_khop_truong_trang_thai(gia: _Dem) -> None:
    """Bước này chỉ được điền **sáu** trường của trạng thái, và đúng tên."""
    from backend.app.workflow.state import STATE_FIELDS

    kq = _chay(resolve.resolve("giấy xác nhận khuyết tật"))
    patch = kq.state_patch()
    assert set(patch) == {
        "codes",
        "documents",
        "entity",
        "entity_ambiguous",
        "needs_antecedent",
        "vector_hash",
        "embedding_used",
        "resolution",
    }
    assert set(patch) <= set(STATE_FIELDS)


def test_state_patch_du_truong_con_cua_resolution(gia: _Dem) -> None:
    """``resolution`` trong trạng thái phải có đủ bảy khoá đã khai báo."""
    from backend.app.workflow.state import ResolutionInfo

    kq = _chay(resolve.resolve("giấy xác nhận khuyết tật"))
    assert set(kq.state_patch()["resolution"]) == set(ResolutionInfo.__annotations__)


# ── Văn bản và thực thể đóng ─────────────────────────────────────────────


def test_document_va_entity_duoc_dien(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_codes(question: str):
        return fact_lookup.CodeLookup()

    async def fake_vocabulary():
        return graph_query.Vocabulary(run_id="test")

    monkeypatch.setattr(fact_lookup, "resolve_codes", fake_codes)
    monkeypatch.setattr(graph_query, "vocabulary", fake_vocabulary)
    monkeypatch.setattr(
        graph_query,
        "match_documents",
        lambda q, v: DocumentResolution(
            unique=DocumentMatch(
                key="102/2024/ND CP", name="Nghị định 102/2024", matched_by="number"
            )
        ),
    )
    monkeypatch.setattr(
        graph_query,
        "match_entities",
        lambda q, v: (EntityMatch(kind="co_quan", value="Bộ Y tế", label="Bộ Y tế"), []),
    )

    kq = _chay(resolve.resolve("Nghị định 102/2024 do Bộ Y tế ban hành quy định gì"))
    assert kq.documents == ["102/2024/ND CP"]
    assert kq.entity == {"kind": "co_quan", "value": "Bộ Y tế", "label": "Bộ Y tế"}


def test_nhieu_thuc_the_cung_khop_thi_ghi_chu(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mơ hồ về thực thể phải để lại ghi chú để bước hỏi lại biết đường xử lý."""

    async def fake_codes(question: str):
        return fact_lookup.CodeLookup()

    async def fake_vocabulary():
        return graph_query.Vocabulary(run_id="test")

    monkeypatch.setattr(fact_lookup, "resolve_codes", fake_codes)
    monkeypatch.setattr(graph_query, "vocabulary", fake_vocabulary)
    monkeypatch.setattr(graph_query, "match_documents", lambda q, v: _rong_doc())
    monkeypatch.setattr(
        graph_query,
        "match_entities",
        lambda q, v: (
            None,
            [
                EntityMatch(kind="co_quan", value="Bộ Y tế", label="Bộ Y tế"),
                EntityMatch(kind="co_quan", value="Bộ Tư pháp", label="Bộ Tư pháp"),
            ],
        ),
    )

    kq = _chay(resolve.resolve("Bộ Y tế và Bộ Tư pháp ban hành văn bản nào"))
    assert kq.entity is None
    assert any("nhiều thực thể" in ghi_chu for ghi_chu in kq.notes)


# ── Hỏng nguồn nào cũng không được làm sập lượt ──────────────────────────


def test_loi_tung_buoc_khong_lam_sap(monkeypatch: pytest.MonkeyPatch) -> None:
    async def hong(*_a, **_k):
        raise RuntimeError("PostgreSQL sập")

    async def fake_vocabulary():
        return graph_query.Vocabulary(run_id="test")

    async def fake_proc(question: str, *, codes=None, get_vector=None):
        return resolver.ProcedureResolution(note="không có mã")

    monkeypatch.setattr(fact_lookup, "resolve_codes", hong)
    monkeypatch.setattr(graph_query, "vocabulary", fake_vocabulary)
    monkeypatch.setattr(graph_query, "match_documents", lambda q, v: _rong_doc())
    monkeypatch.setattr(graph_query, "match_entities", lambda q, v: (None, []))
    monkeypatch.setattr(resolver, "resolve_procedure", fake_proc)

    kq = _chay(resolve.resolve("câu hỏi bất kỳ"))
    assert kq.ma == ""
    assert kq.co_dinh_danh is False
    assert any("định danh mã lỗi" in ghi_chu for ghi_chu in kq.notes)


def test_tu_dien_hong_van_di_tiep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_codes(question: str):
        return fact_lookup.CodeLookup()

    async def hong_vocab():
        raise RuntimeError("Neo4j sập")

    async def fake_names():
        return {"1.001699": "Cấp Giấy xác nhận khuyết tật"}

    async def fake_proc(question: str, *, codes=None, get_vector=None):
        return resolver.ProcedureResolution(code="1.001699", method="vector", confidence=0.9)

    monkeypatch.setattr(fact_lookup, "resolve_codes", fake_codes)
    monkeypatch.setattr(graph_query, "vocabulary", hong_vocab)
    monkeypatch.setattr(resolver, "resolve_procedure", fake_proc)

    kq = _chay(resolve.resolve("giấy xác nhận khuyết tật"))
    assert kq.ma == "1.001699", "từ điển hỏng nhưng định danh theo tên vẫn phải chạy"
    assert any("văn bản/thực thể lỗi" in ghi_chu for ghi_chu in kq.notes)


# ── Kho vector ───────────────────────────────────────────────────────────


def test_hash_on_dinh_va_phan_biet() -> None:
    assert resolve.vector_hash([0.1, 0.2]) == resolve.vector_hash([0.1, 0.2])
    assert resolve.vector_hash([0.1, 0.2]) != resolve.vector_hash([0.1, 0.3])
    assert resolve.vector_hash([]) == ""


def test_kho_vector_gioi_han_so_muc(monkeypatch: pytest.MonkeyPatch) -> None:
    """Kho phải có giới hạn: không giới hạn thì một phiên dài sẽ ăn hết bộ nhớ."""
    monkeypatch.setattr(resolve, "VECTOR_CACHE_MAX", 3)
    resolve.reset_vector_cache()
    dau_vet = [resolve.remember_vector([float(i)] * 4) for i in range(5)]
    assert resolve.get_vector(dau_vet[0]) is None, "mục cũ nhất phải bị bỏ"
    assert resolve.get_vector(dau_vet[1]) is None
    assert resolve.get_vector(dau_vet[4]) is not None
    resolve.reset_vector_cache()


def test_cat_cung_vector_hai_lan_khong_nhan_doi() -> None:
    resolve.reset_vector_cache()
    v = [0.5, 0.6, 0.7]
    a = resolve.remember_vector(v)
    b = resolve.remember_vector(list(v))
    assert a == b
    assert resolve.get_vector(a) == v
    resolve.reset_vector_cache()


def test_cau_thong_ke_khong_nhung(gia_khong_ma: _Dem) -> None:
    """Câu thống kê không cần biết thủ tục nào — nhúng là thừa ~145 ms mỗi câu.

    Đo được: ba câu "Lĩnh vực nào nhiều thủ tục nhất", "Cơ quan nào ban hành nhiều thủ tục
    nhất", "Văn bản nào làm căn cứ cho nhiều thủ tục nhất" đều bị nhúng trước khi thêm luật
    "khớp hình dạng không cần tham số thì không định danh".
    """
    for cau in (
        "Lĩnh vực nào nhiều thủ tục nhất?",
        "Cơ quan nào ban hành nhiều thủ tục nhất?",
        "Văn bản nào làm căn cứ cho nhiều thủ tục nhất?",
    ):
        kq = _chay(resolve.resolve(cau))
        assert kq.embedding_used is False, cau
    assert gia_khong_ma.nhung == 0


def test_cau_ngoai_pham_vi_van_nhung(gia_khong_ma: _Dem) -> None:
    """Câu không khớp hình dạng nào thì **phải** nhúng — đó là cách duy nhất biết nó
    ngoài phạm vi, và biết nó nói về thủ tục nào (nếu có)."""
    kq = _chay(resolve.resolve("thời tiết Gia Lai hôm nay thế nào"))
    assert kq.embedding_used is True
    assert gia_khong_ma.nhung == 1


# ── Đại từ chỉ định không có tiền ngữ ───────────────────────────────────


def test_dai_tu_dau_cau_thi_khong_dinh_danh(gia_khong_ma: _Dem) -> None:
    """Hệ thống không có bộ nhớ hội thoại → "thủ tục này" ở đầu câu không trỏ vào đâu.

    Đo được: câu *"Thủ tục này cần những giấy tờ nào?"* từng bị gán cho thủ tục hôn nhân
    (1.004873) và trả 51 đoạn văn về hôn nhân — sai chủ đề mà trông rất tự tin.
    """
    kq = _chay(resolve.resolve("Thủ tục này cần những giấy tờ nào?"))
    assert kq.needs_antecedent is True
    assert kq.ma == ""
    assert not kq.procedure.code
    assert "đại từ" in kq.procedure.note
    assert gia_khong_ma.nhung == 0, "biết là thiếu tiền ngữ thì không cần nhúng"


def test_co_ten_thu_tuc_truoc_dai_tu_thi_du_tien_ngu(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tiền ngữ nằm **trong chính câu hỏi** thì vẫn hiểu được."""

    async def fake_names():
        return {"1.001699": "Cấp Giấy xác nhận khuyết tật"}

    async def fake_proc(question: str, *, codes=None, get_vector=None):
        return resolver.ProcedureResolution(code="1.001699", method="vector", confidence=0.9)

    async def fake_codes(question: str):
        return fact_lookup.CodeLookup()

    async def fake_vocabulary():
        return graph_query.Vocabulary(run_id="test")

    monkeypatch.setattr(resolver, "procedure_names", fake_names)
    monkeypatch.setattr(resolver, "resolve_procedure", fake_proc)
    monkeypatch.setattr(fact_lookup, "resolve_codes", fake_codes)
    monkeypatch.setattr(graph_query, "vocabulary", fake_vocabulary)
    monkeypatch.setattr(graph_query, "match_documents", lambda q, v: _rong_doc())
    monkeypatch.setattr(graph_query, "match_entities", lambda q, v: (None, []))

    kq = _chay(
        resolve.resolve(
            "Tôi muốn làm thủ tục cấp Giấy xác nhận khuyết tật. Thủ tục này cần giấy tờ gì?"
        )
    )
    assert kq.needs_antecedent is False, "có tên thủ tục trước đại từ nên vẫn hiểu được"
    assert kq.ma == "1.001699"


def test_khong_co_dai_tu_thi_khong_bi_chan(gia_khong_ma: _Dem) -> None:
    kq = _chay(resolve.resolve("giấy xác nhận khuyết tật do cơ quan nào ban hành"))
    assert kq.needs_antecedent is False


# ── Thực thể không được chặn định danh tên ──────────────────────────────


def test_thuc_the_linh_vuc_khong_chan_dinh_danh_ten(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lĩnh vực chỉ là manh mối, không phải câu trả lời.

    Đo được: *"quán cơm … xin giấy chứng nhận an toàn thực phẩm hết bao nhiêu tiền phí"* khớp
    lĩnh vực "An toàn thực phẩm", nên bản cũ **bỏ qua** định danh tên; router thấy không có mã
    rồi kết luận "không có thủ tục" — trong khi 1.013855 có trong dữ liệu.
    """
    goi = {"proc": 0}

    async def fake_codes(question: str):
        return fact_lookup.CodeLookup()

    async def fake_vocabulary():
        return graph_query.Vocabulary(run_id="test")

    async def fake_proc(question: str, *, codes=None, get_vector=None):
        goi["proc"] += 1
        return resolver.ProcedureResolution(code="1.013855", method="vector", confidence=0.79)

    monkeypatch.setattr(fact_lookup, "resolve_codes", fake_codes)
    monkeypatch.setattr(graph_query, "vocabulary", fake_vocabulary)
    monkeypatch.setattr(graph_query, "match_documents", lambda q, v: _rong_doc())
    monkeypatch.setattr(
        graph_query,
        "match_entities",
        lambda q, v: (
            EntityMatch(kind="linh_vuc", value="An toàn thực phẩm", label="An toàn thực phẩm"),
            [],
        ),
    )
    monkeypatch.setattr(resolver, "resolve_procedure", fake_proc)

    kq = _chay(
        resolve.resolve("xin giấy chứng nhận an toàn thực phẩm hết bao nhiêu tiền phí")
    )
    assert goi["proc"] == 1, "câu hỏi nội dung vẫn phải định danh tên"
    assert kq.ma == "1.013855"


def test_thuc_the_co_quan_van_du_khi_cau_la_liet_ke(monkeypatch: pytest.MonkeyPatch) -> None:
    """Câu liệt kê theo cơ quan thì thực thể **đã đủ** — không tốn lần nhúng nào."""
    goi = {"proc": 0}

    async def fake_codes(question: str):
        return fact_lookup.CodeLookup()

    async def fake_vocabulary():
        return graph_query.Vocabulary(run_id="test")

    async def fake_proc(question: str, *, codes=None, get_vector=None):
        goi["proc"] += 1
        return resolver.ProcedureResolution()

    monkeypatch.setattr(fact_lookup, "resolve_codes", fake_codes)
    monkeypatch.setattr(graph_query, "vocabulary", fake_vocabulary)
    monkeypatch.setattr(graph_query, "match_documents", lambda q, v: _rong_doc())
    monkeypatch.setattr(
        graph_query,
        "match_entities",
        lambda q, v: (EntityMatch(kind="co_quan", value="Bộ Y tế", label="Bộ Y tế"), []),
    )
    monkeypatch.setattr(resolver, "resolve_procedure", fake_proc)

    _chay(resolve.resolve("Bộ Y tế quy định thủ tục nào về khuyết tật?"))
    assert goi["proc"] == 0, "thực thể đã đủ cho câu liệt kê, không cần định danh tên"