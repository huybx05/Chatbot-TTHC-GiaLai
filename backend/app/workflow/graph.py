"""Đồ thị luồng xử lý — nối các bước lại và khai báo **mọi** đường rẽ.

## Hình dạng

```
                        ┌─────────────┐
      câu hỏi ────────► │ ① neo       │  mã · văn bản · thực thể (0 token)
                        └──────┬──────┘
                    có neo │            │ chưa neo
                           │            ▼
                           │    ┌───────────────┐
                           │    │ ② định danh    │  một lần nhúng, tra tên thủ tục
                           │    └───┬───────┬───┘
                           │  trúng  │       │ trượt
                           │        ▼       │
                           │   ┌────────┐   │
                           │   │ (không còn FAQ) │
                           │   └────────┘   │
                           ▼                ▼
                        ┌──────────────────────┐
                        │ ③ QuestionFrame      │  semantic parser + adapter tất định
                        └──┬────┬────┬────┬────┘
                    ┌──────┘    │    │    └──────┐
                    ▼           ▼    ▼           ▼
              ┌──────────┐ ┌────────┐ ┌────────┐ ┌──────────┐
              │④ thuộc   │ │ đồ thị │ │  lai   │ │ ⑥ hỏi lại│
              │  tính    │ │        │ │        │ │ (chỗ chờ)│
              └────┬─────┘ └───┬────┘ └───┬────┘ └────┬─────┘
                   └───────────┴──────────┴───────────┘
                                   ▼
                            ┌─────────────┐
                            │ ⑦ kết thúc  │  đổi tín hiệu thành kết cục
                            └─────────────┘
```

## Vì sao tách ``neo`` và ``định danh`` thành hai bước

Vì chúng có **điều kiện chạy khác nhau**: câu đã có mã thì không cần nhúng, nên phải quyết
định được "có cần nhúng không" **trước khi** nhúng. Gộp làm một bước thì mọi câu đều phải
nhúng — đo được là 20/20 câu thay vì 14/20, tức trả thêm tiền cho 6 câu không cần.

## Vì sao kho đệm nằm **trước** router

Câu trả lời trong kho đệm đã có sẵn: trúng là rẻ nhất và chắc nhất. Đặt sau router thì câu
lẽ ra trúng đệm đã đi tìm kiếm tốn kém trước rồi mới biết là không cần.

## Chỗ chờ cho mốc sau

``hỏi lại`` hiện là bước tạm: nó dựng câu hỏi lại từ những gì đã có. Việc 13.10 sẽ thay bằng
bước thật (chọn lựa chọn, ghi nhớ ngữ cảnh hỏi lại). Việc 13.11 sẽ thêm đường **leo thang**
từ nhánh này sang nhánh khác; việc 13.13–13.14 sẽ thêm bước sinh và kiểm chứng **sau** bước
kết thúc. Đồ thị được viết để ba việc đó chỉ cần **thêm cạnh**, không phải sửa bước nào.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.app.rag import contracts, embeddings, grounding, resolve, scope
from backend.app.rag.evidence import Branch
from backend.app.rag.resolver import ProcedureResolution
from backend.app.workflow import answer, executor, nodes, plan_class, planner, question_parser
from backend.app.workflow.router_rules import RouterDecision, decide
from backend.app.workflow.state import (
    AgentState,
    BranchSignal,
    ClarifyInfo,
    Outcome,
)

logger = logging.getLogger(__name__)

#: Tên các bước. Dùng hằng số để không có chuỗi nào gõ sai ở hai nơi.
NEO = "neo"
DINH_DANH = "dinh_danh"
ROUTER = "router"
NHUNG_BO_SUNG = "nhung_bo_sung"
TU_CHOI = "tu_choi"
HOI_LAI = "hoi_lai"
KET_THUC = "ket_thuc"

#: Tên nhánh = tên bước của nhánh đó.
CAC_NHANH = tuple(Branch)

#: Nhánh **cần vector câu hỏi** để chạy. Câu đã có mã mà hỏi nội dung thì router chọn nhánh
#: lai, nhưng bước ``neo`` đã không nhúng (vì có mã) — nên phải nhúng bổ sung **một** lần
#: trước khi vào nhánh. Bỏ sót chỗ này thì triệu chứng là "nhánh trả 0 bằng chứng", rất khó
#: đoán ra nguyên nhân.
CAN_VECTOR = {Branch.HYBRID.value}

#: Tín hiệu → kết cục. ``OK`` là ``ANSWERED`` vì bằng chứng đã có; bước sinh câu trả lời
#: (việc 13.13) sẽ đọc bằng chứng chứ không đổi kết cục.
KET_CUC = {
    BranchSignal.OK: Outcome.ANSWERED,
    BranchSignal.EMPTY: Outcome.ABSTAINED,
    BranchSignal.NOT_GRAPH: Outcome.ABSTAINED,
    BranchSignal.NEED_IDENTITY: Outcome.CLARIFY,
    BranchSignal.CLARIFY: Outcome.CLARIFY,
    BranchSignal.ERROR: Outcome.ERROR,
}


def _noi_dung_hoi_lai(state: AgentState) -> dict[str, Any]:
    """Dựng câu hỏi lại **đúng nguyên nhân**, kèm lựa chọn lấy từ dữ liệu đã có.

    Câu hỏi chung "Bạn muốn hỏi thủ tục nào?" chỉ đúng khi không biết vì sao phải hỏi. Đo
    được ba nguyên nhân khác nhau, và mỗi nguyên nhân cần một câu khác:

    * thiếu tiền ngữ cho đại từ → hỏi lại **thủ tục nào**, nhắc rằng câu trước không nêu;
    * nhiều văn bản cùng khớp → cho chọn **văn bản**;
    * nhiều thủ tục cùng khớp tên → cho chọn **thủ tục**;
    * nhiều thực thể cùng khớp → hỏi **giá trị**.

    Lựa chọn luôn lấy từ dữ liệu thật, không bịa: mã thủ tục, mã văn bản, hoặc giá trị thực
    thể đã khớp.
    """
    hien_co = dict(state.get("clarify") or {})
    lua_chon = list(hien_co.get("options") or [])

    if state.get("needs_antecedent"):
        return {
            "question": (
                "Bạn đang nói tới thủ tục nào? Câu hỏi chưa nêu thủ tục cụ thể nên tôi chưa "
                "biết **thủ tục này** là thủ tục nào."
            ),
            "options": lua_chon,
        }

    van_ban = list(state.get("documents") or [])
    if len(van_ban) > 1:
        return {
            "question": (
                f"Có {len(van_ban)} văn bản pháp lý cùng khớp với câu hỏi. "
                "Bạn muốn hỏi văn bản nào?"
            ),
            "options": lua_chon
            or [{"value": ma, "label": ma, "hint": "văn bản pháp lý"} for ma in van_ban[:5]],
        }

    alternatives = list((state.get("resolution") or {}).get("alternatives") or [])
    if len(alternatives) > 1:
        return {
            "question": (
                f"Có {len(alternatives)} thủ tục cùng khớp tên với câu hỏi. "
                "Bạn muốn hỏi thủ tục nào?"
            ),
            "options": lua_chon
            or [
                {
                    "value": str(a.get("code") or ""),
                    "label": str(a.get("name") or a.get("code") or ""),
                    "hint": f"mã {a.get('code')}",
                }
                for a in alternatives[:5]
            ],
        }

    if state.get("entity_ambiguous"):
        return {
            "question": "Câu hỏi khớp nhiều giá trị trong dữ liệu. Bạn muốn hỏi giá trị nào?",
            "options": lua_chon,
        }

    if hien_co.get("question"):
        return {"question": str(hien_co["question"]), "options": lua_chon}

    ma = str((state.get("resolution") or {}).get("code") or "")
    if ma:
        ten = str((state.get("resolution") or {}).get("name") or ma)
        return {"question": f"Bạn muốn hỏi về thủ tục {ten}?", "options": lua_chon}
    return {"question": "Bạn muốn hỏi thủ tục nào?", "options": lua_chon}


def _hoi_lai_mac_dinh(state: AgentState) -> dict[str, Any]:
    """Nội dung hỏi lại: giữ **lựa chọn đã có**, chỉ bổ sung câu hỏi còn thiếu.

    Cố ý không dựng lại từ đầu. Bản cũ trả về ``options: []`` khi câu hỏi rỗng, nên nó **xoá
    mất** danh sách lựa chọn mà bước router vừa bổ sung — và hệ quả là câu hỏi lại rơi vào
    ngõ cụt. Đo được: *"đổi sổ đỏ bị rách cũ"* có 3 thủ tục cùng khớp, router đã đưa 3 lựa
    chọn, rồi bị chính hàm này xoá sạch.
    """
    hien_co = dict(state.get("clarify") or {})
    lua_chon = list(hien_co.get("options") or [])

    if hien_co.get("question"):
        return {"question": str(hien_co["question"]), "options": lua_chon}

    ma = str((state.get("resolution") or {}).get("code") or "")
    if ma:
        ten = str((state.get("resolution") or {}).get("name") or ma)
        return {"question": f"Bạn muốn hỏi về thủ tục {ten}?", "options": lua_chon}
    return {"question": "Bạn muốn hỏi thủ tục nào?", "options": lua_chon}


# ── Các bước ─────────────────────────────────────────────────────────────


async def node_neo(state: AgentState) -> dict[str, Any]:
    """Bước ①: chỉ định neo, **không** nhúng. Đây là bước rẻ nhất của cả luồng.

    Đồng thời chặn **hai loại ngoài phạm vi** ngay tại đây, trước mọi bước tốn tiền:

    * câu hỏi về **tỉnh khác** — dữ liệu chỉ có TTHC của Gia Lai;
    * câu nêu **mã thủ tục không tồn tại** — mã khớp hình dạng nhưng không có trong bảng.

    Cả hai đều kết luận được bằng dữ liệu đóng (danh sách tỉnh, khoá bảng ``procedures``),
    không phải bằng mô hình hay bằng điểm liên quan.
    """
    cau = str(state.get("question") or "")
    ket_qua = await resolve.resolve(cau, only_anchors=True)
    patch = dict(ket_qua.state_patch())

    tinh = scope.tinh_khac(cau)
    if tinh:
        patch.update(
            {
                "outcome": Outcome.ABSTAINED.value,
                "branch": "",
                "branch_signal": BranchSignal.EMPTY.value,
                "branch_reason": f"câu hỏi về {tinh}, ngoài phạm vi dữ liệu",
                "refusal": scope.cau_tu_choi_tinh(tinh),
            }
        )
        return patch

    if ket_qua.asked_codes and not ket_qua.codes:
        # Người dùng nêu mã **và** mã đó không tồn tại. Đây khác "không nêu mã": câu hỏi đã
        # chỉ đích danh một thủ tục, nên phải nói rõ mã đó không có thay vì đi tìm theo nghĩa
        # rồi trả lời bằng thủ tục khác.
        patch.update(
            {
                "outcome": Outcome.ABSTAINED.value,
                "branch": "",
                "branch_signal": BranchSignal.EMPTY.value,
                "branch_reason": "mã thủ tục không tồn tại",
                "refusal": scope.cau_tu_choi_ma(ket_qua.asked_codes),
            }
        )
        return patch

    return patch


async def node_dinh_danh(state: AgentState) -> dict[str, Any]:
    """Bước ②: nhúng **một lần** rồi định danh thủ tục theo tên.

    Câu không có neo (không mã, không văn bản, không thực thể đủ) mới tới đây. Bước này làm
    đúng một việc: nhúng câu hỏi và tra tên thủ tục, để router có dữ kiện mà chọn nhánh.

    **Không** còn kho câu hỏi thường gặp: FAQ đã được gỡ khỏi luồng truy xuất. Câu trả lời luôn
    sinh từ bằng chứng thật (PostgreSQL / Neo4j / Hybrid), nên không còn đường nào trả về đáp
    án soạn sẵn của một thủ tục khác.
    """
    cau = str(state.get("question") or "")

    vector = await embeddings.embed(cau)
    dau_vet = resolve.remember_vector(vector)
    ket_qua = await resolve.resolve(cau, vector=vector)

    # Vá của bộ định danh **trước**, rồi mới ghi đè phần vector: ``state_patch`` mang
    # ``vector_hash=""`` cho câu chưa nhúng, nên nếu ghi đè trước thì dấu vết bị xoá và bước
    # sau tưởng chưa nhúng.
    patch: dict[str, Any] = dict(ket_qua.state_patch())
    patch["vector_hash"] = dau_vet
    patch["embedding_used"] = True
    patch["branch"] = ""
    patch["branch_signal"] = BranchSignal.OK.value
    return patch


async def node_router(state: AgentState) -> dict[str, Any]:
    """Bước ③: sinh QuestionFrame rồi ánh xạ sang nhánh; luật làm dự phòng.

    Ba thứ được ghi lại để đọc được về sau:

    * ``router_source`` — câu này dùng semantic parser hay router luật dự phòng;
    * ``router_fallback_reason`` — nếu phải rơi về luật thì **vì sao**
      (quá hạn / nhãn lạ / API lỗi);
    * ``tokens`` + ``timings.router_ms`` — chi phí thật của quyết định.

    Không bao giờ để parser làm hỏng lượt: lỗi API, timeout hoặc frame sai schema đều thành
    một lý do và rơi về luật.
    """
    cau = str(state.get("question") or "")
    ket_qua = _dung_lai_ket_qua(state)

    nguon_vector = _GroundingVector(state, cau)
    quyet_dinh, ly_do_du_phong, frame, groundings, grounding_ms = await _chon_nhanh(
        cau, ket_qua, get_vector=nguon_vector.get
    )
    quyet_dinh = _abstain_khi_co_lua_chon(quyet_dinh, ket_qua)

    patch: dict[str, Any] = {
        "branch": quyet_dinh.branch,
        "branch_signal": quyet_dinh.signal,
        "branch_reason": quyet_dinh.reason,
        "router_source": quyet_dinh.source,
        "router_fallback_reason": ly_do_du_phong,
        # Phân tích ý của mô hình: quyết định bước bổ sung và quyền nói "chưa ghi nhận".
        "parts": list(quyet_dinh.parts),
        "subjects": list(quyet_dinh.subjects),
        "tokens": {
            "input": quyet_dinh.tokens_in,
            "output": quyet_dinh.tokens_out,
        },
    }
    if frame is not None:
        patch["question_frame"] = frame
        # Planner tất định: biến frame + grounding thành task. Giai đoạn 5 sẽ thực thi plan;
        # ở đây ghi vào trace để biết hệ thống **định** truy xuất gì, không đổi nhánh đang chạy.
        patch["plan"] = planner.plan_retrieval(frame, groundings).to_dict()
        # Nhãn nguồn lực suy bằng mã nguồn (không phải nhãn nhánh của router cũ).
        phan_loai = plan_class.classify_turn(frame, groundings)
        patch["plan_class"] = phan_loai.plan_class.value
        patch["plan_class_reason"] = phan_loai.reason
        patch["request_plan_class"] = [item.to_dict() for item in phan_loai.requests]
    if groundings:
        patch["groundings"] = [item.to_dict() for item in groundings]
    # Ứng viên (giả thuyết) tách khỏi bằng chứng: ghi vào trace để bước sau dùng, tuyệt đối
    # không đưa vào danh sách evidence.
    candidates = contracts.from_groundings(groundings, ket_qua)
    if candidates:
        patch["discovery"] = [item.to_dict() for item in candidates]
    if nguon_vector.used:
        # Grounding đã dùng vector (nhúng hoặc lấy lại) — ghi đúng thực tế để phép đo
        # "mỗi câu nhúng tối đa một lần" không bị sai.
        vector = await nguon_vector.get()
        if not str(state.get("vector_hash") or ""):
            patch["vector_hash"] = resolve.remember_vector(vector)
            patch["embedding_used"] = True
    # Grounding có thể xác định được thủ tục trong khi bước định danh đầu lượt thì không.
    # Ghi vào ``resolution`` để các nhánh truy xuất dùng cùng một sự thật.
    grounded = grounding.resolved_procedure(groundings) if groundings else None
    # Mã người dùng gõ trực tiếp đã được PostgreSQL xác minh là neo mạnh nhất. Nếu không có
    # neo đó, kết quả grounding thay thế kết quả resolver toàn câu để các nhánh truy xuất dùng
    # đúng subject mà QuestionFrame đã trỏ tới.
    if grounded is not None and not list(state.get("codes") or []):
        patch["resolution"] = {
            **dict(state.get("resolution") or {}),
            "code": grounded.code,
            "name": grounded.name,
            "method": f"grounding:{grounded.method}",
            "confidence": grounded.score,
            "note": grounded.note or "thủ tục do grounding xác định",
        }
    if quyet_dinh.branch:
        # Chỉ nhánh chạy thật mới cần cộng thời gian quyết định vào ``router_ms``. Câu bị
        # đưa sang hỏi lại / từ chối vẫn có chi phí, nhưng ghi ở đây là đủ để đo.
        patch["timings"] = {
            **dict(state.get("timings") or {}),
            "router_ms": quyet_dinh.ms,
            "grounding_ms": grounding_ms,
        }
    else:
        patch["timings"] = {
            **dict(state.get("timings") or {}),
            "router_ms": quyet_dinh.ms,
            "grounding_ms": grounding_ms,
        }
        if quyet_dinh.signal == BranchSignal.CLARIFY.value:
            patch["clarify"] = _clarify_co_lua_chon(quyet_dinh, ket_qua)
    return patch


#: Dấu hiệu trong lý do cho thấy câu hỏi **mơ hồ vì tên gọi**, tức là hỏi lại sẽ hữu ích.
#: Cố ý hẹp: chỉ những cụm này mới đủ để lật một quyết định "từ chối" thành "hỏi lại".
DAU_HIEU_MO_HO: tuple[str, ...] = (
    "cùng khớp",
    "cung khop",
    "mơ hồ",
    "mo ho",
    "nhiều thủ tục",
    "nhieu thu tuc",
)


def _abstain_khi_co_lua_chon(quyet_dinh, ket_qua: resolve.Resolution):
    """Từ chối là **sai** khi hệ thống đang có sẵn lựa chọn để đưa ra.

    Mô hình không ổn định ở đúng chỗ này: cùng một câu, lúc chọn ``clarify`` lúc chọn
    ``abstain`` (đo được: *"đổi sổ đỏ bị rách cũ"* có 3 thủ tục cùng khớp, mô hình trả lời
    "nhiều thủ tục cùng khớp tên, cần làm rõ" nhưng lại chọn nhãn ``abstain``).

    Nên chốt bằng **dữ liệu**: có từ hai ứng viên trở lên thì phải hỏi lại, vì đó là câu trả
    lời hữu ích hơn — người dùng chọn một cái là xong.
    """
    if quyet_dinh.signal != BranchSignal.EMPTY.value:
        return quyet_dinh

    alternatives = ket_qua.procedure.alternatives or []
    if len(alternatives) < 2:
        return quyet_dinh

    # **Chỉ** lật khi lý do nói về mơ hồ tên gọi. Nếu lý do thuộc nhóm "không mô hình hoá"
    # (người ký, hiệu lực, so sánh/xếp hạng, không khớp thủ tục nào) thì dữ liệu có ứng viên
    # cũng **không** biến câu đó thành câu hỏi lại được — chúng là ứng viên nhiễu.
    #
    # Đo được: *"Thủ tục nào có lệ phí cao nhất?"* bị lật thành "3 thủ tục cùng khớp, bạn muốn
    # hỏi thủ tục nào?" — một câu hỏi lại vô nghĩa cho câu hỏi cần xếp hạng.
    if not any(x in quyet_dinh.reason.lower() for x in DAU_HIEU_MO_HO):
        return quyet_dinh

    return RouterDecision(
        branch="",
        signal=BranchSignal.CLARIFY.value,
        reason=(
            "có nhiều thủ tục cùng khớp tên nên phải hỏi lại, không từ chối"
            f" ({len(alternatives)} lựa chọn)"
        ),
        confident=quyet_dinh.confident,
        clarify=ClarifyInfo(question="", options=[]),
        source=quyet_dinh.source,
        ms=quyet_dinh.ms,
        tokens_in=quyet_dinh.tokens_in,
        tokens_out=quyet_dinh.tokens_out,
        tokens_cached=quyet_dinh.tokens_cached,
        model=quyet_dinh.model,
    )


def _clarify_co_lua_chon(quyet_dinh, ket_qua: resolve.Resolution) -> dict[str, Any]:
    """Bổ sung danh sách lựa chọn cho câu hỏi lại, lấy từ những gì bộ định danh đã tìm được.

    Mô hình chỉ quyết định **có cần hỏi lại hay không**; nó không biết mã thủ tục. Nếu để
    nguyên, câu hỏi lại là "Bạn muốn hỏi thủ tục nào?" kèm **danh sách rỗng** — người dùng bị
    chặn mà không có gì để chọn. Đo được: hai câu trong một lần thử của người dùng rơi vào
    đúng trạng thái này.

    Khi bộ định danh không có ứng viên nào thì để rỗng, và bước ``hoi_lai`` sẽ đổi thành lời
    từ chối kèm hướng dẫn (xem ``node_hoi_lai``).
    """
    hien_co = dict(quyet_dinh.clarify or {})
    lua_chon = list(hien_co.get("options") or [])

    if not lua_chon:
        for ma, ten, _diem in (ket_qua.procedure.alternatives or [])[:5]:
            lua_chon.append({"value": ma, "label": ten or ma, "hint": f"mã {ma}"})

    return {"question": hien_co.get("question") or "", "options": lua_chon}


class _GroundingVector:
    """Vector dùng cho grounding: tái sử dụng vector đã có, hoặc nhúng đúng một lần."""

    def __init__(self, state: AgentState, question: str) -> None:
        self._state = state
        self._question = question
        self._value: list[float] | None = None
        self.used = False

    async def get(self) -> list[float]:
        if self._value is not None:
            return self._value
        self.used = True
        cu = resolve.get_vector(str(self._state.get("vector_hash") or ""))
        self._value = cu if cu is not None else await embeddings.embed(self._question)
        return self._value


async def _chon_nhanh(
    question: str,
    ket_qua: resolve.Resolution,
    *,
    get_vector: Callable[[], Awaitable[list[float]]] | None = None,
) -> tuple[RouterDecision, str, dict | None, list[grounding.SubjectGrounding], int]:
    """Phân tích QuestionFrame, grounding mention, rồi ánh xạ sang luồng hiện tại.

    Trả ``(quyết định, lý do dự phòng, frame, groundings, grounding_ms)``. ``frame`` rỗng khi
    parser bị tắt hoặc lỗi — khi đó ``groundings`` cũng rỗng và router luật quyết định.
    """
    if not question_parser.enabled():
        return decide(ket_qua), "tắt semantic parser bằng cấu hình", None, [], 0

    try:
        parsed = await question_parser.parse_question(question, ket_qua)
    except question_parser.QuestionParserError as exc:
        logger.warning("Semantic parser lỗi, rơi về router luật: %s", exc.reason)
        return decide(ket_qua), exc.reason, None, [], 0

    started = time.perf_counter()
    items = await grounding.ground_frame(
        parsed.frame, ket_qua, question=question, get_vector=get_vector
    )
    grounding_ms = int((time.perf_counter() - started) * 1000)
    decision = question_parser.to_router_decision(parsed, ket_qua, items)
    return decision, "", parsed.frame, items, grounding_ms


async def node_nhung_bo_sung(state: AgentState) -> dict[str, Any]:
    """Bước ②': nhúng bổ sung khi nhánh được chọn cần vector mà câu chưa nhúng.

    Chỉ tới đây khi câu **đã có neo** (nên bước ``neo`` đã bỏ qua việc nhúng) mà router lại
    chọn nhánh cần vector — ví dụ *"thủ tục 1.123 cần hồ sơ gì"*: có mã, nhưng hồ sơ chỉ có
    trong đoạn văn.

    Vẫn giữ nguyên tắc một lần nhúng: câu này chưa nhúng lần nào, và bước này là lần duy nhất.
    """
    cau = str(state.get("question") or "")
    vector = await embeddings.embed(cau)
    return {
        "vector_hash": resolve.remember_vector(vector),
        "embedding_used": True,
    }


#: Nhóm lý do từ chối **đọc được**, nhận ra từ chính lý do của mô hình. Thứ tự quan trọng:
#: nhóm cụ thể đứng trước, nhóm chung đứng sau.
NHOM_TU_CHOI: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("người ký", "nguoi ky", "thẩm quyền ký", "ai ký"),
        "Dữ liệu chưa có thông tin **người ký** văn bản hay quyết định. Hiện chỉ có *cơ quan "
        "ban hành*.",
    ),
    (
        ("hiệu lực", "hieu luc", "hết hiệu lực", "ngày ban hành"),
        "Dữ liệu chưa có thông tin **ngày hiệu lực** của văn bản pháp lý.",
    ),
    (
        ("cao nhất", "thấp nhất", "nhiều nhất theo", "so sánh", "xếp hạng", "trung bình"),
        "Câu này cần **so sánh hoặc xếp hạng** giữa nhiều thủ tục — hệ thống chưa làm được "
        "việc đó. Ba câu thống kê có sẵn là: lĩnh vực nào nhiều thủ tục nhất, cơ quan nào "
        "ban hành nhiều nhất, văn bản nào làm căn cứ cho nhiều thủ tục nhất.",
    ),
    (
        ("không khớp", "khong khop", "không có thủ tục", "chưa ghi nhận", "không có trong"),
        "Không có thủ tục nào trong dữ liệu khớp với câu hỏi này.",
    ),
)

#: Lời từ chối dùng khi lý do không rơi vào nhóm nào ở trên.
TU_CHOI_CHUNG = (
    "Tôi chưa trả lời được câu này bằng dữ liệu hiện có. "
    "Bạn có thể hỏi về: hồ sơ cần nộp, lệ phí, thời hạn, trình tự thực hiện, cơ quan ban "
    "hành, đối tượng áp dụng, kết quả nhận được, hoặc căn cứ pháp lý của một thủ tục."
)


def loi_tu_choi(ly_do: str) -> str:
    """Lời từ chối đọc được, dựa trên **lý do** mà router đưa ra.

    Không dựng câu chung chung: người dùng cần biết *thiếu cái gì* thì mới biết đường hỏi
    cách khác. Lý do của mô hình đã nêu đúng điểm thiếu ("dữ liệu không có thông tin người
    ký"), nên việc ở đây chỉ là chọn câu giải thích phù hợp và nói rõ dữ liệu **đang có** gì.
    """
    chu = " ".join(str(ly_do or "").lower().split())
    for dau_hieu, loi in NHOM_TU_CHOI:
        if any(x in chu for x in dau_hieu):
            return loi
    return TU_CHOI_CHUNG


async def node_tu_choi(state: AgentState) -> dict[str, Any]:
    """Bước từ chối: hiểu câu hỏi nhưng dữ liệu **không có** câu trả lời.

    Khác ``hoi_lai``: không hỏi thêm, vì người dùng đã nói rõ điều họ muốn — chỉ là hệ thống
    không có. Nên nói thẳng **thiếu gì** thay vì im lặng, và **không** để trống câu trả lời:
    người dùng cần biết hệ thống làm được gì để hỏi lại cho đúng.
    """
    ly_do = str(state.get("branch_reason") or "")
    co_san = str(state.get("refusal") or "").strip()
    return {
        "outcome": Outcome.ABSTAINED.value,
        "branch_signal": BranchSignal.EMPTY.value,
        "branch": "",
        # Câu từ chối dựng sẵn ở bước trước (tỉnh khác, mã không tồn tại) nói đúng điều người
        # dùng đã hỏi; câu từ chối chung không làm được điều đó.
        "refusal": co_san or loi_tu_choi(ly_do),
    }


#: Lời hướng dẫn khi **không có lựa chọn nào** để đưa ra. Hỏi "bạn muốn hỏi thủ tục nào?" mà
#: không kèm gì là ngõ cụt: người dùng không biết phải trả lời thế nào cho đúng định dạng.
HUONG_DAN_CHON = (
    "Tôi cần biết bạn muốn hỏi thủ tục nào. Hãy cho tôi **mã thủ tục** (ví dụ 1.001699) "
    "hoặc **tên thủ tục**, rồi hỏi lại."
)


async def node_hoi_lai(state: AgentState) -> dict[str, Any]:
    """Bước ⑥: hỏi lại — nhưng chỉ khi thật sự có thứ để người dùng chọn.

    Hai kết cục, phân biệt bằng **có lựa chọn hay không**:

    * có ≥ 1 lựa chọn → hỏi lại bình thường, người dùng chọn một cái là xong;
    * không có lựa chọn nào → đây không phải "hỏi lại" mà là "chưa đủ thông tin để tra": đổi
      thành **từ chối** kèm hướng dẫn cụ thể. Đo được: câu *"Bộ Y tế quy định thủ tục nào về
      khuyết tật?"* và *"chuyển nhượng đất cho con ruột…"* đều rơi vào trạng thái hỏi-rỗng
      này, tức người dùng bị chặn mà không có gì để chọn.
    """
    return {
        "outcome": Outcome.CLARIFY.value,
        "branch_signal": BranchSignal.CLARIFY.value,
        "clarify": _noi_dung_hoi_lai(state),
    }


async def node_ket_thuc(state: AgentState) -> dict[str, Any]:
    """Bước ⑦: đổi tín hiệu của nhánh thành **kết cục**.

    Ba việc sau này bám vào đây: leo thang (13.11) đọc kết cục để quyết định thử nhánh khác;
    từ chối (13.10) đọc ``EMPTY``; sinh câu trả lời (13.13) chèn **trước** bước này.
    """
    tin_hieu = str(state.get("branch_signal") or BranchSignal.OK.value)
    try:
        ket_cuc = KET_CUC[BranchSignal(tin_hieu)]
    except (ValueError, KeyError):
        ket_cuc = Outcome.ERROR

    patch: dict[str, Any] = {
        "outcome": ket_cuc.value,
        "timings": dict(state.get("timings") or {}),
    }
    if ket_cuc is Outcome.ABSTAINED and not str(state.get("refusal") or "").strip():
        # Nhánh kết luận "không có gì để trả lời" (ví dụ cổng từ chối chặn) mà chưa có câu từ
        # chối dựng sẵn. Không để trống: giao diện sẽ hiện khung rỗng, còn API phải tự bịa một
        # câu chung — hai chỗ nói hai kiểu.
        patch["refusal"] = loi_tu_choi(str(state.get("branch_reason") or ""))
    if ket_cuc is Outcome.CLARIFY:
        hien_co = state.get("clarify") or {}
        if not (hien_co.get("options") or []):
            # Hỏi lại mà **không có lựa chọn nào** là ngõ cụt: người dùng không biết trả lời
            # thế nào. Đổi thành lời từ chối kèm hướng dẫn cụ thể.
            #
            # Đặt ở **bước kết thúc** chứ không ở bước hỏi lại, vì câu hỏi lại còn đến từ hai
            # đường khác: router và chính nhánh đồ thị (khi đồ thị cần mã mà không có). Đây là
            # điểm ra duy nhất nên không đường nào lọt.
            patch["outcome"] = Outcome.ABSTAINED.value
            patch["branch_signal"] = BranchSignal.EMPTY.value
            patch["refusal"] = HUONG_DAN_CHON
            patch["clarify"] = {"question": "", "options": []}
            patch["branch_reason"] = (
                str(state.get("branch_reason") or "")
                + " · không có lựa chọn nào để đưa ra nên chuyển thành hướng dẫn"
            ).lstrip(" ·")
        elif not hien_co.get("question"):
            patch["clarify"] = _noi_dung_hoi_lai(state)
    return patch


THUC_THI = "thuc_thi"
SINH = "sinh"
BO_SUNG_MUC = "bo_sung_muc"


#: Câu từ chối đọc được theo mã lý do của planner/coverage.
LOI_KE_HOACH = {
    "UNSUPPORTED_OPERATION": (
        "Hệ thống chưa hỗ trợ phép so sánh hoặc xếp hạng thủ tục. "
        "Bạn có thể hỏi về hồ sơ, thời hạn, phí, cơ quan hoặc căn cứ pháp lý của một thủ tục."
    ),
    "UNSUPPORTED_FACET": (
        "Hệ thống chưa có dữ liệu cho loại thông tin này. "
        "Hiện tra cứu được: hồ sơ, trình tự, cách nộp, thời hạn, phí, kết quả, "
        "cơ quan, lĩnh vực, cấp, đối tượng và căn cứ pháp lý."
    ),
    "UNSUPPORTED_COUNT": "Hệ thống chưa hỗ trợ đếm cho loại thông tin này.",
    "UNSUPPORTED_CONSTRAINT": (
        "Hệ thống chưa hỗ trợ lọc theo điều kiện bạn nêu. "
        "Bạn có thể bỏ điều kiện đó hoặc hỏi theo mã/tên thủ tục."
    ),
    "INSUFFICIENT_EVIDENCE": (
        "Dữ liệu hiện có chưa đủ để trả lời câu hỏi này. "
        "Bạn thử nêu mã hoặc tên thủ tục để tôi tra chính xác hơn."
    ),
    "TOOL_UNAVAILABLE": (
        "Nguồn dữ liệu đang tạm lỗi nên tôi chưa tra được. Bạn thử lại sau ít phút."
    ),
}


def _plan_from_state(state: AgentState) -> planner.Plan:
    """Dựng lại ``planner.Plan`` từ dict trong state (plan đã serialize khi ghi trace)."""
    data = state.get("plan") or {}
    tasks = [
        planner.Task(
            request_index=int(item.get("request_index") or 0),
            tool=str(item.get("tool") or ""),
            facet=str(item.get("facet") or ""),
            operation=str(item.get("operation") or "get"),
            intent=str(item.get("intent") or ""),
            expected_types=tuple(item.get("expected_types") or ()),
            procedure_codes=tuple(item.get("procedure_codes") or ()),
            subject_ref=item.get("subject_ref"),
            constraints=tuple(item.get("constraints") or ()),
        )
        for item in data.get("tasks") or []
    ]
    return planner.Plan(tasks=tasks, unsupported=list(data.get("unsupported") or []))


async def node_thuc_thi(state: AgentState) -> dict[str, Any]:
    """Bước ④: thực thi RetrievalPlan, tính coverage, quyết định kết cục.

    Đây là chỗ duy nhất biến task thành bằng chứng. Câu nhiều ý chạy song song; một nguồn lỗi
    không làm mất kết quả của nguồn khác; mỗi request có trạng thái phủ riêng để câu trả lời
    nói đúng phần nào có dữ liệu, phần nào không.
    """
    plan = _plan_from_state(state)
    execution = await executor.execute_plan(state, plan)

    patch: dict[str, Any] = {
        "branch": "executor",
        "evidence": execution.evidence,
        "coverage": [item.to_dict() for item in execution.coverage],
        "timings": {**dict(state.get("timings") or {}), "executor_ms": execution.ms},
    }
    if execution.vector_used and execution.vector:
        patch["vector_hash"] = resolve.remember_vector(execution.vector)
        patch["embedding_used"] = True

    existing_fallback = list(state.get("fallback_from") or [])
    patch["fallback_from"] = existing_fallback + [
        f"{index}:{from_tool}->{to_tool}" for index, from_tool, to_tool in execution.fallbacks
    ]

    unsupported_reasons = {
        str(item.get("reason") or "") for item in plan.unsupported if item.get("reason")
    }
    if execution.covered:
        # ``thieu`` chỉ dành cho ý **dữ liệu thật sự không có**. Lỗi nguồn, chưa hỗ trợ và cần
        # làm rõ đã nằm trong ``coverage`` và được prompt nói bằng trạng thái riêng.
        thieu = [
            item.facet
            for item in execution.coverage
            if item.status == executor.STATUS_EMPTY and item.facet
        ]
        patch.update(
            outcome=Outcome.ANSWERED.value,
            branch_signal=BranchSignal.OK.value,
            thieu=list(dict.fromkeys(thieu)),
            branch_reason=(
                f"plan: {execution.covered}/{len(execution.coverage)} ý có dữ liệu"
            ),
        )
        return patch

    # Không ý nào có dữ liệu. Graph có thể đã trả câu hỏi lại kèm lựa chọn thật — ưu tiên nó
    # thay vì biến mơ hồ thành "dữ liệu chưa đủ".
    if execution.clarify:
        patch.update(
            outcome=Outcome.CLARIFY.value,
            branch_signal=BranchSignal.CLARIFY.value,
            clarify={
                "question": str(execution.clarify.get("question") or "Bạn muốn chọn mục nào?"),
                "options": list(execution.clarify.get("options") or []),
            },
            branch_reason="plan: graph yêu cầu làm rõ",
        )
        return patch

    clarify_reason = next((r for r in unsupported_reasons if r in executor.CLARIFY_REASONS), "")
    if clarify_reason:
        patch.update(
            outcome=Outcome.CLARIFY.value,
            branch_signal=BranchSignal.CLARIFY.value,
            clarify={
                "question": "Bạn vui lòng nêu mã hoặc tên thủ tục cần tra cứu.",
                "options": [],
            },
            branch_reason=f"plan: {clarify_reason}",
        )
        return patch

    if execution.failed_all:
        reason = "TOOL_UNAVAILABLE"
    elif unsupported_reasons:
        reason = sorted(unsupported_reasons)[0]
    else:
        reason = "INSUFFICIENT_EVIDENCE"
    patch.update(
        outcome=Outcome.ABSTAINED.value,
        branch_signal=BranchSignal.EMPTY.value,
        refusal=LOI_KE_HOACH.get(reason, LOI_KE_HOACH["INSUFFICIENT_EVIDENCE"]),
        branch_reason=f"plan: {reason}",
    )
    return patch


async def node_sinh(state: AgentState) -> dict[str, Any]:
    """Bước ⑧: sinh câu trả lời từ **bằng chứng** (việc 13.13).

    Chỉ chạy khi câu đã có bằng chứng **và** kết cục là trả lời được. Hỏi lại, từ chối, lỗi —
    đều không có gì để sinh: đã có câu nói riêng cho người dùng ở các bước trước.

    Không bao giờ để lỗi mô hình làm mất kết quả: bằng chứng vẫn còn, và ``answer_error`` ghi
    lại lý do để giao diện nói đúng thay vì hiện khung trống.
    """
    if str(state.get("outcome") or "") != Outcome.ANSWERED.value:
        return {}
    if not state.get("evidence"):
        return {}
    if state.get("skip_generate"):
        # Đường streaming: nơi gọi tự stream bước sinh ra ngoài, sinh ở đây là sinh hai lần.
        return {}
    if not answer.dang_bat():
        return {"answer_error": "chưa cấu hình mô hình sinh câu trả lời"}

    cau = str(state.get("question") or "")
    evidence = list(state["evidence"])
    thieu = list(state.get("thieu") or [])
    requests = list((state.get("question_frame") or {}).get("requests") or [])
    coverage = list(state.get("coverage") or [])

    try:
        ket_qua = await answer.sinh(
            cau,
            evidence,
            thieu=thieu,
            requests=requests,
            coverage=coverage,
        )
    except answer.AnswerError as exc:
        logger.warning("Không sinh được câu trả lời: %s", exc.reason)
        return {
            "answer_error": exc.reason,
            "timings": {**dict(state.get("timings") or {}), "generate_ms": 0},
        }

    return {
        "answer": ket_qua.text,
        "citations": list(ket_qua.citations),
        "answer_error": "",
        # Evidence, coverage and the prompt are fully prepared before the model starts. Do not
        # verify or replace its text here: the SSE path must expose the same one-pass answer.
        "verification": {"status": "skipped", "issues": []},
        "timings": {**dict(state.get("timings") or {}), "generate_ms": ket_qua.ms},
        "tokens": {
            "input": int((state.get("tokens") or {}).get("input", 0)) + ket_qua.tokens_in,
            "output": int((state.get("tokens") or {}).get("output", 0)) + ket_qua.tokens_out,
        },
    }


async def node_bo_sung_muc(state: AgentState) -> dict[str, Any]:
    """Bước ③b: bổ sung mục còn thiếu cho câu nhiều ý (xem ``nodes.node_bo_sung_muc``)."""
    return await nodes.node_bo_sung_muc(state)


def sau_khi_ket_thuc(state: AgentState) -> str:
    """Còn khía cạnh nào chưa có dữ liệu thì bù, rồi mới sinh câu trả lời.

    Hỏi lại / từ chối / lỗi thì **không** bù: đã có câu nói riêng cho người dùng, thêm ngữ
    cảnh không làm nó đúng hơn.
    """
    if str(state.get("outcome") or "") != Outcome.ANSWERED.value:
        return SINH
    if state.get("coverage"):
        # Executor đã chạy đúng các task của plan; bù thêm sẽ truy xuất lần hai.
        return SINH
    if nodes.khia_canh_con_thieu(state):
        return BO_SUNG_MUC
    return SINH


# ── Cạnh rẽ nhánh ────────────────────────────────────────────────────────


def sau_khi_neo(state: AgentState) -> str:
    """Có neo rồi, hay là câu thống kê, thì khỏi nhúng; còn lại phải nhúng để tra đệm."""
    if str(state.get("outcome") or "") == Outcome.ABSTAINED.value:
        # ``neo`` đã kết luận ngoài phạm vi (tỉnh khác / mã không tồn tại) và dựng sẵn câu
        # từ chối. Đi thẳng tới đó — nhúng hay gọi router lúc này chỉ tốn tiền mà không đổi
        # được kết luận.
        return TU_CHOI
    if state.get("codes") or state.get("documents"):
        return ROUTER
    if state.get("entity") and resolve.do_thi_tra_loi_duoc_bang_thuc_the(
        str(state.get("question") or ""), state.get("entity")
    ):
        # Thực thể **đủ** để đồ thị trả lời (câu liệt kê theo cơ quan/cấp/lĩnh vực) → đi thẳng.
        # Còn thực thể chỉ là manh mối (câu hỏi nội dung) → phải qua bước định danh tên, vì
        # "phí bao nhiêu" cần biết **thủ tục nào**, không phải lĩnh vực nào.
        return ROUTER
    if state.get("entity_ambiguous"):
        return ROUTER  # đã biết là mơ hồ → hỏi lại, nhúng thêm không giúp gì
    if resolve.needs_no_anchor(str(state.get("question") or "")):
        return ROUTER
    return DINH_DANH


def sau_khi_router(state: AgentState) -> str:
    """Nhánh nào được chọn thì đi nhánh đó; thiếu vector thì nhúng bổ sung trước.

    Thứ tự kiểm quan trọng: **thiếu vector thì nhúng trước**, chứ không đi thẳng vào nhánh.
    Đi thẳng thì nhánh lai không có vector và trả 0 bằng chứng — trông như "không tìm thấy
    gì" trong khi thật ra là "chưa nhúng".
    """
    nhanh = str(state.get("branch") or "")
    # Plan do semantic parser sinh thì executor là **đường chạy duy nhất**, kể cả khi plan
    # rỗng hoặc chỉ có ``unsupported``. Nếu để rơi về nhánh cũ, quyết định "không hỗ trợ"
    # của planner bị bỏ qua và Graph/Hybrid vẫn truy xuất.
    plan = state.get("plan") or {}
    if nhanh and (plan.get("tasks") or plan.get("unsupported")):
        return THUC_THI
    if nhanh in CAN_VECTOR and not state.get("vector_hash"):
        return NHUNG_BO_SUNG
    if nhanh in {b.value for b in CAC_NHANH}:
        return nhanh
    # Không nhánh nào: phân biệt **hỏi lại** với **từ chối**. Hai chuyện khác nhau với người
    # dùng — "tôi không biết bạn hỏi thủ tục nào" khác "dữ liệu của tôi không có thứ đó".
    if str(state.get("branch_signal") or "") == BranchSignal.EMPTY.value:
        return TU_CHOI
    return HOI_LAI


def sau_khi_bo_sung(state: AgentState) -> str:
    """Nhúng xong thì vào đúng nhánh đã chọn."""
    nhanh = str(state.get("branch") or "")
    return nhanh if nhanh in {b.value for b in CAC_NHANH} else HOI_LAI


# ── Dựng đồ thị ──────────────────────────────────────────────────────────


def _dung_lai_ket_qua(state: AgentState) -> resolve.Resolution:
    """Dựng lại kết quả định danh từ trạng thái — để gọi bảng quyết định.

    Router nhận :class:`Resolution` chứ không nhận trạng thái, vì nó được kiểm thử độc lập
    (việc 13.4). Hàm này là cầu nối duy nhất giữa hai kiểu dữ liệu.
    """
    thong_tin = state.get("resolution") or {}
    ket_qua = resolve.Resolution(question=str(state.get("question") or ""))
    ket_qua.codes = list(state.get("codes") or [])
    ket_qua.asked_codes = list(thong_tin.get("asked") or [])
    ket_qua.documents = list(state.get("documents") or [])
    ket_qua.entity = dict(state["entity"]) if state.get("entity") else None
    ket_qua.entity_ambiguous = bool(state.get("entity_ambiguous"))
    ket_qua.needs_antecedent = bool(state.get("needs_antecedent"))
    ket_qua.dau_vet_vector = str(state.get("vector_hash") or "")
    ket_qua.embedding_used = bool(state.get("embedding_used"))
    ket_qua.procedure = ProcedureResolution(
        code=str(thong_tin.get("code") or ""),
        name=str(thong_tin.get("name") or ""),
        method=str(thong_tin.get("method") or ""),
        confidence=float(thong_tin.get("confidence") or 0.0),
        ambiguous=bool(thong_tin.get("ambiguous")),
        alternatives=[
            (str(a.get("code") or ""), str(a.get("name") or ""), float(a.get("score") or 0.0))
            for a in (thong_tin.get("alternatives") or [])
        ],
        note=str(thong_tin.get("note") or ""),
    )
    ket_qua.ma = ket_qua.codes[0] if ket_qua.codes else (ket_qua.procedure.code or "")
    ket_qua.ten = ket_qua.procedure.name or ""
    return ket_qua


def build_graph():
    """Dựng và biên dịch đồ thị. Trả về đối tượng chạy được (``ainvoke``)."""
    do_thi = StateGraph(AgentState)

    do_thi.add_node(NEO, node_neo)
    do_thi.add_node(DINH_DANH, node_dinh_danh)
    do_thi.add_node(ROUTER, node_router)
    do_thi.add_node(THUC_THI, node_thuc_thi)
    do_thi.add_node(NHUNG_BO_SUNG, node_nhung_bo_sung)
    do_thi.add_node(HOI_LAI, node_hoi_lai)
    do_thi.add_node(TU_CHOI, node_tu_choi)
    do_thi.add_node(KET_THUC, node_ket_thuc)
    do_thi.add_node(SINH, node_sinh)
    do_thi.add_node(BO_SUNG_MUC, node_bo_sung_muc)
    for nhanh, buoc in nodes.NODES.items():
        do_thi.add_node(nhanh, buoc)

    do_thi.add_edge(START, NEO)
    do_thi.add_conditional_edges(
        NEO, sau_khi_neo, {ROUTER: ROUTER, DINH_DANH: DINH_DANH, TU_CHOI: TU_CHOI}
    )
    # Chỉ còn một đường: định danh xong thì giao cho router. Không còn nhánh rẽ nào ở đây —
    # kho câu hỏi thường gặp đã được gỡ khỏi luồng truy xuất.
    do_thi.add_edge(DINH_DANH, ROUTER)
    do_thi.add_conditional_edges(
        ROUTER,
        sau_khi_router,
        {
            **{b.value: b.value for b in CAC_NHANH},
            NHUNG_BO_SUNG: NHUNG_BO_SUNG,
            THUC_THI: THUC_THI,
            HOI_LAI: HOI_LAI,
            TU_CHOI: TU_CHOI,
        },
    )
    do_thi.add_conditional_edges(
        NHUNG_BO_SUNG,
        sau_khi_bo_sung,
        {**{b.value: b.value for b in CAC_NHANH}, HOI_LAI: HOI_LAI},
    )
    for nhanh in CAC_NHANH:
        do_thi.add_edge(nhanh.value, KET_THUC)
    do_thi.add_edge(THUC_THI, KET_THUC)
    do_thi.add_edge(HOI_LAI, KET_THUC)
    do_thi.add_edge(TU_CHOI, KET_THUC)
    do_thi.add_conditional_edges(KET_THUC, sau_khi_ket_thuc, {SINH: SINH, BO_SUNG_MUC: BO_SUNG_MUC})
    do_thi.add_edge(BO_SUNG_MUC, SINH)
    do_thi.add_edge(SINH, END)

    return do_thi.compile()


#: Đồ thị dùng chung. Biên dịch một lần ở lần import đầu tiên.
WORKFLOW = build_graph()


def mermaid() -> str:
    """Sơ đồ dạng văn bản Mermaid — để dán vào báo cáo và vẽ thành hình."""
    return WORKFLOW.get_graph().draw_mermaid()
