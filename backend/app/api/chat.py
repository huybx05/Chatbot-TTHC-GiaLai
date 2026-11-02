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

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.app.api.chat_sessions import persist_chat_message
from backend.app.api.faq import FaqSuggestion, find_ready_faq, suggest_ready_faqs
from backend.app.api.guest_sessions import resolve_guest_session, touch_guest_session
from backend.app.auth.dependencies import OptionalUser
from backend.app.config import settings
from backend.app.documents import repository
from backend.app.memory.rewriter import rewrite_question_with_memory
from backend.app.memory.service import (
    empty_memory,
    load_chat_memory,
    save_preferred_name,
    summarize_session_memory,
)
from backend.app.memory.types import SessionMemory
from backend.app.rate_limit import limiter
from backend.app.security_utils import client_ip
from backend.app.workflow import trace_log

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])

#: Số nguồn tối đa trả về. Ba nguồn là đủ để đối chiếu; nhiều hơn thì người đọc bỏ qua.
MAX_CITATIONS = 3

#: Thời gian giữ một câu trả lời đã sinh. ``CHAT_CACHE_TTL_S=0`` để tắt.
CACHE_TTL_S = float(os.getenv("CHAT_CACHE_TTL_S", "600"))

#: Số câu trả lời giữ trong cache.
CACHE_MAX = 256


class HistoryTurn(BaseModel):
    model_config = {"extra": "forbid"}

    role: Literal["user", "assistant"]
    content: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=1_200),
    ]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
    ]
    session_id: UUID | None = None
    history: list[HistoryTurn] = Field(default_factory=list, max_length=8)


async def _load_request_memory(
    payload: ChatRequest,
    user: dict[str, Any] | None,
    request: Request,
) -> SessionMemory:
    """Nạp memory theo session (browser) hoặc history (guest).

    Session ID do client gửi không bao giờ đủ để đọc dữ liệu:
    phải có user và session phải thuộc user đó.
    """
    if not settings.memory_enabled:
        memory = empty_memory()
        request.state.memory = memory
        return memory

    if payload.session_id is not None and user is None:
        guest = resolve_guest_session(request)
        if guest is None or str(guest["id"]) != str(payload.session_id):
            raise HTTPException(
                status_code=401,
                detail="Phiên khách đã hết hạn hoặc không hợp lệ.",
            )
        request.state.guest_session_id = payload.session_id
        touch_guest_session(payload.session_id)
        memory = await load_chat_memory(
            user_id=None,
            session_id=payload.session_id,
            current_message_id=None,
            history=[item.model_dump() for item in payload.history],
            allow_guest=True,
        )
        if memory is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện.")
        request.state.memory = memory
        return memory

    memory = await load_chat_memory(
        user_id=user["id"] if user is not None else None,
        session_id=payload.session_id,
        current_message_id=None,
        history=[item.model_dump() for item in payload.history],
    )

    if payload.session_id is not None and memory is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy cuộc trò chuyện.",
        )

    memory = memory or empty_memory()
    request.state.memory = memory
    logger.debug(
        "memory loaded: turns=%d topics=%d session=%s",
        len(memory.recent_turns),
        len(memory.topics),
        bool(payload.session_id),
    )
    return memory


async def _persist_message(
    payload: ChatRequest,
    user: dict[str, Any] | None,
    *,
    role: Literal["user", "assistant"],
    content: str,
    metadata: dict[str, Any] | None = None,
    guest_session_id: UUID | None = None,
) -> str | None:
    if payload.session_id is None or not content.strip():
        return None
    guest = user is None
    if guest and (
        guest_session_id is None
        or str(guest_session_id) != str(payload.session_id)
    ):
        return None
    try:
        message_id = await asyncio.to_thread(
            persist_chat_message,
            session_id=payload.session_id,
            user_id=None if guest else int(user["id"]),
            role=role,
            content=content,
            metadata=metadata,
            guest=guest,
        )
        return str(message_id)
    except Exception:
        logger.exception("Không lưu được %s message cho session %s", role, payload.session_id)
        return None


