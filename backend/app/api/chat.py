"""Public chat API backed by the unified retrieval workflow.

Bốn thứ được xử lý **ở đây** thay vì để client tự làm:

* **Gộp nguồn trùng** — bằng chứng là 10 đoạn của cùng một thủ tục, nên danh sách thô có 10
  dòng y hệt nhau. Người dân nhìn 10 dòng giống nhau sẽ tưởng hệ thống lỗi.
* **Nói rõ loại kết cục** — trả lời được, cần hỏi lại, hay từ chối. Cờ ``abstained`` cũ gộp
  hai loại sau vào một, khiến giao diện tô câu hỏi lại bằng màu "không trả lời được".
* **Giữ cấu trúc lựa chọn** — câu hỏi lại có thể có 2–5 thủ tục để người dùng chọn; trả về
  dạng mảng để giao diện vẽ nút bấm, thay vì nhét vào chuỗi văn bản.
* **Chặn lạm dụng và lặp lại** — endpoint công khai, mỗi câu tốn hai lần gọi mô hình.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from collections import OrderedDict, deque
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, StringConstraints

from backend.app.workflow import trace_log

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

#: Số nguồn tối đa trả về. Ba nguồn là đủ để đối chiếu; nhiều hơn thì người đọc bỏ qua.
MAX_CITATIONS = 3

#: Số câu tối đa một địa chỉ IP được hỏi trong một phút. Đặt ``CHAT_RATE_LIMIT_PER_MIN=0`` để tắt.
RATE_LIMIT = int(os.getenv("CHAT_RATE_LIMIT_PER_MIN", "10"))

#: Thời gian giữ một câu trả lời đã sinh. ``CHAT_CACHE_TTL_S=0`` để tắt.
CACHE_TTL_S = float(os.getenv("CHAT_CACHE_TTL_S", "600"))

#: Số câu trả lời giữ trong cache.
CACHE_MAX = 256


class ChatRequest(BaseModel):
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ]


class CitationResponse(BaseModel):
    title: str
    url: str = ""
    #: Mục nội dung mà nguồn này ứng với ("Phí, lệ phí", "Hồ sơ, giấy tờ"…). Rỗng nếu không rõ.
    section: str = ""


class ProcedureSummary(BaseModel):
    procedure_code: str
    procedure_name: str


class ClarifyOptionResponse(BaseModel):
    """Một lựa chọn cho câu hỏi lại — giao diện vẽ thành nút, người dùng bấm là hỏi tiếp."""

    value: str
    label: str
    hint: str = ""


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationResponse]
    procedure: ProcedureSummary | None = None
    #: ``answered`` = có câu trả lời; ``clarify`` = cần người dùng chọn; ``abstained`` = từ chối.
    status: Literal["answered", "clarify", "abstained"] = "answered"
    #: Giữ cho client cũ. Tương đương ``status != "answered"``.
    abstained: bool = False
    #: Chỉ có khi ``status == "clarify"`` và hệ thống biết các lựa chọn cụ thể.
    options: list[ClarifyOptionResponse] = []


# ══════════════════════════════════════════════════════════════════════════
# CHẶN LẠM DỤNG — theo IP, cửa sổ trượt 60 giây
# ══════════════════════════════════════════════════════════════════════════

_luot_goi: dict[str, deque[float]] = {}


def _ip(yeu_cau: Request) -> str:
    """IP của người gọi, ưu tiên ``X-Forwarded-For`` khi chạy sau proxy."""
    chuyen_tiep = yeu_cau.headers.get("x-forwarded-for") or ""
    if chuyen_tiep:
        return chuyen_tiep.split(",")[0].strip()
    return yeu_cau.client.host if yeu_cau.client else ""


def _kiem_tan_suat(ip: str) -> None:
    """Ném 429 nếu IP đã hỏi quá nhiều trong một phút.

    Bộ đếm nằm trong **bộ nhớ tiến trình** — đủ cho một máy chủ. Chạy nhiều tiến trình thì cần
    Redis; ghi ở đây để không ai tưởng nó là giới hạn toàn cục.
    """
    if RATE_LIMIT <= 0 or not ip:
        return

    now = time.monotonic()
    cua_so = _luot_goi.setdefault(ip, deque())
    while cua_so and now - cua_so[0] > 60:
        cua_so.popleft()

    if len(cua_so) >= RATE_LIMIT:
        con_lai = int(60 - (now - cua_so[0])) + 1
        raise HTTPException(
            status_code=429,
            detail=(
                "Bạn đã hỏi quá nhiều câu trong một phút. "
                f"Vui lòng thử lại sau {con_lai} giây."
            ),
            headers={"Retry-After": str(con_lai)},
        )

    cua_so.append(now)
    # Dọn IP không còn hoạt động để dict không phình mãi.
    if len(_luot_goi) > 2048:
        for khoa in [k for k, v in _luot_goi.items() if not v]:
            _luot_goi.pop(khoa, None)


# ══════════════════════════════════════════════════════════════════════════
# CACHE CÂU TRẢ LỜI
# ══════════════════════════════════════════════════════════════════════════

_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()


def _khoa_cache(question: str) -> str:
    """Khoá theo **câu đã chuẩn hoá**: hoa/thường và khoảng trắng thừa không tạo mục mới."""
    chuan = " ".join(question.lower().split())
    return hashlib.sha256(chuan.encode("utf-8")).hexdigest()[:32]


def _lay_cache(khoa: str) -> dict[str, Any] | None:
    if CACHE_TTL_S <= 0:
        return None
    muc = _cache.get(khoa)
    if muc is None:
        return None
    het_han, du_lieu = muc
    if time.monotonic() > het_han:
        _cache.pop(khoa, None)
        return None
    _cache.move_to_end(khoa)
    return du_lieu


def _cat_cache(khoa: str, du_lieu: dict[str, Any]) -> None:
    if CACHE_TTL_S <= 0:
        return
    _cache[khoa] = (time.monotonic() + CACHE_TTL_S, du_lieu)
    _cache.move_to_end(khoa)
    while len(_cache) > CACHE_MAX:
        _cache.popitem(last=False)


def xoa_cache() -> None:
    """Xoá cache — dùng cho bài kiểm và khi cần đo lại từ đầu."""
    _cache.clear()


# ══════════════════════════════════════════════════════════════════════════
# ĐÓNG GÓI KẾT QUẢ
# ══════════════════════════════════════════════════════════════════════════


def _trich_dan(item: dict[str, Any]) -> CitationResponse:
    code = str(item.get("procedure_code") or "").strip()
    name = str(item.get("procedure_name") or "").strip()
    document = str(item.get("document_code") or "").strip()
    title = name or document or code or "Nguồn thủ tục hành chính"
    if code and code not in title:
        title = f"{title} (Mã TTHC: {code})"
    return CitationResponse(
        title=title,
        url=str(item.get("detail_url") or "").strip(),
        section=str(item.get("section") or "").strip(),
    )


def _gop_nguon(
    items: list[dict[str, Any]], *, ma_thu_tuc: str = ""
) -> list[CitationResponse]:
    """Gộp nguồn trùng, chỉ giữ nguồn của **thủ tục đã trả lời**, cắt còn :data:`MAX_CITATIONS`.

    Hai việc, cùng một lý do: danh sách nguồn phải là **căn cứ của câu trả lời**.

    * Gộp trùng — bằng chứng là 10 đoạn của cùng một thủ tục, nên danh sách thô có 10 dòng y
      hệt; người dân thấy 10 dòng giống nhau sẽ tưởng hệ thống lỗi.
    * Chỉ giữ nguồn của thủ tục đã trả lời — nhánh lai lấy về cả đoạn của thủ tục khác (cùng
      lĩnh vực), và để nguyên thì câu trả lời về ATTP lại kèm nguồn về đăng ký đất đai. Đo
      được đúng ca đó: 3 nguồn, 2 nguồn thuộc thủ tục khác.
    """
    if ma_thu_tuc:
        cung_ma = [x for x in items if str(x.get("procedure_code") or "") == ma_thu_tuc]
        if cung_ma:
            items = cung_ma

    ra: list[CitationResponse] = []
    da_co: set[str] = set()
    for item in items:
        trich = _trich_dan(item)
        khoa = trich.url or trich.title
        if khoa in da_co:
            continue
        da_co.add(khoa)
        ra.append(trich)
        if len(ra) >= MAX_CITATIONS:
            break
    return ra


def _lua_chon(clarify: dict[str, Any]) -> list[ClarifyOptionResponse]:
    ra: list[ClarifyOptionResponse] = []
    for option in clarify.get("options") or []:
        if not isinstance(option, dict):
            continue
        label = str(option.get("label") or "").strip()
        value = str(option.get("value") or "").strip()
        if not (label or value):
            continue
        ra.append(
            ClarifyOptionResponse(
                value=value,
                label=label or value,
                hint=str(option.get("hint") or "").strip(),
            )
        )
    return ra


def _tra_loi_hoi_lai(clarify: dict[str, Any]) -> str:
    """Văn bản cho câu hỏi lại — giao diện nào không đọc ``options`` vẫn dùng được."""
    question = str(clarify.get("question") or "").strip()
    nhan = [o.label for o in _lua_chon(clarify)]
    return "\n".join([question, *(f"- {x}" for x in nhan)]).strip()


def _status(outcome: str) -> Literal["answered", "clarify", "abstained"]:
    if outcome == "answered":
        return "answered"
    if outcome == "clarify":
        return "clarify"
    return "abstained"


def _dung_phan_hoi(result: dict[str, Any]) -> ChatResponse:
    """Đổi kết quả luồng thành phản hồi công khai. Không gọi mô hình, không chạm mạng."""
    outcome = str(result.get("outcome") or "")
    status = _status(outcome)

    clarify = dict(result.get("clarify") or {})
    options = _lua_chon(clarify)

    answer = str(result.get("answer") or "").strip()
    if not answer and status == "clarify":
        answer = _tra_loi_hoi_lai(clarify)
    if not answer:
        answer = str(result.get("refusal") or "").strip()
    if not answer:
        answer = (
            "Tôi chưa trả lời được câu này bằng dữ liệu hiện có. "
            "Bạn có thể hỏi về hồ sơ, lệ phí, thời hạn, trình tự thực hiện, cơ quan ban hành."
        )

    resolution = dict(result.get("resolution") or {})
    code = str(resolution.get("code") or "").strip()
    name = str(resolution.get("name") or "").strip()

    return ChatResponse(
        answer=answer,
        citations=_gop_nguon(list(result.get("citations") or []), ma_thu_tuc=code),
        procedure=(
            ProcedureSummary(procedure_code=code, procedure_name=name or code)
            if code
            else None
        ),
        status=status,
        abstained=status != "answered",
        options=options if status == "clarify" else [],
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    """Chạy một câu hỏi công khai qua đúng luồng mà trang quản trị dùng."""
    from backend.app.rag import retrieval

    _kiem_tan_suat(_ip(request))

    khoa = _khoa_cache(payload.question)
    da_co = _lay_cache(khoa)
    if da_co is not None:
        return ChatResponse(**da_co)

    result = await retrieval.retrieve(payload.question, source="chat")
    if str(result.get("outcome") or "") == "error":
        raise HTTPException(status_code=503, detail="Hệ thống chưa thể xử lý câu hỏi lúc này.")

    phan_hoi = _dung_phan_hoi(result)
    _cat_cache(khoa, phan_hoi.model_dump())
    return phan_hoi


# ══════════════════════════════════════════════════════════════════════════
# STREAMING — dùng cho giao diện người dân
# ══════════════════════════════════════════════════════════════════════════


def _su_kien(event: str, du_lieu: dict[str, Any]) -> str:
    """Một khung SSE. ``ensure_ascii=False`` để tiếng Việt không bị \\uXXXX."""
    return f"event: {event}\ndata: {json.dumps(du_lieu, ensure_ascii=False)}\n\n"


#: Kích thước một mẩu khi **phát lại** câu trả lời đã lưu.
#:
#: Câu trả lời cache không cần "stream" vì đã có sẵn, nhưng người dùng vẫn phải thấy nó chạy
#: như câu mới — nếu hiện một cục thì hai đường trông khác nhau, và người dùng tưởng câu cache
#: bị lỗi. Cắt theo **từ** để không chẻ đôi một từ hay một cụm in đậm.
CAT_MAU = 40


def _cat_mau(van_ban: str, *, co: int = CAT_MAU) -> list[str]:
    """Cắt văn bản thành các mẩu ~``co`` ký tự, cắt ở ranh giới từ."""
    mau: list[str] = []
    hien = ""
    for tu in van_ban.split(" "):
        ung_vien = f"{hien} {tu}".strip()
        if len(ung_vien) > co and hien:
            mau.append(hien + " ")
            hien = tu
        else:
            hien = ung_vien
    if hien:
        mau.append(hien)
    return mau


async def _phat_stream(
    question: str, ket_qua: dict[str, Any]
) -> AsyncIterator[str]:
    """Phát câu trả lời theo từng mẩu.

    Ba loại sự kiện, cố ý tách nhau:

    * ``meta`` — trạng thái, thủ tục, nguồn, **và lựa chọn** (nếu cần hỏi lại). Gửi **trước**
      khi sinh, vì đó là thứ giao diện cần để vẽ khung và nút bấm ngay.
    * ``delta`` — từng mẩu chữ. Đây là phần người dùng thấy chạy.
    * ``done`` — câu trả lời đầy đủ (để giao diện chốt lại, và để khớp cache).

    Hỏi lại / từ chối thì **không** có ``delta``: câu đó không do mô hình viết, gửi nguyên văn
    một lần trong ``done`` còn hơn giả vờ stream.
    """
    from backend.app.workflow import answer as sinh

    phan_hoi = _dung_phan_hoi(ket_qua)
    yield _su_kien(
        "meta",
        {
            "status": phan_hoi.status,
            "procedure": phan_hoi.procedure.model_dump() if phan_hoi.procedure else None,
            "citations": [c.model_dump() for c in phan_hoi.citations],
            "options": [o.model_dump() for o in phan_hoi.options],
            # Để phía client và bộ đo phân biệt được câu trả lời thật với câu phát lại.
            "cached": False,
        },
    )

    if phan_hoi.status != "answered" or not ket_qua.get("evidence"):
        yield _su_kien("done", {"answer": phan_hoi.answer, "streamed": False})
        return

    gom: list[str] = []
    try:
        async for mau in sinh.sinh_stream(
            question,
            list(ket_qua["evidence"]),
            thieu=list(ket_qua.get("thieu") or []),
            requests=list((ket_qua.get("question_frame") or {}).get("requests") or []),
            coverage=list(ket_qua.get("coverage") or []),
        ):
            gom.append(mau)
            yield _su_kien("delta", {"text": mau})
    except sinh.AnswerError as exc:
        # Ghi lý do vào kết quả để trace cuối lượt thấy được lỗi sinh câu trả lời.
        ket_qua["error"] = f"answer_error: {exc.reason}"
        # Chưa phát được mẩu nào → có câu trả lời dự phòng (từ chối) thay vì khung trống.
        if not gom:
            yield _su_kien("done", {"answer": phan_hoi.answer, "streamed": False})
        else:
            yield _su_kien("error", {"message": exc.reason, "partial": "".join(gom)})
        return

    day_du = "".join(gom).strip()
    # Ghi lại vào kết quả để nơi gọi cache **đúng nội dung đã stream**, không phải bản rỗng.
    ket_qua["answer"] = day_du or phan_hoi.answer
    # Kiểm chứng hậu sinh: stream không thể viết lại, nhưng vẫn ghi lại để monitoring/cache thấy
    # câu nào mô hình phủ nhận bằng chứng hoặc bỏ sót ý.
    covered_facets = [
        str(item.get("facet") or "")
        for item in (ket_qua.get("coverage") or [])
        if str(item.get("status") or "") == "covered" and item.get("facet")
    ]
    issues = sinh.verify_contract(
        ket_qua["answer"],
        list(ket_qua["evidence"]),
        thieu=list(ket_qua.get("thieu") or []),
        covered_facets=covered_facets,
    )
    ket_qua["verification"] = {"status": "ok" if not issues else "issues", "issues": issues}
    if issues:
        logger.warning("Kiểm chứng câu trả lời stream có vấn đề: %s", issues)
    yield _su_kien("done", {"answer": ket_qua["answer"], "streamed": True})


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request) -> StreamingResponse:
    """Như ``POST /chat`` nhưng phát câu trả lời theo từng mẩu (SSE).

    ``POST /chat`` vẫn giữ nguyên cho trang quản trị: nó trả một lần, dễ đo và dễ so sánh.
    Giao diện người dân dùng đường này vì chờ 5 giây nhìn vòng xoay là trải nghiệm tệ.
    """
    from backend.app.rag import retrieval

    _kiem_tan_suat(_ip(request))

    khoa = _khoa_cache(payload.question)
    da_co = _lay_cache(khoa)
    if da_co is not None:
        async def _phat_lai() -> AsyncIterator[str]:
            # Cùng hình dạng sự kiện với đường chạy thật, để client không phải xử lý hai kiểu.
            yield _su_kien("start", {"question": payload.question})
            yield _su_kien(
                "meta",
                {
                    **{k: da_co[k] for k in ("status", "procedure", "citations", "options")},
                    "cached": True,
                },
            )
            # Phát lại thành từng mẩu: câu cache phải **trông** giống câu mới. Không có mô
            # hình nào chạy ở đây — chỉ cắt chuỗi đã lưu, nên chi phí bằng 0.
            for manh in _cat_mau(str(da_co.get("answer") or "")):
                yield _su_kien("delta", {"text": manh})
            yield _su_kien("done", {"answer": da_co["answer"], "streamed": True})

        return StreamingResponse(
            _phat_lai(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def _phat() -> AsyncIterator[str]:
        # Mở luồng **trước** khi tra cứu. Nếu chạy đồ thị trước rồi mới trả ``StreamingResponse``
        # thì byte đầu tiên phải chờ trọn 5–7 giây — đúng thứ streaming sinh ra để tránh. Đo
        # được: mẩu đầu về sau 6,7 s, trong khi bản này bắt đầu ngay.
        yield _su_kien("start", {"question": payload.question})
        bat_dau = time.perf_counter()

        ket_qua = await retrieval.retrieve(
            payload.question, generate=False, log_trace=False, source="chat_stream"
        )
        if str(ket_qua.get("outcome") or "") == "error":
            trace_log.append_from_state(
                payload.question,
                ket_qua,
                ms=int((time.perf_counter() - bat_dau) * 1000),
                source="chat_stream",
                phase="error",
                error_detail=str(ket_qua.get("error") or ""),
            )
            yield _su_kien("error", {"message": "Hệ thống chưa thể xử lý câu hỏi lúc này."})
            return

        async for khung in _phat_stream(payload.question, ket_qua):
            yield khung
        # Cache sau khi stream xong: câu lặp lại trả về ngay, không tốn lần sinh nữa.
        _cat_cache(khoa, _dung_phan_hoi(ket_qua).model_dump())
        # Ghi trace **sau khi stream xong** để có câu trả lời và kết quả kiểm chứng thật.
        trace_log.append_from_state(
            payload.question,
            ket_qua,
            ms=int((time.perf_counter() - bat_dau) * 1000),
            source="chat_stream",
            phase="final",
        )

    return StreamingResponse(
        _phat(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
