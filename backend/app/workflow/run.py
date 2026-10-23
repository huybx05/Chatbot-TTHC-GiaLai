"""**Lối vào duy nhất** của luồng trả lời — mọi thứ bên ngoài chỉ gọi hàm ở đây.

## Vì sao phải có đúng một lối vào

Trước việc này, ba nơi cùng dựng câu trả lời: trang admin gọi lẻ từng động cơ, ``api/chat.py``
chưa có gì, và bảng thử truy xuất có thứ tự tầng riêng. Ba nơi dựng ba kiểu kết quả là nguồn
gốc của loại lỗi đã gặp ba lần ở giao diện: *backend trả thiếu trường, React vỡ trang trắng*.

Từ nay: ``ask()`` gọi đồ thị, trả **một** kiểu kết quả, và ghi **một** dòng vết.

## Mốc 1 trả về cái gì

Mốc này **chưa có bước sinh câu trả lời** (việc 13.13) và **chưa có bước kiểm chứng**
(việc 13.14). Nên kết quả là **bằng chứng đã tìm được**, không phải câu văn trả lời người dân:

* ``outcome = answered`` nghĩa là *"tìm được bằng chứng"*, **không** phải *"đã có câu trả lời"*;
* ``evidence`` là danh sách mục đã chuẩn hoá, mỗi mục có ``kind`` cho biết nó thuộc loại gì;
* ``clarify`` có nội dung khi phải hỏi lại;
* ``timings`` cho biết thời gian từng chặng.

``tom_tat()`` in ra bản đọc được, và nói rõ **chưa sinh câu trả lời** — để không ai đọc nhầm
bằng chứng thành câu trả lời.

## Ghi vết một dòng

Mỗi câu đúng một dòng, đủ để trả lời "câu này đi nhánh nào, vì sao, mất bao lâu, tốn bao nhiêu
lần nhúng" mà không cần mở trình gỡ lỗi. Đây cũng là dữ liệu thô cho báo cáo ở việc 13.18.
"""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass
from typing import Any

from backend.app.workflow import trace_log
from backend.app.workflow.graph import WORKFLOW
from backend.app.workflow.state import AgentState, Outcome, new_state

logger = logging.getLogger("backend.app.workflow")

#: Độ dài tối đa của phần câu hỏi và lý do trong dòng vết. Dòng vết phải **một dòng**;
#: câu hỏi dài 800 ký tự sẽ làm dòng vết thành một khối không đọc được.
MAX_LOG_CHARS = 80