def _queue_memory_summary(
    background_tasks: BackgroundTasks,
    payload: ChatRequest,
    user: dict[str, Any] | None,
) -> None:
    if payload.session_id is not None:
        background_tasks.add_task(summarize_session_memory, payload.session_id)


def _assistant_metadata(
    response: ChatResponse,
    *,
    source: str = "",
    social_intent: str = "",
    ttft_ms: int | None = None,
    total_ms: int | None = None,
    streamed: bool = False,
) -> dict[str, Any]:
    data = {
        "citations": [item.model_dump() for item in response.citations],
        "documents": [item.model_dump() for item in response.documents],
        "procedure": response.procedure.model_dump() if response.procedure else None,
        "status": response.status,
        "memory_eligible": (
            response.status == "answered" and response.procedure is not None
        ),
        "options": [item.model_dump() for item in response.options],
        "abstained": response.abstained,
        "streamed": streamed,
        "suggestions": [item.model_dump() for item in response.suggestions],
    }
    if source:
        data["source"] = source
    if social_intent:
        data["social_intent"] = social_intent
    if ttft_ms is not None:
        data["ttft_ms"] = ttft_ms
    if total_ms is not None:
        data["total_ms"] = total_ms
    return data


def _elapsed_ms(started_at: float) -> int:
    return max(0, int((time.perf_counter() - started_at) * 1000))


def _previous_questions(
    memory: SessionMemory | None, payload: ChatRequest
) -> list[str]:
    questions: list[str] = []
    if memory is not None:
        questions.extend(
            turn.content
            for turn in memory.recent_turns
            if turn.role == "user" and turn.content.strip()
        )
    questions.extend(
        item.content
        for item in (payload.history or [])
        if item.role == "user" and item.content.strip()
    )
    return questions


def _suggestions_for_result(
    result: dict[str, Any],
    response: ChatResponse,
    *,
    previous_questions: list[str] | None = None,
) -> list[FaqSuggestion]:
    if response.status != "answered" or response.procedure is None:
        return []
    code = response.procedure.procedure_code
    frame = result.get("question_frame") or {}
    facets = [
        str(item.get("facet") or "")
        for item in (frame.get("requests") or [])
        if isinstance(item, dict)
    ]
    question = str(result.get("original_question") or result.get("question") or "")
    return [
        FaqSuggestion(**item)
        for item in suggest_ready_faqs(
            code,
            facets=facets,
            exclude_question=question,
            exclude_questions=previous_questions or (),
            limit=3,
        )
    ]


def _suggestions_for_faq(
    faq: dict[str, Any],
    *,
    exclude_question: str,
    previous_questions: list[str] | None = None,
) -> list[FaqSuggestion]:
    code = str(faq.get("procedure_code") or "")
    if not code:
        return []
    return [
        FaqSuggestion(**item)
        for item in suggest_ready_faqs(
            code,
            facets=[str(faq.get("intent") or "")],
            exclude_question=exclude_question,
            exclude_questions=previous_questions or (),
            limit=3,
        )
    ]


def _with_suggestions(
    result: dict[str, Any],
    response: ChatResponse,
    *,
    previous_questions: list[str] | None = None,
) -> ChatResponse:
    suggestions = _suggestions_for_result(
        result, response, previous_questions=previous_questions
    )
    return (
        response.model_copy(update={"suggestions": suggestions})
        if suggestions
        else response
    )


def _answer_source(result: dict[str, Any]) -> str:
    """Nguồn đã tạo bằng chứng: ``hybrid``, ``graph`` hoặc ``fact_lookup``."""
    if result.get("source"):
        return str(result["source"])
    sources = {
        str(item.get("source") or "")
        for item in (result.get("evidence") or [])
        if isinstance(item, dict)
    }
    for source in ("hybrid", "graph", "fact_lookup"):
        if source in sources:
            return source
    return ""


