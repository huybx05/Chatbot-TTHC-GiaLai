"""Bốn bước truy xuất của luồng — mỗi bước **mỏng**, chỉ gọi phần đã có và đóng gói.

## Nguyên tắc của tệp này

Mỗi bước nhận **trạng thái** và trả về **phần trạng thái cần sửa**. Nó không:

* tự định danh lại (bộ định danh đã chạy trước, việc 13.3),
* tự quyết định từ chối (việc của bước hỏi lại, việc 13.10),
* tự chuyển sang nhánh khác (việc của bước leo thang, việc 13.11).

Nó chỉ: gọi nhánh tương ứng → đổi kết quả sang kiểu bằng chứng chung → báo **tín hiệu**
cho biết nhánh có trả lời được không. Nhờ vậy thêm một nhánh mới chỉ là thêm một bước, không
phải sửa các bước khác.

## Vì sao bước không tự nhúng câu hỏi

Câu hỏi được nhúng **tối đa một lần** cho mỗi lượt, và lần nhúng đó thuộc về bộ định danh
(việc 13.3). Các bước đọc lại vector theo **dấu vết** đã lưu. Bước nào tự nhúng là phá vỡ
nguyên tắc chi phí của cả dự án — và có bài kiểm khẳng định điều này.

"""

from __future__ import annotations

import logging
import time
from typing import Any

from backend.app.config import settings
from backend.app.rag import fact_lookup, graph_query, hybrid, resolve, sections
from backend.app.rag.evidence import (
    Branch,
    from_chunks,
    from_fact,
    from_graph,
    from_sections,
)
from backend.app.workflow.state import AgentState, BranchSignal

logger = logging.getLogger(__name__)

def _gop_thoi_gian(state: AgentState, **them: int) -> dict[str, int]:
    """Gộp thời gian của bước này vào bảng thời gian chung của lượt."""
    timings = {khoa: int(gia_tri) for khoa, gia_tri in (state.get("timings") or {}).items()}
    for khoa, gia_tri in them.items():
        timings[khoa] = int(gia_tri)
    return timings


def _vector_cua(state: AgentState) -> list[float] | None:
    """Lấy lại vector theo dấu vết. ``None`` = câu này không nhúng (có neo sẵn)."""
    dau_vet = str(state.get("vector_hash") or "")
    return resolve.get_vector(dau_vet) if dau_vet else None


def _ma_cua_thu_tuc(state: AgentState) -> str:
    """Mã thủ tục đã định danh được, nếu có."""
    codes = state.get("codes") or []
    if codes:
        return str(codes[0])
    return str((state.get("resolution") or {}).get("code") or "")


def _patch(
    state: AgentState,
    *,
    evidence: list[dict[str, Any]],
    signal: BranchSignal,
    branch: Branch,
    ms: int,
    error: str = "",
    branch_reason: str = "",
    clarify: dict[str, Any] | None = None,
    gate: dict[str, Any] | None = None,
    thieu: list[str] | None = None,
) -> dict[str, Any]:
    """Bản vá trạng thái chung của mọi bước trong nhánh.

    Một chỗ duy nhất để biết bước nhánh ghi những trường nào — nếu mỗi nhánh tự dựng từ điển
    thì trường nào quên điền sẽ không ai báo, và ``ket_thuc`` đọc phải trường rỗng.
    """
    patch: dict[str, Any] = {
        "branch": branch.value if isinstance(branch, Branch) else str(branch),
        "branch_signal": signal.value,
        "evidence": list(evidence),
        "error": error,
        "branch_reason": branch_reason,
        "timings": _gop_thoi_gian(state, branch_ms=int(ms)),
    }
    if clarify is not None:
        patch["clarify"] = clarify
    if gate is not None:
        patch["gate"] = gate
    if thieu is not None:
        patch["thieu"] = list(thieu)
    return patch


async def node_fact_lookup(state: AgentState) -> dict[str, Any]:
    """Sáu thuộc tính định danh của thủ tục đã có mã.

    Không có mã thì **không** tự đi tìm: đó là việc của bộ định danh. Báo tín hiệu
    ``NEED_IDENTITY`` để tầng trên biết phải hỏi lại hoặc chuyển nhánh.
    """
    bat_dau = time.perf_counter()
    code = _ma_cua_thu_tuc(state)
    codes = [code] if code else []

    if not codes:
        return _patch(
            state,
            evidence=[],
            signal=BranchSignal.NEED_IDENTITY,
            branch=Branch.FACT_LOOKUP,
            ms=int((time.perf_counter() - bat_dau) * 1000),
            error="",
            branch_reason="Thiếu mã thủ tục",
        )

    facts = await fact_lookup.get_facts(codes)
    evidence = [muc for f in facts for muc in from_fact(f)]
    ms = int((time.perf_counter() - bat_dau) * 1000)
    return _patch(
        state,
        evidence=evidence,
        signal=BranchSignal.OK if evidence else BranchSignal.EMPTY,
        branch=Branch.FACT_LOOKUP,
        ms=ms,
        branch_reason=f"PostgreSQL · {len(codes)} mã",
    )