@dataclass(slots=True)
class RunResult:
    """Kết quả một lượt hỏi, kèm trạng thái đầy đủ để gỡ lỗi."""

    question: str
    state: AgentState
    #: Tổng thời gian của cả lượt (không chỉ phần truy xuất).
    ms: int = 0
    #: Trạng thái có đi qua đồ thị hay không. ``False`` = lỗi trước khi chạy.
    ran: bool = True

    # ── đọc nhanh, không phải chọc vào ``state`` ────────────────────────

    @property
    def branch(self) -> str:
        return str(self.state.get("branch") or "")

    @property
    def signal(self) -> str:
        return str(self.state.get("branch_signal") or "")

    @property
    def outcome(self) -> str:
        return str(self.state.get("outcome") or "")

    @property
    def reason(self) -> str:
        return str(self.state.get("branch_reason") or "")

    @property
    def evidence(self) -> list[dict[str, Any]]:
        return list(self.state.get("evidence") or [])

    @property
    def citations(self) -> list[dict[str, str]]:
        """Nguồn của câu trả lời.

        Lấy từ trạng thái khi bước sinh đã dựng; nếu **chưa sinh** (đường streaming chạy đồ thị
        với ``generate=False``) thì dựng từ **bằng chứng** — nguồn là thứ thuộc về bằng chứng,
        không phải thứ chỉ tồn tại sau khi sinh.
        """
        co_san = list(self.state.get("citations") or [])
        if co_san:
            return co_san
        evidence = list(self.state.get("evidence") or [])
        if not evidence:
            return []
        from backend.app.workflow import answer as sinh

        frame = dict(self.state.get("question_frame") or {})
        return [
            dict(muc)
            for muc in sinh.build_citations(
                evidence,
                requests=list(frame.get("requests") or []),
                coverage=list(self.state.get("coverage") or []),
            )
        ]

    @property
    def answer(self) -> str:
        """Câu trả lời đã sinh (rỗng nếu chưa)."""
        return str(self.state.get("answer") or "")

    @property
    def clarify(self) -> dict[str, Any]:
        return dict(self.state.get("clarify") or {})

    @property
    def timings(self) -> dict[str, int]:
        return dict(self.state.get("timings") or {})

    @property
    def answerable(self) -> bool:
        """Có bằng chứng để bước sinh câu trả lời dùng được hay không."""
        return self.outcome == Outcome.ANSWERED.value and bool(self.evidence)

    def to_dict(self) -> dict[str, Any]:
        """Dạng gửi ra ngoài (API, CLI, trang kiểm thử).

        Chỉ gồm thứ người đọc cần; **không** đổ toàn bộ trạng thái ra — trạng thái có những
        trường chỉ dùng nội bộ và sẽ đổi khi làm mốc 2.
        """
        return {
            "question": self.question,
            "branch": self.branch,
            "branch_signal": self.signal,
            "outcome": self.outcome,
            "branch_reason": self.reason,
            "router_source": str(self.state.get("router_source") or ""),
            #: Nếu phải rơi về luật thì vì sao. ``""`` = mô hình tự quyết định.
            "router_fallback_reason": str(self.state.get("router_fallback_reason") or ""),
            "question_frame": dict(self.state.get("question_frame") or {}),
            #: Grounding từng mention + plan tất định: cần để giải thích **vì sao** một task
            #: tồn tại, và để chẩn đoán khi coverage thiếu ở giai đoạn 5.
            "groundings": list(self.state.get("groundings") or []),
            "plan": dict(self.state.get("plan") or {}),
            "coverage": list(self.state.get("coverage") or []),
            "discovery": list(self.state.get("discovery") or []),
            "plan_class": str(self.state.get("plan_class") or ""),
            "plan_class_reason": str(self.state.get("plan_class_reason") or ""),
            "request_plan_class": list(self.state.get("request_plan_class") or []),
            "verification": dict(self.state.get("verification") or {}),
            "tokens": dict(self.state.get("tokens") or {}),
            "embedding_used": bool(self.state.get("embedding_used")),
            "evidence": self.evidence,
            "clarify": self.clarify,
            #: Lời từ chối đọc được, chỉ có khi kết cục là "không trả lời được".
            "refusal": str(self.state.get("refusal") or ""),
            "gate": dict(self.state.get("gate") or {}),
            "codes": list(self.state.get("codes") or []),
            #: Câu hỏi tách thành các ý (router trả), và các ý **không có dữ liệu** (mã tính).
            "parts": list(self.state.get("parts") or []),
            "subjects": list(self.state.get("subjects") or []),
            "thieu": list(self.state.get("thieu") or []),
            "documents": list(self.state.get("documents") or []),
            "entity": self.state.get("entity"),
            "resolution": dict(self.state.get("resolution") or {}),
            "grounding_ms": int((self.state.get("timings") or {}).get("grounding_ms") or 0),
            "error": str(self.state.get("error") or ""),
            "timings": self.timings,
            "ms": self.ms,
            "answerable": self.answerable,
            #: Câu trả lời cho người dân, sinh từ bằng chứng (13.13). Rỗng = chưa sinh được.
            "answer": str(self.state.get("answer") or ""),
            #: Vì sao không sinh được câu trả lời — chỉ có khi ``answer`` rỗng mà vẫn có bằng chứng.
            "answer_error": str(self.state.get("answer_error") or ""),
            #: Nguồn ứng với ``[1]``, ``[2]``… **trong** câu trả lời, cùng thứ tự.
            "citations": self.citations,
            #: Có câu trả lời thật hay chưa. Giao diện dựa vào cờ này, không đoán theo độ dài.
            "has_answer": bool(str(self.state.get("answer") or "").strip()),
        }