_SOCIAL_REPLIES: dict[str, tuple[str, ...]] = {
    "greeting": (
        (
            "Xin chào! Mình có thể giúp bạn tra cứu thủ tục hành chính tại Gia Lai. "
            "Bạn muốn tìm thủ tục nào?"
        ),
        (
            "Chào bạn! Mình sẵn sàng hỗ trợ tra cứu hồ sơ, thời hạn, phí và cơ quan "
            "giải quyết thủ tục. Bạn cần tìm thủ tục gì?"
        ),
    ),
    "thanks": (
        "Rất vui được hỗ trợ bạn. Nếu cần tra cứu thêm thủ tục nào, bạn cứ hỏi nhé.",
        "Cảm ơn bạn! Khi cần tra cứu thủ tục hành chính, bạn quay lại đây bất cứ lúc nào.",
    ),
    "goodbye": (
        "Chào bạn, hẹn gặp lại! Khi cần tra cứu thủ tục hành chính, bạn quay lại nhé.",
        "Tạm biệt bạn! Chúc bạn một ngày tốt lành.",
    ),
    "acknowledgement": (
        "Vâng, mình đã ghi nhận. Bạn cần tra cứu thêm thủ tục nào không?",
        "Được ạ. Nếu cần thêm thông tin, bạn cứ hỏi mình nhé.",
    ),
    "other": (
        "Mình có thể giúp bạn tra cứu thủ tục hành chính tại Gia Lai. Bạn muốn tìm thủ tục nào?",
    ),
}


def _clean_preferred_name(value: Any) -> str:
    """Tên chỉ để xưng hô: chữ cái, khoảng trắng, gạch nối, dấu nháy, chấm."""
    text = " ".join(str(value or "").split())
    if not text or len(text) > 50 or len(text.split()) > 4:
        return ""
    if any(not (character.isalpha() or character in " -'") for character in text):
        return ""
    return text


def _attach_preferred_name(result: dict[str, Any]) -> dict[str, Any]:
    frame = result.get("question_frame") or {}
    name = _clean_preferred_name(frame.get("preferred_name"))
    if not name:
        return result
    updated = dict(result)
    updated["preferred_name"] = name
    return updated


def _apply_social_answer(result: dict[str, Any]) -> dict[str, Any]:
    """Thay kết quả xã giao bằng câu trả lời tự nhiên, không truy xuất dữ liệu."""
    frame = result.get("question_frame") or {}
    if str(frame.get("scope") or "") != "smalltalk":
        return result

    intent = str(frame.get("social_intent") or "other")
    name = str(
        result.get("preferred_name") or _clean_preferred_name(frame.get("preferred_name"))
    ).strip()
    if name:
        named = {
            "greeting": (
                f"Chào {name}! Mình có thể giúp {name} tra cứu thủ tục hành chính tại Gia Lai. "
                f"{name} muốn tìm thủ tục nào?"
            ),
            "thanks": (
                f"Rất vui được hỗ trợ {name}. Nếu cần tra cứu thêm thủ tục nào, "
                f"{name} cứ hỏi nhé."
            ),
            "goodbye": f"Chào {name}, hẹn gặp lại! Khi cần tra cứu thủ tục, {name} quay lại nhé.",
            "acknowledgement": f"Vâng, mình đã ghi nhận. {name} cần tra cứu thêm gì không?",
        }
        answer = named.get(
            intent,
            f"Mình có thể giúp {name} tra cứu thủ tục hành chính tại Gia Lai.",
        )
    else:
        replies = _SOCIAL_REPLIES.get(intent, _SOCIAL_REPLIES["other"])
        index = hashlib.sha256(
            f"{intent}:{result.get('question') or ''}".encode()
        ).digest()[0] % len(replies)
        answer = replies[index]

    updated = dict(result)
    updated.update(
        {
            "outcome": "answered",
            "answer": answer,
            "refusal": "",
            "answerable": False,
            "evidence": [],
            "coverage": [],
            "citations": [],
            "source": "none",
            "social_intent": intent,
            "preferred_name": name,
        }
    )
    return updated


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