# ── Bước 2: truy vấn đồ thị (Neo4j) ─────────────────────────────────────


async def node_graph(state: AgentState) -> dict[str, Any]:
    """Chuyển **thẳng** kết quả đồ thị sang bằng chứng chung.

    Đồ thị có ba kết cục riêng (không phải câu quan hệ / thiếu định danh / nhiều lựa chọn).
    Bước này **không** nuốt chúng: mỗi kết cục thành một tín hiệu để bước leo thang đọc.
    """
    bat_dau = time.perf_counter()
    cau = str(state.get("question") or "")
    vector = _vector_cua(state)
    frame = state.get("question_frame") or {}
    requested_facets = [
        str(request.get("facet") or "") for request in (frame.get("requests") or [])
    ]
    code = _ma_cua_thu_tuc(state)
    codes = [code] if code else []

    async def lay_vector() -> list[float]:
        return vector or []

    try:
        evidence_graph = await graph_query.answer(
            cau,
            codes=codes or None,
            limit=max(int(state.get("max_retry") or 2) * 10, 20),
            get_vector=lay_vector if vector else None,
            **({"requested_facets": requested_facets} if requested_facets else {}),
        )
    except Exception as exc:  # noqa: BLE001 — đồ thị lỗi thì báo tín hiệu, không sập lượt
        logger.warning("Bước đồ thị lỗi: %s", exc)
        return _patch(
            state,
            evidence=[],
            signal=BranchSignal.ERROR,
            branch=Branch.GRAPH,
            ms=int((time.perf_counter() - bat_dau) * 1000),
            error=f"đồ thị lỗi: {str(exc)[:160]}",
            branch_reason="Neo4j · lỗi",
        )

    muc = from_graph(evidence_graph)
    tin_hieu = _tin_hieu_do_thi(evidence_graph.intent, co_du_lieu=bool(muc))
    ms = int((time.perf_counter() - bat_dau) * 1000)
    return _patch(
        state,
        evidence=muc,
        signal=tin_hieu,
        branch=Branch.GRAPH,
        ms=ms,
        branch_reason=_ly_do_do_thi(evidence_graph),
        clarify=_clarify_tu_do_thi(evidence_graph),
    )


def _ly_do_do_thi(evidence: graph_query.GraphEvidence) -> str:
    """Lý do **ngắn** của bước đồ thị.

    Khi đồ thị không trả bằng chứng, lý do thật nằm ở ``note`` ("Dữ liệu chưa ghi nhận thủ
    tục nào ở Cấp huyện…") — đó là thứ đáng hiện, không phải mã intent. Còn lại chỉ ghi
    ``Neo4j`` kèm số phần, vì người đọc cần biết **nguồn nào đã trả lời**, không cần đọc một
    câu mô tả dài.
    """
    if evidence.intent in {"NOT_GRAPH", "NONE"} and evidence.note:
        return " ".join(evidence.note.split())[:200]
    return "Neo4j" + (f" · {len(evidence.parts)} phần" if evidence.parts else "")


def _tin_hieu_do_thi(intent: str, *, co_du_lieu: bool) -> BranchSignal:
    """Đổi kết cục của đồ thị thành tín hiệu của luồng."""
    if intent == "NOT_GRAPH":
        return BranchSignal.NOT_GRAPH
    if intent == "NEED_IDENTITY":
        return BranchSignal.NEED_IDENTITY
    if intent == "CLARIFY":
        return BranchSignal.CLARIFY
    if intent in {"NONE", "ERROR"}:
        return BranchSignal.ERROR
    return BranchSignal.OK if co_du_lieu else BranchSignal.EMPTY


def _clarify_tu_do_thi(evidence: graph_query.GraphEvidence) -> dict[str, Any]:
    """Nội dung hỏi lại mà đồ thị đã dựng sẵn (nếu có)."""
    if not evidence.clarify:
        return {"question": "", "options": []}
    return {
        "question": evidence.clarify_question,
        "options": [
            {
                "value": str(o.get("value") or ""),
                "label": str(o.get("label") or ""),
                "hint": str(o.get("hint") or ""),
            }
            for o in evidence.options
        ],
    }