async def ask(
    question: str,
    *,
    turn_index: int = 1,
    generate: bool = True,
    log_trace: bool = True,
    source: str = "api",
) -> RunResult:
    """Chạy một câu hỏi trọn luồng. Đây là hàm **duy nhất** bên ngoài được gọi.

    Không nuốt lỗi: đồ thị đã được thiết kế để mọi bước tự bắt lỗi và báo tín hiệu, nên lỗi
    thoát ra tới đây là lỗi **của chính đồ thị** — cần thấy, không cần giấu.
    """
    bat_dau = time.perf_counter()
    state = new_state(question, turn_index=turn_index)
    state["skip_generate"] = not generate

    try:
        ra = await WORKFLOW.ainvoke(state)
    except Exception:
        logger.exception("Luồng xử lý ném ngoại lệ: %s", _ngan(question))
        chi_tiet = traceback.format_exc()
        ket_qua = RunResult(
            question=question,
            state={**state, "outcome": Outcome.ERROR.value},
            ms=int((time.perf_counter() - bat_dau) * 1000),
            ran=False,
        )
        logger.info(_dong_vet(ket_qua))
        if log_trace:
            trace_log.append(
                ket_qua, source=source, phase="error", error_detail=chi_tiet
            )
        return ket_qua

    ket_qua = RunResult(
        question=question,
        state=ra,  # type: ignore[arg-type]
        ms=int((time.perf_counter() - bat_dau) * 1000),
    )
    logger.info(_dong_vet(ket_qua))
    if log_trace:
        trace_log.append(ket_qua, source=source)
    return ket_qua


def _ngan(chu: str, gioi_han: int = MAX_LOG_CHARS) -> str:
    chu = " ".join(str(chu).split())
    return chu if len(chu) <= gioi_han else chu[: gioi_han - 1] + "…"


def _dong_vet(ket_qua: RunResult) -> str:
    """Một dòng, dạng ``khoá=giá_trị`` — đọc bằng mắt và bằng máy đều được.

    Không có lý do chọn nhánh ở đây. Người đọc cần biết **câu này đi đâu, ra gì, mất bao
    lâu**; còn "vì sao" là chuyện của người gỡ lỗi, ghi riêng ở mức ``DEBUG`` để không làm
    nhiễu dòng vết của mỗi câu.
    """
    if ket_qua.reason:
        logger.debug("Lý do định tuyến: %s", ket_qua.reason)
    return (
        f'workflow q="{_ngan(ket_qua.question)}" '
        f"branch={ket_qua.branch or '-'} "
        f"signal={ket_qua.signal or '-'} "
        f"outcome={ket_qua.outcome or '-'} "
        f"ev={len(ket_qua.evidence)} "
        f"nhung={int(bool(ket_qua.state.get('embedding_used')))} "
        f"total_ms={ket_qua.ms} "
        f"branch_ms={ket_qua.timings.get('branch_ms', 0)}"
    )


# ── Bản đọc được cho người dùng CLI ──────────────────────────────────────

#: Nhãn loại bằng chứng — dùng **tên nguồn dữ liệu** để đồng nhất với nhánh.
NHAN_LOAI = {
    "fact": "PostgreSQL",
    "graph": "Neo4j",
    "chunk": "Hybrid",
    "section": "PostgreSQL",
}

#: Nhãn nhánh — cũng dùng tên nguồn để người đọc không phải nhớ hai bộ tên.
NHAN_NHANH = {
    "fact_lookup": "PostgreSQL",
    "graph": "Neo4j",
    "hybrid": "Hybrid",
    "": "Không có nguồn truy xuất",
}

#: Nhãn kết cục.
NHAN_KET_CUC = {
    "answered": "Tìm được bằng chứng",
    "clarify": "Cần hỏi lại",
    "need_identity": "Cần biết thủ tục nào",
    "abstained": "Không trả lời được",
    "error": "Lỗi",
}