class DocumentResponse(BaseModel):
    """File mẫu đi kèm câu trả lời về hồ sơ."""

    id: str
    document_name: str
    file_name: str
    mime_type: str | None = None
    size_bytes: int | None = None
    download_url: str
    case_order: int = 0
    component_index: int = 0
    case_orders: list[int] = []
    component_indexes: list[int] = []
    file_id: str | None = None
    file_ids: list[str] = []


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationResponse]
    procedure: ProcedureSummary | None = None
    #: File mẫu — chỉ có khi câu trả lời phủ facet ``required_documents``.
    documents: list[DocumentResponse] = Field(default_factory=list)
    #: ``answered`` = có câu trả lời; ``clarify`` = cần người dùng chọn; ``abstained`` = từ chối.
    status: Literal["answered", "clarify", "abstained"] = "answered"
    #: Giữ cho client cũ. Tương đương ``status != "answered"``.
    abstained: bool = False
    #: Chỉ có khi ``status == "clarify"`` và hệ thống biết các lựa chọn cụ thể.
    options: list[ClarifyOptionResponse] = []
    #: Phase 1: tối đa 3 FAQ cùng thủ tục, khác facet vừa hỏi.
    suggestions: list[FaqSuggestion] = []


# ══════════════════════════════════════════════════════════════════════════
# CHẶN LẠM DỤNG — theo IP, cửa sổ 60 giây, Redis nếu có
# ══════════════════════════════════════════════════════════════════════════

#: Giữ tên cũ để test hiện có có thể monkeypatch/khôi phục.
RATE_LIMIT = settings.chat_rate_limit_per_min


class _ResetableMemory(dict[str, object]):
    """Dict tương thích test cũ; ``clear()`` cũng xoá bộ đếm limiter."""

    def clear(self) -> None:
        super().clear()
        limiter.reset()


_luot_goi: _ResetableMemory = _ResetableMemory()


def _ip(yeu_cau: Request) -> str:
    """IP thật của người gọi; không tin header nếu không đến từ proxy."""
    return client_ip(yeu_cau) or "unknown"


def _kiem_tan_suat(ip: str) -> None:
    """Ném 429 nếu IP đã hỏi quá nhiều trong một phút.

    Dùng limiter chung: Redis khi có ``REDIS_URL``, fallback in-memory khi local.
    """
    if RATE_LIMIT <= 0:
        return
    result = limiter.check(f"chat:{ip}", limit=RATE_LIMIT)
    if not result.allowed:
        raise HTTPException(
            status_code=429,
            detail=(
                "Bạn đã hỏi quá nhiều câu trong một phút. "
                f"Vui lòng thử lại sau {result.retry_after} giây."
            ),
            headers={"Retry-After": str(result.retry_after)},
        )


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


def _status(outcome: str) -> Literal["answered", "clarify", "abstained"]:
    if outcome == "answered":
        return "answered"
    if outcome == "clarify":
        return "clarify"
    return "abstained"


def _co_ho_so(coverage: list[dict[str, Any]]) -> bool:
    """Câu trả lời có phủ facet thành phần hồ sơ hay không."""
    return any(
        isinstance(item, dict)
        and str(item.get("facet") or "") == "required_documents"
        and str(item.get("status") or "") == "covered"
        for item in coverage
    )


_FILE_MARKER = re.compile(r"\{\{file:([^}]+)\}\}")


def _case_orders(result: dict[str, Any]) -> set[int]:
    return {
        int((item.get("metadata") or {}).get("case_order") or 0)
        for item in (result.get("evidence") or [])
        if (item.get("metadata") or {}).get("case_order")
    }