# ── Bước 3: tìm kiếm lai (Elasticsearch + Qdrant) ────────────────────────


async def node_hybrid(state: AgentState) -> dict[str, Any]:
    """Tìm kiếm lai, dùng lại vector đã có. Có mã thủ tục thì lọc theo mã.

    Giữ nguyên mặc định của nhánh: **không** rerank đầy đủ (đo được là làm giảm độ chính xác
    mục), cổng từ chối chỉ chạy khi chưa định danh được — hai điều đó do ``hybrid`` tự lo,
    bước này không ép.
    """
    bat_dau = time.perf_counter()
    cau = str(state.get("question") or "")
    vector = _vector_cua(state)

    if not vector:
        return _patch(
            state,
            evidence=[],
            signal=BranchSignal.NEED_IDENTITY,
            branch=Branch.HYBRID,
            ms=int((time.perf_counter() - bat_dau) * 1000),
            error="",
            branch_reason="Chưa nhúng câu hỏi",
        )

    # Mã để **lọc** truy xuất: ưu tiên mã đã xác thực ở tầng ①, không có thì dùng mã
    # grounding đã ghi vào ``resolution``. Hai nguồn này khác nhau về độ tin cậy, nên phần
    # cổng bên dưới chỉ dựa trên mã **đã xác thực** — xem ``use_gate``.
    code = _ma_cua_thu_tuc(state)
    codes = [code] if code else []

    # Cổng từ chối bật **có điều kiện**, dựa trên hai điều đo được:
    #
    # * có mã đã xác thực → mặc nhiên trong phạm vi, không cần chấm;
    # * câu **nhiều ý** → điểm bị chia nhỏ (đo được câu hợp lệ 2 ý chỉ 0,6219, cách ngưỡng
    #   0,60 đúng 0,0219) → chấm là từ chối oan đúng lớp câu giá trị nhất.
    #
    # Còn lại (một ý, không mã) mới chấm: đó là lớp "trông giống TTHC mà dữ liệu không có",
    # lớp mà router **không** thấy được vì nó không đọc dữ liệu. Đo trên 20 câu ngoài phạm vi:
    # cổng bắt thêm ca *"giấy phép lái xe B2"* (0,2684) mà router cho qua.
    parts = state.get("parts") or []
    # Cổng chỉ miễn khi có mã **đã xác thực** (``state["codes"]``, tra PostgreSQL). Mã từ
    # grounding không đủ để kết luận câu hỏi nằm trong phạm vi: nếu miễn cổng theo nó, đúng
    # lớp câu "trông giống TTHC mà dữ liệu không có" sẽ lọt qua.
    verified = list(state.get("codes") or [])
    use_gate = not verified and len(parts) <= 1

    try:
        ket_qua = await hybrid.hybrid(
            cau, vector=vector, codes=codes, use_gate=use_gate
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Bước tìm kiếm lai lỗi: %s", exc)
        return _patch(
            state,
            evidence=[],
            signal=BranchSignal.ERROR,
            branch=Branch.HYBRID,
            ms=int((time.perf_counter() - bat_dau) * 1000),
            error=f"tìm kiếm lai lỗi: {str(exc)[:160]}",
            branch_reason="Hybrid · lỗi",
        )

    # Truy xuất 30 đoạn để chọn đúng, nhưng **ngữ cảnh trả lời chỉ lấy 6 đoạn đầu**. Mỗi đoạn
    # ~600 ký tự, nên 30 đoạn là ~18 000 ký tự — vượt xa nhu cầu của một câu trả lời và làm
    # loãng phần quan trọng. Đo được: nhánh lai từng đẩy 51–56 mục vào ngữ cảnh cho một câu.
    so_luong = max(1, int(settings.hybrid_context_k or 6))
    muc = from_chunks(ket_qua.candidates[:so_luong])
    ms = int((time.perf_counter() - bat_dau) * 1000)
    tin_hieu = BranchSignal.OK if muc else BranchSignal.EMPTY
    if ket_qua.refused:
        tin_hieu = BranchSignal.EMPTY
    return _patch(
        state,
        evidence=muc,
        signal=tin_hieu,
        branch=Branch.HYBRID,
        ms=ms,
        branch_reason=f"Hybrid · {len(muc)} đoạn",
        gate={
            "score": float(ket_qua.gate_score or 0.0),
            "skipped": bool(ket_qua.gate_skipped),
            "refused": bool(ket_qua.refused),
            "reason": "cổng từ chối" if ket_qua.refused else "",
        },
    )


# ── Bước 3b: bổ sung mục nội dung theo khía cạnh câu hỏi ─────────────────


def _khia_canh_can(parts: list[dict[str, Any]]) -> list[str]:
    """Các khía cạnh câu hỏi yêu cầu, theo đúng thứ tự người dùng hỏi."""
    can: list[str] = []
    for phan in parts:
        for need in phan.get("need") or ():
            if need not in can:
                can.append(need)
    return can


def _khia_canh_da_co(evidence: list[dict[str, Any]]) -> set[str]:
    """Khía cạnh mà bằng chứng hiện tại đã phủ."""
    return {
        khia_canh
        for muc in evidence
        if (khia_canh := sections.khia_canh_cua(str(muc.get("section_type") or "")))
    }


def khia_canh_con_thieu(state: AgentState) -> list[str]:
    """Khía cạnh câu hỏi **yêu cầu mà bằng chứng chưa phủ**.

    Đây là chỗ biến "câu hỏi nhiều ý" thành việc làm được mà **không** cần luật đoán câu chữ:
    router đã nói câu hỏi cần những khía cạnh nào; hàm này chỉ so với những gì đã có.

    Câu **một ý** cũng phải bù. Cổng cũ (``len(parts) < 2``) từng làm hỏng đúng loại câu đó:

        "cho tôi biết **trình tự thực hiện** của thủ tục cấp giấy xác nhận tình trạng hôn nhân"

    Câu này trúng kho đệm, mà kho đệm chỉ có mục **hồ sơ**; cổng theo số ý chặn bước bù, nên
    bằng chứng không có ``STEPS`` và mô hình viết "dữ liệu chưa ghi nhận trình tự" — trong khi
    ``STEPS`` của thủ tục đó dài 4 375 ký tự trong PostgreSQL.

    Điều kiện duy nhất còn lại là "khía cạnh được hỏi mà bằng chứng chưa phủ". Chi phí khi phải
    bù: **một** truy vấn SQL theo ``(mã, mục)``, không gọi mô hình.
    """
    parts = state.get("parts") or []
    if not parts:
        return []

    da_co = _khia_canh_da_co(list(state.get("evidence") or []))
    return [need for need in _khia_canh_can(parts) if need not in da_co]


async def node_bo_sung_muc(state: AgentState) -> dict[str, Any]:
    """Bước ③b: lấy thêm những mục mà nhánh đã chạy **không** lấy.

    Không phải "thêm một lần tìm kiếm nữa": chỉ đọc đúng dòng của đúng thủ tục trong
    PostgreSQL, theo khía cạnh mà router đã nêu. Nhờ vậy câu hỏi ba ý không còn nhận câu trả
    lời một ý, và câu "chưa ghi nhận thời hạn" không còn xuất hiện khi `PROCESSING_TIME` có.

    Bước này **không đổi kết cục**: nó chỉ làm ngữ cảnh đầy hơn.
    """
    parts = list(state.get("parts") or [])
    thieu = khia_canh_con_thieu(state)
    if not thieu:
        return {}

    codes = [str(ma) for ma in (state.get("codes") or [])]
    ma_dinh_danh = str((state.get("resolution") or {}).get("code") or "")
    if not codes and ma_dinh_danh:
        codes = [ma_dinh_danh]
    if not codes:
        return {"thieu": thieu}

    bat_dau = time.perf_counter()
    rows = await sections.theo_khia_canh(codes, thieu)
    them = from_sections(rows)
    da_co = list(state.get("evidence") or []) + them
    con_thieu = [need for need in _khia_canh_can(parts) if need not in _khia_canh_da_co(da_co)]
    ms = int((time.perf_counter() - bat_dau) * 1000)

    if not them:
        return {"thieu": con_thieu, "timings": _gop_thoi_gian(state, branch_ms=ms)}

    # Xếp theo đúng thứ tự khía cạnh mà câu hỏi hỏi — người đọc thấy phần trả lời đi theo thứ
    # tự họ hỏi, không theo thứ tự bảng.
    thu_tu = {need: i for i, need in enumerate(_khia_canh_can(parts))}
    them.sort(key=lambda muc: thu_tu.get(sections.khia_canh_cua(muc["section_type"]) or "", 99))

    return _patch(
        state,
        evidence=list(state.get("evidence") or []) + them,
        signal=BranchSignal.OK,
        branch=Branch(state.get("branch") or Branch.HYBRID.value),
        ms=ms,
        thieu=con_thieu,
    )


NODES = {
    Branch.FACT_LOOKUP.value: node_fact_lookup,
    Branch.GRAPH.value: node_graph,
    Branch.HYBRID.value: node_hybrid,
}