def tom_tat(ket_qua: RunResult, *, so_bang_chung: int = 3) -> str:
    """Bản đọc được của một lượt — dùng cho CLI và cho trang kiểm thử.

    Cố ý **ngắn**: chỉ câu hỏi, nguồn đã trả lời, kết cục, thời gian, và ngữ cảnh tìm được.
    Lý do chọn nhánh và mã tín hiệu nội bộ **không** in ở đây — chúng nằm trong dòng vết
    ``workflow q=... why="..."``, là chỗ để gỡ lỗi. Bản in cho người đọc không phải bản gỡ lỗi.
    """
    so_muc = len(ket_qua.evidence)
    dong: list[str] = [
        f"Câu hỏi : {ket_qua.question}",
        f"Nguồn   : {NHAN_NHANH.get(ket_qua.branch, ket_qua.branch)}",
        f"Kết cục : {NHAN_KET_CUC.get(ket_qua.outcome, ket_qua.outcome)}",
        f"Thời gian: {ket_qua.ms} ms  ·  ngữ cảnh: {so_muc} mục",
    ]

    ma = (ket_qua.state.get("resolution") or {}).get("code") or ""
    if ket_qua.state.get("codes"):
        dong.append(f"Mã thủ tục: {', '.join(ket_qua.state['codes'])}")
    elif ma:
        ten = (ket_qua.state.get("resolution") or {}).get("name") or ""
        dong.append(f"Thủ tục  : {ma}" + (f" — {ten}" if ten else ""))

    if ket_qua.answer:
        dong.append("")
        dong.append("Trả lời:")
        dong.extend(f"  {dong_cau}" for dong_cau in ket_qua.answer.splitlines())
    elif ket_qua.state.get("answer_error"):
        dong.append("")
        dong.append(f"(chưa sinh được câu trả lời: {ket_qua.state['answer_error']})")

    if ket_qua.state.get("refusal"):
        dong.append("")
        dong.append(f"🚫 {ket_qua.state['refusal']}")

    if ket_qua.clarify.get("question"):
        dong.append("")
        dong.append(f"❓ {ket_qua.clarify['question']}")
        for lua_chon in ket_qua.clarify.get("options") or []:
            dong.append(f"   · {lua_chon.get('label')} ({lua_chon.get('value')})")

    if ket_qua.state.get("error"):
        dong.append(f"⚠️  {ket_qua.state['error']}")

    if not ket_qua.evidence:
        dong.append("")
        dong.append("(không có bằng chứng nào)")
        return "\n".join(dong)

    dong.append("")
    hien = min(so_bang_chung, len(ket_qua.evidence))
    dong.append(f"Bằng chứng ({len(ket_qua.evidence)} mục, hiện {hien}):")
    for chi_so, muc in enumerate(ket_qua.evidence[:so_bang_chung], start=1):
        loai = NHAN_LOAI.get(str(muc.get("kind")), str(muc.get("kind")))
        phan = (
            f" [phần {muc['part_index']}: {muc.get('part_title')}]" if muc.get("part_index") else ""
        )
        tieu_de = muc.get("title") or ""
        dong.append(f"  {chi_so}. ({loai}){phan} {tieu_de}")
        noi_dung = " ".join(str(muc.get("content") or "").split())
        if noi_dung:
            dong.append(f"     {noi_dung[:220]}{'…' if len(noi_dung) > 220 else ''}")
    if len(ket_qua.evidence) > so_bang_chung:
        dong.append(f"  … còn {len(ket_qua.evidence) - so_bang_chung} mục nữa")

    dong.append("")
    if not ket_qua.answer:
        dong.append("— Phần trên là BẰNG CHỨNG tìm được.")
    return "\n".join(dong)


__all__ = ["RunResult", "ask", "tom_tat", "NHAN_NHANH", "NHAN_KET_CUC", "NHAN_LOAI"]