def _file_mau(
    code: str,
    *,
    case_orders: set[int] | None = None,
    file_ids: set[str] | None = None,
) -> list[DocumentResponse]:
    """Lấy file mẫu của thủ tục; lỗi DB không được làm hỏng câu trả lời."""
    if not code:
        return []

    try:
        if case_orders:
            records = repository.list_documents(code, case_orders=case_orders)
        else:
            records = repository.list_documents(code)
    except Exception:  # noqa: BLE001
        logger.exception("Không đọc được file mẫu của thủ tục %s", code)
        return []

    if file_ids:
        records = [
            record
            for record in records
            if set(record.file_ids or (record.file_id,)) & file_ids
        ]

    return [
        DocumentResponse(
            id=str(record.id),
            document_name=record.document_name,
            file_name=record.file_name,
            mime_type=record.mime_type,
            size_bytes=record.size_bytes,
            download_url=(
                f"{settings.api_v1_prefix}/documents/{record.id}/download"
            ),
            case_order=record.case_order,
            component_index=record.component_index,
            case_orders=list(record.case_orders),
            component_indexes=list(record.component_indexes),
            file_id=record.file_id,
            file_ids=list(record.file_ids),
        )
        for record in records
    ]


CLARIFY_REPHRASE_ANSWER = (
    "Xin lỗi bạn, tôi chưa hiểu được câu hỏi này. "
    "Bạn có thể diễn đạt lại theo cách khác hoặc mô tả chi tiết hơn "
    "về thủ tục bạn đang quan tâm giúp tôi được không?"
)


def _dung_phan_hoi(result: dict[str, Any]) -> ChatResponse:
    """Đổi kết quả luồng thành phản hồi công khai. Không gọi mô hình, không chạm mạng."""
    outcome = str(result.get("outcome") or "")
    status = _status(outcome)

    clarify = dict(result.get("clarify") or {})
    options = _lua_chon(clarify)

    if status == "clarify":
        # Người dùng tự mô tả lại; không đưa danh sách thủ tục dễ gây hiểu nhầm.
        answer = CLARIFY_REPHRASE_ANSWER
        options = []
    else:
        answer = str(result.get("answer") or "").strip()
        if not answer:
            answer = str(result.get("refusal") or "").strip()
        if not answer:
            answer = (
                "Tôi chưa trả lời được câu này bằng dữ liệu hiện có. "
                "Bạn có thể hỏi về hồ sơ, lệ phí, thời hạn, trình tự thực hiện, cơ quan ban hành."
            )

    answered = dict(result.get("answered_procedure") or {})
    code = str(answered.get("code") or "").strip()
    name = str(answered.get("name") or "").strip()
    answered_with_evidence = status == "answered" and bool(
        result.get("answerable", False)
    ) and bool(code)

    marker_ids = set(_FILE_MARKER.findall(answer))
    case_orders = _case_orders(result)
    documents = (
        _file_mau(
            code,
            case_orders=case_orders or None,
            file_ids=marker_ids or None,
        )
        if status == "answered"
        and _co_ho_so(list(result.get("coverage") or []))
        else []
    )

    return ChatResponse(
        answer=answer,
        citations=_gop_nguon(list(result.get("citations") or []), ma_thu_tuc=code),
        procedure=(
            ProcedureSummary(procedure_code=code, procedure_name=name or code)
            if answered_with_evidence and code
            else None
        ),
        documents=documents,
        status=status,
        abstained=status != "answered",
        options=options if status == "clarify" else [],
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    user: OptionalUser,
    background_tasks: BackgroundTasks,
) -> ChatResponse:
    """Chạy một câu hỏi công khai qua đúng luồng mà trang quản trị dùng."""
    from backend.app.rag import retrieval

    started_at = time.perf_counter()
    _kiem_tan_suat(_ip(request))
    memory = await _load_request_memory(payload, user, request)
    guest_id = getattr(request.state, "guest_session_id", None)
    memory_bound = payload.session_id is not None or bool(payload.history)
    await _persist_message(
        payload, user, role="user", content=payload.question, guest_session_id=guest_id
    )

    faq = find_ready_faq(payload.question)
    if faq is not None:
        code = str(faq.get("procedure_code") or "")
        phan_hoi = ChatResponse(
            answer=str(faq["answer"]),
            citations=[],
            procedure=(
                ProcedureSummary(
                    procedure_code=code,
                    procedure_name=str(faq.get("procedure_name") or code),
                )
                if code
                else None
            ),
            status="answered",
            abstained=False,
            suggestions=_suggestions_for_faq(
                faq,
                exclude_question=payload.question,
                previous_questions=_previous_questions(memory, payload),
            ),
        )
        saved_assistant = await _persist_message(
            payload,
            user,
            role="assistant",
            content=phan_hoi.answer,
            metadata=_assistant_metadata(
                phan_hoi,
                source="faq",
                total_ms=_elapsed_ms(started_at),
                streamed=False,
            ),
            guest_session_id=guest_id,
        )
        if saved_assistant:
            _queue_memory_summary(background_tasks, payload, user)
        return phan_hoi

    khoa = _khoa_cache(payload.question)
    da_co = _lay_cache(khoa) if not memory_bound else None
    if da_co is not None:
        return ChatResponse(**da_co)

    rewrite = await rewrite_question_with_memory(payload.question, memory)
    retrieval_question = rewrite.retrieval_question
    request.state.rewrite = rewrite
    memory_anchor = (
        rewrite.anchor.to_dict()
        if rewrite.used and rewrite.anchor is not None
        else None
    )

    result = await retrieval.retrieve(
        retrieval_question,
        original_question=payload.question,
        memory_anchor=memory_anchor,
        rewrite=rewrite.to_dict(),
        source="chat",
        memory=memory,
    )
    if str(result.get("outcome") or "") == "error":
        raise HTTPException(status_code=503, detail="Hệ thống chưa thể xử lý câu hỏi lúc này.")

    result = _apply_social_answer(_attach_preferred_name(result))
    if payload.session_id is not None and str(result.get("preferred_name") or "").strip():
        await save_preferred_name(payload.session_id, str(result["preferred_name"]))
    phan_hoi = _with_suggestions(
        result,
        _dung_phan_hoi(result),
        previous_questions=_previous_questions(memory, payload),
    )
    saved_assistant = await _persist_message(
        payload,
        user,
        role="assistant",
        content=phan_hoi.answer,
        metadata=_assistant_metadata(
            phan_hoi,
            source=_answer_source(result),
            social_intent=str(result.get("social_intent") or ""),
            total_ms=_elapsed_ms(started_at),
            streamed=False,
        ),
        guest_session_id=guest_id,
    )
    if saved_assistant:
        _queue_memory_summary(background_tasks, payload, user)
    if not memory_bound:
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
    question: str,
    ket_qua: dict[str, Any],
    *,
    save_assistant: Callable[[ChatResponse], Awaitable[str | None]] | None = None,
    started_at: float | None = None,
    previous_questions: list[str] | None = None,
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
    se_stream = phan_hoi.status == "answered" and bool(ket_qua.get("evidence"))
    yield _su_kien(
        "meta",
        {
            "status": phan_hoi.status,
            "procedure": phan_hoi.procedure.model_dump() if phan_hoi.procedure else None,
            "citations": [c.model_dump() for c in phan_hoi.citations],
            "options": [o.model_dump() for o in phan_hoi.options],
            # Khi đã có evidence, file mẫu chỉ được chốt sau khi model viết marker.
            # Gửi toàn bộ file của case ở đây sẽ khiến UI hiện 3 file trong khi câu trả lời
            # chỉ nhắc 2 mẫu.
            "documents": [] if se_stream else [d.model_dump() for d in phan_hoi.documents],
            # Để phía client và bộ đo phân biệt được câu trả lời thật với câu phát lại.
            "cached": False,
        },
    )

    if not se_stream:
        yield _su_kien("done", {"answer": phan_hoi.answer, "streamed": False})
        return

    gom: list[str] = []
    stream_started = time.perf_counter()
    try:
        async for mau in sinh.sinh_stream(
            question,
            list(ket_qua["evidence"]),
            thieu=list(ket_qua.get("thieu") or []),
            requests=list((ket_qua.get("question_frame") or {}).get("requests") or []),
            coverage=list(ket_qua.get("coverage") or []),
            preferred_name=str((ket_qua.get("memory") or {}).get("preferred_name") or ""),
        ):
            if started_at is not None and "ttft_ms" not in ket_qua:
                ket_qua["ttft_ms"] = _elapsed_ms(started_at)
            gom.append(mau)
            yield _su_kien("delta", {"text": mau})
    except sinh.AnswerError as exc:
        # Ghi lý do vào kết quả để trace cuối lượt thấy được lỗi sinh câu trả lời.
        ket_qua["error"] = f"answer_error: {exc.reason}"
        ket_qua.setdefault("timings", {})["generate_ms"] = int(
            (time.perf_counter() - stream_started) * 1000
        )
        # Chưa phát được mẩu nào → có câu trả lời dự phòng (từ chối) thay vì khung trống.
        if not gom:
            yield _su_kien("done", {"answer": phan_hoi.answer, "streamed": False})
        else:
            yield _su_kien("error", {"message": exc.reason, "partial": "".join(gom)})
        return

    ket_qua.setdefault("timings", {})["generate_ms"] = int(
        (time.perf_counter() - stream_started) * 1000
    )
    day_du = "".join(gom).strip()
    ket_qua["total_ms"] = _elapsed_ms(started_at) if started_at is not None else None
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
        requests=list((ket_qua.get("question_frame") or {}).get("requests") or []),
        coverage=list(ket_qua.get("coverage") or []),
    )
    ket_qua["verification"] = {"status": "ok" if not issues else "issues", "issues": issues}
    if issues:
        logger.warning("Kiểm chứng câu trả lời stream có vấn đề: %s", issues)
    final = _with_suggestions(
        ket_qua,
        _dung_phan_hoi(ket_qua),
        previous_questions=previous_questions or [],
    )
    message_id = await save_assistant(final) if save_assistant is not None else None
    yield _su_kien(
        "meta",
        {
            "status": final.status,
            "procedure": final.procedure.model_dump() if final.procedure else None,
            "citations": [c.model_dump() for c in final.citations],
            "options": [o.model_dump() for o in final.options],
            # Chốt danh sách file theo marker trong câu trả lời, không theo toàn bộ case.
            "documents": [d.model_dump() for d in final.documents],
            "cached": False,
            "message_id": message_id,
            "suggestions": [item.model_dump() for item in final.suggestions],
        },
    )
    yield _su_kien(
        "done",
        {"answer": ket_qua["answer"], "streamed": True, "message_id": message_id},
    )


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    user: OptionalUser,
    background_tasks: BackgroundTasks,
) -> StreamingResponse:
    """Như ``POST /chat`` nhưng phát câu trả lời theo từng mẩu (SSE).

    ``POST /chat`` vẫn giữ nguyên cho trang quản trị: nó trả một lần, dễ đo và dễ so sánh.
    Giao diện người dân dùng đường này vì chờ 5 giây nhìn vòng xoay là trải nghiệm tệ.
    """
    from backend.app.rag import retrieval

    started_at = time.perf_counter()
    _kiem_tan_suat(_ip(request))
    memory = await _load_request_memory(payload, user, request)
    guest_id = getattr(request.state, "guest_session_id", None)
    memory_bound = payload.session_id is not None or bool(payload.history)
    await _persist_message(
        payload, user, role="user", content=payload.question, guest_session_id=guest_id
    )

    faq = find_ready_faq(payload.question)
    if faq is not None:
        answer = str(faq["answer"])
        code = str(faq.get("procedure_code") or "")
        phan_hoi = ChatResponse(
            answer=answer,
            citations=[],
            procedure=(
                ProcedureSummary(
                    procedure_code=code,
                    procedure_name=str(faq.get("procedure_name") or code),
                )
                if code
                else None
            ),
            status="answered",
            abstained=False,
            suggestions=_suggestions_for_faq(
                faq,
                exclude_question=payload.question,
                previous_questions=_previous_questions(memory, payload),
            ),
        )
        # FAQ là câu trả lời đã có sẵn: lưu trước khi phát meta để có message_id
        # cho like/dislike, giống câu trả lời do mô hình sinh.
        saved_message_id = await _persist_message(
            payload,
            user,
            role="assistant",
            content=answer,
            metadata=_assistant_metadata(
                phan_hoi,
                source="faq",
                total_ms=_elapsed_ms(started_at),
                streamed=False,
            ),
            guest_session_id=guest_id,
        )
        if saved_message_id:
            _queue_memory_summary(background_tasks, payload, user)

        async def _phat_faq() -> AsyncIterator[str]:
            yield _su_kien("start", {"question": payload.question})
            yield _su_kien(
                "meta",
                {
                    "status": "answered",
                    "procedure": None,
                    "citations": [],
                    "options": [],
                    "documents": [],
                    "cached": False,
                    "message_id": saved_message_id,
                    "source": "faq",
                    "suggestions": [
                        item.model_dump() for item in phan_hoi.suggestions
                    ],
                },
            )
            for manh in _cat_mau(answer):
                yield _su_kien("delta", {"text": manh})
            yield _su_kien(
                "done",
                {"answer": answer, "streamed": True, "message_id": saved_message_id},
            )

        return StreamingResponse(
            _phat_faq(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            background=background_tasks,
        )

    khoa = _khoa_cache(payload.question)
    da_co = _lay_cache(khoa) if not memory_bound else None
    if da_co is not None:
        async def _phat_lai() -> AsyncIterator[str]:
            # Cùng hình dạng sự kiện với đường chạy thật, để client không phải xử lý hai kiểu.
            yield _su_kien("start", {"question": payload.question})
            yield _su_kien(
                "meta",
                {
                    **{
                        k: da_co[k]
                        for k in ("status", "procedure", "citations", "options")
                    },
                    "documents": da_co.get("documents") or [],
                    "suggestions": da_co.get("suggestions") or [],
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

        rewrite = await rewrite_question_with_memory(payload.question, memory)
        retrieval_question = rewrite.retrieval_question
        request.state.rewrite = rewrite
        memory_anchor = (
            rewrite.anchor.to_dict()
            if rewrite.used and rewrite.anchor is not None
            else None
        )

        retrieve_kwargs: dict[str, Any] = {
            "original_question": payload.question,
            "rewrite": rewrite.to_dict(),
            "generate": False,
            "log_trace": False,
            "source": "chat_stream",
            "memory": memory,
        }
        if memory_anchor is not None:
            retrieve_kwargs["memory_anchor"] = memory_anchor
        ket_qua = await retrieval.retrieve(retrieval_question, **retrieve_kwargs)
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

        ket_qua = _apply_social_answer(_attach_preferred_name(ket_qua))
        if payload.session_id is not None and str(ket_qua.get("preferred_name") or "").strip():
            await save_preferred_name(payload.session_id, str(ket_qua["preferred_name"]))
        saved_message_id: str | None = None

        async def save_assistant(final: ChatResponse) -> str | None:
            nonlocal saved_message_id
            if saved_message_id is None:
                saved_message_id = await _persist_message(
                    payload,
                    user,
                    role="assistant",
                    content=final.answer,
                    metadata=_assistant_metadata(
                        final,
                        source=_answer_source(ket_qua),
                        social_intent=str(ket_qua.get("social_intent") or ""),
                        ttft_ms=ket_qua.get("ttft_ms"),
                        total_ms=_elapsed_ms(started_at),
                        streamed=ket_qua.get("ttft_ms") is not None,
                    ),
                    guest_session_id=guest_id,
                )
            return saved_message_id

        try:
            async for khung in _phat_stream(
                payload.question,
                ket_qua,
                save_assistant=save_assistant,
                started_at=started_at,
                previous_questions=_previous_questions(memory, payload),
            ):
                yield khung
        finally:
            # Fallback: câu hỏi lại/từ chối không đi qua nhánh stream sinh chữ,
            # nên vẫn phải lưu assistant message sau khi generator kết thúc.
            if saved_message_id is None:
                await save_assistant(_dung_phan_hoi(ket_qua))
            if saved_message_id:
                _queue_memory_summary(background_tasks, payload, user)
        # Cache sau khi stream xong: câu lặp lại trả về ngay, không tốn lần sinh nữa.
        if not memory_bound:
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
        background=background_tasks,
    )
