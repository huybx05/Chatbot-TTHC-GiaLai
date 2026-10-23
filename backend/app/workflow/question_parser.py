"""Phân tích câu hỏi thành :class:`QuestionFrame` bằng LLM.

Mô hình chỉ mô tả ý nghĩa câu hỏi. Quyết định chọn nhánh vẫn do mã nguồn thực hiện để
không cho chuỗi từ mô hình điều khiển trực tiếp SQL, Cypher hay công cụ truy xuất.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, replace
from typing import Any

from openai import AsyncOpenAI

from backend.app.config import settings
from backend.app.rag import grounding
from backend.app.rag.evidence import Branch
from backend.app.rag.grounding import SubjectGrounding
from backend.app.rag.resolve import Resolution
from backend.app.workflow.question_frame import (
    QUESTION_FRAME_SCHEMA_VERSION,
    AmbiguityInfo,
    AmbiguityKind,
    ConstraintType,
    Facet,
    QuestionFrame,
    QuestionRequest,
    QuestionScope,
    RequestConstraint,
    RequestOperation,
    SubjectMention,
    SubjectType,
)
from backend.app.workflow.router_rules import PartSpec, RouterDecision
from backend.app.workflow.state import NEED_HOP_LE, BranchSignal, ClarifyInfo

logger = logging.getLogger(__name__)

PARSER_TIMEOUT_S = float(os.getenv("ROUTER_TIMEOUT_S", "10"))
PARSER_TEMPERATURE = 0.0
TAT_SUY_NGHI: dict[str, Any] = {"chat_template_kwargs": {"enable_thinking": False}}
CACHE_MAX = 512
MAX_SUBJECTS = 6
MAX_REQUESTS = 8
MAX_CONSTRAINTS = 8
MAX_TEXT_CHARS = 500
MAX_SCENARIO_CHARS = 500

CONTENT_FACETS = frozenset(NEED_HOP_LE)
GRAPH_FACETS = frozenset(
    {
        Facet.ISSUING_AGENCY.value,
        Facet.IMPLEMENTING_AGENCY.value,
        Facet.COORDINATING_AGENCY.value,
        Facet.AUTHORIZED_AGENCY.value,
        Facet.ADMINISTRATIVE_LEVEL.value,
        Facet.FIELD.value,
        Facet.DOMAIN_GROUP.value,
        Facet.STATUS.value,
        Facet.TARGET_AUDIENCE.value,
        Facet.RELATED_PROCEDURES.value,
    }
)

SYSTEM_PROMPT = """Bạn là bộ phận phân tích câu hỏi cho chatbot thủ tục hành chính tỉnh Gia Lai.

Nhiệm vụ duy nhất: chuyển câu hỏi thành QuestionFrame JSON. Không trả lời câu hỏi, không
chọn database, không chọn tool, không tạo SQL/Cypher và không tự gán mã thủ tục hay ID.

Trả đúng một JSON object theo khuôn:
{
  "schema_version": "1.0",
  "scope": "tthc|smalltalk|out_of_scope|unknown",
  "subject_mentions": [{"type": "procedure", "text": "cụm định danh ngắn"}],
  "requests": [{
    "text": "ý hỏi nguyên văn", "facet": "general_info", "operation": "get",
    "subject_ref": 0,
    "scenario": "cụm mô tả tình huống, nguyên văn; rỗng nếu không có",
    "constraints": []
  }],
  "ambiguity": {"present": false, "kind": "none|subject|request|constraint", "reason": ""}
}

subject.type chỉ được là: procedure, document, agency, field, administrative_level,
domain_group, target_audience, unknown.
operation chỉ được là: get, guide, list, count, compare, rank, check.
facet chỉ được là: required_documents, steps, submission_method, processing_time, fee,
result, legal_basis, requirements, general_info, issuing_agency, implementing_agency,
coordinating_agency, authorized_agency, administrative_level, field, domain_group, status,
target_audience, related_procedures, unknown.
constraint.type chỉ được là: agency, field, administrative_level, domain_group,
target_audience, status, location, time, unknown.

Quy tắc:
- Mỗi ý người dùng hỏi là một phần tử requests, giữ đúng thứ tự xuất hiện.
- scenario là cụm **mô tả tình huống** người dùng nêu cho ý đó, giữ nguyên văn
  (ví dụ: "cho thuê lại trong dự án", "bán tài sản gắn liền với đất thuê trả tiền hàng năm",
  "tặng cho Nhà nước để làm đường giao thông"). Không suy diễn, không đổi thành tên thủ tục,
  không gán mã. Câu không nêu tình huống thì để chuỗi rỗng "".
- Tách tình huống khỏi phần câu hỏi: phần nêu đối tượng/hoàn cảnh cụ thể (thường sau
  "trường hợp", "nếu", "đối với", "khi") thuộc scenario; phần hỏi ("bao lâu", "cần gì",
  "ở đâu"...) thuộc text. Ví dụ câu "Nếu nộp hồ sơ bán tài sản gắn liền với đất thuê của
  Nhà nước trả tiền hàng năm thì bao nhiêu ngày có kết quả?" có text="bao nhiêu ngày có
  kết quả" và scenario="bán tài sản gắn liền với đất thuê của Nhà nước trả tiền hàng năm".
- scenario chỉ là mô tả tình huống, không phải điều kiện lọc: không đưa nó vào constraints.
- subject_ref là chỉ số trong subject_mentions; dùng null nếu ý hỏi không có chủ thể rõ ràng.
- Chỉ trích cụm từ người dùng đã viết. Không biến tên thành mã và không chế mã mới.
- Dữ kiện hệ thống kèm theo đã được đối chiếu dữ liệu thật; không được phủ nhận chúng.
- Câu nói về hồ sơ/giấy tờ -> required_documents; mất bao lâu -> processing_time;
  nộp ở đâu/cách nộp -> submission_method; phí/lệ phí -> fee; ai/cơ quan nào xử lý ->
  implementing_agency; căn cứ/văn bản nào -> legal_basis; nhận được gì -> result.
- Câu có nhiều ý phải có đủ requests, không gộp thành general_info.
- Câu thủ tục hành chính ngoài Gia Lai là scope out_of_scope.
- Câu hỏi tư vấn quyền/nghĩa vụ pháp lý trong một tình huống cá nhân (ví dụ hỏi một giao dịch
  có được phép hay không), nhưng không hỏi cách thực hiện một thủ tục hành chính, là scope
  out_of_scope. Không biến câu này thành yêu cầu hồ sơ hoặc điều kiện của một thủ tục gần nghĩa.
- Câu nói về TTHC nhưng chưa rõ hoặc chưa biết hệ thống có dữ liệu hay không là scope tthc
  hoặc unknown; không tự kết luận dữ liệu không tồn tại.
- Không có bộ nhớ hội thoại. "thủ tục này", "cái trên" mà không có chủ thể ngay trong câu
  thì ambiguity.present=true, kind=subject.
- Chỉ trả JSON, không markdown, không giải thích ngoài JSON.
"""


class QuestionParserError(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class ParseResult:
    frame: QuestionFrame
    ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_cached: int = 0
    model: str = ""
    cached: bool = False


_cache: OrderedDict[str, ParseResult] = OrderedDict()
_cache_stats = {"trung": 0, "truot": 0, "goi_mo_hinh": 0}
_client_by_loop: AsyncOpenAI | None = None
_client_loop: asyncio.AbstractEventLoop | None = None
_supports_disable_thinking = True


def enabled() -> bool:
    if not settings.router_model_name:
        return False
    return os.getenv("ROUTER_USE_LLM", "1").strip().lower() not in {"0", "false", "no", "off"}


def cache_enabled() -> bool:
    return os.getenv("ROUTER_CACHE", "1").strip().lower() not in {"0", "false", "no", "off"}


def clear_cache() -> None:
    _cache.clear()
    for key in _cache_stats:
        _cache_stats[key] = 0


def cache_stats() -> dict[str, int]:
    return {**_cache_stats, "kich_thuoc": len(_cache)}


def build_user_message(question: str, resolution: Resolution | None = None) -> str:
    if resolution is None:
        return f"Câu hỏi:\n{question}\n\nDữ kiện đã xác minh: (không có)"

    procedure = resolution.procedure
    verified = {
        "matched_procedure_codes": list(resolution.codes),
        "resolved_procedure": (
            {"code": procedure.code, "name": procedure.name, "method": procedure.method}
            if procedure.code
            else None
        ),
        "legal_documents": list(resolution.documents),
        "entity": resolution.entity,
        "procedure_ambiguous": bool(procedure.ambiguous),
        "entity_ambiguous": bool(resolution.entity_ambiguous),
        "needs_antecedent": bool(resolution.needs_antecedent),
    }
    return (
        f"Câu hỏi:\n{question}\n\n"
        "Dữ kiện đã xác minh (chỉ dùng làm neo, không phải câu trả lời):\n"
        + json.dumps(verified, ensure_ascii=False, separators=(",", ":"))
    )


def build_messages(question: str, resolution: Resolution | None = None) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_message(question, resolution)},
    ]


def _cache_key(messages: list[dict[str, str]]) -> str:
    content = "\0".join(f"{m['role']}\1{m['content']}" for m in messages)
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]


def _client() -> AsyncOpenAI:
    global _client_by_loop, _client_loop
    loop = asyncio.get_running_loop()
    if _client_by_loop is None or _client_loop is not loop:
        _client_by_loop = AsyncOpenAI(
            base_url=settings.qwen_base_url,
            api_key=settings.qwen_api_key,
        )
        _client_loop = loop
    return _client_by_loop


async def close_client() -> None:
    global _client_by_loop, _client_loop
    if _client_by_loop is not None and _client_loop is asyncio.get_running_loop():
        try:
            await _client_by_loop.close()
        except Exception:  # noqa: BLE001
            logger.debug("Khong dong duoc client question parser", exc_info=True)
    _client_by_loop = None
    _client_loop = None


def _unsupported_parameter(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    markers = ("chat_template_kwargs", "enable_thinking", "unexpected", "unrecognized")
    return any(marker in text for marker in markers)


async def _call_model(client: AsyncOpenAI, messages: list[dict[str, str]]):
    global _supports_disable_thinking
    params: dict[str, Any] = {
        "model": settings.router_model_name,
        "messages": messages,
        "temperature": PARSER_TEMPERATURE,
        "response_format": {"type": "json_object"},
    }
    if _supports_disable_thinking:
        params["extra_body"] = TAT_SUY_NGHI
    try:
        return await client.chat.completions.create(**params)
    except Exception as exc:  # noqa: BLE001
        if not _supports_disable_thinking or not _unsupported_parameter(exc):
            raise
        _supports_disable_thinking = False
        params.pop("extra_body", None)
        return await client.chat.completions.create(**params)


def _enum[EnumT](enum_type: type[EnumT], value: Any, path: str) -> EnumT:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise QuestionParserError(f"{path} co gia tri la: {value!r}") from exc


def _object(
    value: Any, keys: set[str], path: str, *, optional: set[str] | None = None
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise QuestionParserError(f"{path} khong phai object")
    required = set(keys)
    allowed = required | set(optional or ())
    actual = set(value)
    if not required <= actual or not actual <= allowed:
        raise QuestionParserError(
            f"{path} sai truong; thieu={sorted(required - actual)}, "
            f"thua={sorted(actual - allowed)}"
        )
    return value


def _text(value: Any, path: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise QuestionParserError(f"{path} khong phai chuoi")
    text = " ".join(value.split())[:MAX_TEXT_CHARS]
    if not text and not allow_empty:
        raise QuestionParserError(f"{path} rong")
    return text


def _scenario_text(value: Any, path: str) -> str:
    """Chuẩn hoá tình huống: gộp khoảng trắng, cắt tối đa 500 ký tự ở ranh giới từ."""
    if not isinstance(value, str):
        raise QuestionParserError(f"{path} khong phai chuoi")
    text = " ".join(value.split())
    if len(text) > MAX_SCENARIO_CHARS:
        text = text[:MAX_SCENARIO_CHARS]
        if " " in text:
            text = text.rsplit(" ", 1)[0]
    return text.rstrip()


def parse_frame(content: str) -> QuestionFrame:
    try:
        raw = json.loads(content)
    except json.JSONDecodeError as exc:
        raise QuestionParserError(f"JSON hong: {str(exc)[:100]}") from exc

    root = _object(
        raw,
        {"schema_version", "scope", "subject_mentions", "requests", "ambiguity"},
        "QuestionFrame",
    )
    if root["schema_version"] != QUESTION_FRAME_SCHEMA_VERSION:
        raise QuestionParserError(f"schema_version khong ho tro: {root['schema_version']!r}")

    raw_subjects = root["subject_mentions"]
    if not isinstance(raw_subjects, list) or len(raw_subjects) > MAX_SUBJECTS:
        raise QuestionParserError("subject_mentions khong hop le")
    subjects: list[SubjectMention] = []
    for index, item in enumerate(raw_subjects):
        obj = _object(item, {"type", "text"}, f"subject_mentions[{index}]")
        subjects.append(
            SubjectMention(
                type=_enum(SubjectType, obj["type"], f"subject_mentions[{index}].type"),
                text=_text(obj["text"], f"subject_mentions[{index}].text"),
            )
        )

    raw_requests = root["requests"]
    if not isinstance(raw_requests, list) or len(raw_requests) > MAX_REQUESTS:
        raise QuestionParserError("requests khong hop le")
    requests: list[QuestionRequest] = []
    for index, item in enumerate(raw_requests):
        obj = _object(
            item,
            {"text", "facet", "operation", "subject_ref", "constraints"},
            f"requests[{index}]",
            optional={"scenario"},
        )
        subject_ref = obj["subject_ref"]
        if subject_ref is not None and (
            isinstance(subject_ref, bool)
            or not isinstance(subject_ref, int)
            or not 0 <= subject_ref < len(subjects)
        ):
            raise QuestionParserError(f"requests[{index}].subject_ref khong hop le")
        raw_constraints = obj["constraints"]
        if not isinstance(raw_constraints, list) or len(raw_constraints) > MAX_CONSTRAINTS:
            raise QuestionParserError(f"requests[{index}].constraints khong hop le")
        constraints: list[RequestConstraint] = []
        for constraint_index, item_constraint in enumerate(raw_constraints):
            constraint = _object(
                item_constraint,
                {"type", "text"},
                f"requests[{index}].constraints[{constraint_index}]",
            )
            constraints.append(
                RequestConstraint(
                    type=_enum(
                        ConstraintType,
                        constraint["type"],
                        f"requests[{index}].constraints[{constraint_index}].type",
                    ),
                    text=_text(
                        constraint["text"],
                        f"requests[{index}].constraints[{constraint_index}].text",
                    ),
                )
            )
        requests.append(
            QuestionRequest(
                text=_text(obj["text"], f"requests[{index}].text"),
                facet=_enum(Facet, obj["facet"], f"requests[{index}].facet"),
                operation=_enum(
                    RequestOperation, obj["operation"], f"requests[{index}].operation"
                ),
                subject_ref=subject_ref,
                constraints=constraints,
                scenario=_scenario_text(
                    obj.get("scenario", ""), f"requests[{index}].scenario"
                ),
            )
        )

    ambiguity_raw = _object(root["ambiguity"], {"present", "kind", "reason"}, "ambiguity")
    if not isinstance(ambiguity_raw["present"], bool):
        raise QuestionParserError("ambiguity.present khong phai boolean")
    ambiguity = AmbiguityInfo(
        present=ambiguity_raw["present"],
        kind=_enum(AmbiguityKind, ambiguity_raw["kind"], "ambiguity.kind"),
        reason=_text(ambiguity_raw["reason"], "ambiguity.reason", allow_empty=True),
    )
    if not ambiguity["present"] and ambiguity["kind"] is not AmbiguityKind.NONE:
        raise QuestionParserError("ambiguity.kind phai la none khi present=false")
    if ambiguity["present"] and ambiguity["kind"] is AmbiguityKind.NONE:
        raise QuestionParserError("ambiguity.kind khong duoc la none khi present=true")

    return QuestionFrame(
        schema_version=QUESTION_FRAME_SCHEMA_VERSION,
        scope=_enum(QuestionScope, root["scope"], "scope"),
        subject_mentions=subjects,
        requests=requests,
        ambiguity=ambiguity,
    )


def _cached_tokens(usage: Any) -> int:
    details = getattr(usage, "prompt_tokens_details", None) if usage is not None else None
    value = (
        details.get("cached_tokens")
        if isinstance(details, dict)
        else getattr(details, "cached_tokens", 0)
    )
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


async def parse_question(
    question: str,
    resolution: Resolution | None = None,
    *,
    timeout: float = PARSER_TIMEOUT_S,
) -> ParseResult:
    if not settings.router_model_name:
        raise QuestionParserError("chua cau hinh ROUTER_MODEL_NAME")

    messages = build_messages(question, resolution)
    key = _cache_key(messages)
    use_cache = cache_enabled()
    if use_cache:
        if key in _cache:
            _cache_stats["trung"] += 1
            _cache.move_to_end(key)
            return replace(
                _cache[key], ms=0, tokens_in=0, tokens_out=0, tokens_cached=0, cached=True
            )
        _cache_stats["truot"] += 1

    started = time.perf_counter()
    try:
        response = await asyncio.wait_for(_call_model(_client(), messages), timeout=timeout)
    except TimeoutError as exc:
        raise QuestionParserError(f"qua thoi gian cho {timeout:.0f} s") from exc
    except Exception as exc:  # noqa: BLE001
        raise QuestionParserError(
            f"goi mo hinh loi: {type(exc).__name__}: {str(exc)[:120]}"
        ) from exc

    try:
        content = (response.choices[0].message.content or "").strip()
    except (AttributeError, IndexError, TypeError) as exc:
        raise QuestionParserError("phản hồi mô hình không có message hợp lệ") from exc
    if not content:
        raise QuestionParserError("mo hinh tra noi dung rong")
    frame = parse_frame(content)
    usage = getattr(response, "usage", None)
    result = ParseResult(
        frame=frame,
        ms=int((time.perf_counter() - started) * 1000),
        tokens_in=int(getattr(usage, "prompt_tokens", 0) or 0),
        tokens_out=int(getattr(usage, "completion_tokens", 0) or 0),
        tokens_cached=_cached_tokens(usage),
        model=settings.router_model_name,
    )
    _cache_stats["goi_mo_hinh"] += 1
    if use_cache:
        _cache[key] = result
        _cache.move_to_end(key)
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)
    return result


def to_router_decision(
    result: ParseResult,
    resolution: Resolution,
    groundings: list[SubjectGrounding] | None = None,
) -> RouterDecision:
    """Adapter tạm thời sang ba nhánh hiện có, chờ RetrievalPlan thay thế.

    Khi có ``groundings``, quyết định hỏi lại dựa trên **kết quả grounding** (có candidate
    thật) thay vì cờ mơ hồ của resolver. Đây là điểm nối của giai đoạn 3 vào luồng chính.
    """
    frame = result.frame
    grounded = groundings or []
    grounded_by_index = {item.index: item for item in grounded}
    unresolved_refs = grounding.unresolved_subject_refs(frame, grounded)
    if unresolved_refs:
        request_index = unresolved_refs[0]
        request = frame["requests"][request_index]
        item = grounded_by_index.get(int(request["subject_ref"]))
        if item is not None and item.status == "ambiguous":
            return RouterDecision(
                signal=BranchSignal.CLARIFY.value,
                reason=f"grounding mơ hồ: {item.note or item.mention}",
                clarify=ClarifyInfo(
                    question="Bạn muốn tra cứu đối tượng nào?",
                    options=[
                        {
                            "value": str(option.get("code") or ""),
                            "label": str(option.get("name") or option.get("code") or ""),
                            "hint": f"mã {option.get('code') or ''}",
                        }
                        for option in item.alternatives
                    ],
                ),
                source="llm",
                ms=result.ms,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                tokens_cached=result.tokens_cached,
                model=result.model,
                cached=result.cached,
            )
        if item is not None and item.status == "context_required":
            return RouterDecision(
                signal=BranchSignal.CLARIFY.value,
                reason="mention cần tiền ngữ nhưng hệ thống chưa có conversation context",
                clarify=ClarifyInfo(
                    question=(
                        "Bạn vui lòng nêu mã hoặc tên thủ tục cần tra cứu "
                        '(ví dụ: 1.001699 hoặc "cấp giấy xác nhận khuyết tật").'
                    ),
                    options=[],
                ),
                source="llm",
                ms=result.ms,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                tokens_cached=result.tokens_cached,
                model=result.model,
                cached=result.cached,
            )
        return RouterDecision(
            signal=BranchSignal.EMPTY.value,
            reason=f"không định danh được chủ thể của ý hỏi thứ {request_index + 1}",
            source="llm",
            ms=result.ms,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            tokens_cached=result.tokens_cached,
            model=result.model,
            cached=result.cached,
        )

    procedure_resolved = next(
        (item for item in grounded if item.type == "procedure" and item.status == "resolved"),
        None,
    )
    referenced_codes = {
        item.code
        for request in frame["requests"]
        if request["subject_ref"] is not None
        for item in [grounded_by_index.get(int(request["subject_ref"]))]
        if item is not None and item.type == "procedure" and item.status == "resolved" and item.code
    }
    if len(referenced_codes) > 1:
        return RouterDecision(
            signal=BranchSignal.EMPTY.value,
            reason=(
                "câu hỏi có nhiều thủ tục; luồng truy xuất hiện tại chưa hỗ trợ "
                "tách riêng từng thủ tục"
            ),
            source="llm",
            ms=result.ms,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            tokens_cached=result.tokens_cached,
            model=result.model,
            cached=result.cached,
        )

    direct_code = str(resolution.codes[0]) if resolution.codes else ""
    subject_code = direct_code or (procedure_resolved.code if procedure_resolved else resolution.ma)
    parts = tuple(
        PartSpec(text=request["text"], need=(request["facet"].value,))
        for request in frame["requests"]
        if request["facet"].value in CONTENT_FACETS
    )
    common = {
        "source": "llm",
        "ms": result.ms,
        "tokens_in": result.tokens_in,
        "tokens_out": result.tokens_out,
        "tokens_cached": result.tokens_cached,
        "model": result.model,
        "parts": parts,
        "subjects": (subject_code,) if subject_code else (),
        "cached": result.cached,
    }

    if resolution.needs_antecedent:
        return RouterDecision(
            signal=BranchSignal.CLARIFY.value,
            reason="câu cần tiền ngữ nhưng hệ thống chưa có conversation context",
            clarify=ClarifyInfo(question="Bạn muốn hỏi thủ tục nào?", options=[]),
            **common,
        )
    if procedure_resolved is None and (
        resolution.procedure.ambiguous
        or resolution.entity_ambiguous
        or len(resolution.documents) > 1
    ):
        return RouterDecision(
            signal=BranchSignal.CLARIFY.value,
            reason="dữ kiện định danh có nhiều ứng viên",
            clarify=ClarifyInfo(question="Bạn muốn hỏi đối tượng nào?", options=[]),
            **common,
        )
    if frame["scope"] in {QuestionScope.OUT_OF_SCOPE, QuestionScope.SMALLTALK}:
        return RouterDecision(
            signal=BranchSignal.EMPTY.value,
            reason=f"QuestionFrame xác định scope={frame['scope'].value}",
            **common,
        )
    # Mơ hồ về **subject** mà grounding đã giải quyết được thì không hỏi lại nữa — hỏi lại lúc
    # đó chỉ làm mất thông tin đã có. Mơ hồ về request/constraint vẫn phải hỏi.
    subject_ambiguity_handled = (
        procedure_resolved is not None
        and frame["ambiguity"]["kind"] == AmbiguityKind.SUBJECT
    )
    if frame["ambiguity"]["present"] and not subject_ambiguity_handled:
        return RouterDecision(
            signal=BranchSignal.CLARIFY.value,
            reason=frame["ambiguity"]["reason"] or "QuestionFrame xác định câu hỏi mơ hồ",
            clarify=ClarifyInfo(
                question="Bạn vui lòng nêu rõ thủ tục cần tra cứu.",
                options=[],
            ),
            **common,
        )

    operations = {request["operation"] for request in frame["requests"]}
    if operations & {RequestOperation.COMPARE, RequestOperation.RANK}:
        return RouterDecision(
            signal=BranchSignal.EMPTY.value,
            reason="phép so sánh/xếp hạng chưa được hỗ trợ",
            **common,
        )

    facets = {request["facet"].value for request in frame["requests"]}
    if Facet.RELATED_PROCEDURES.value in facets:
        return RouterDecision(
            signal=BranchSignal.EMPTY.value,
            reason="quan hệ thủ tục liên quan chưa có template dữ liệu tin cậy",
            **common,
        )
    if RequestOperation.COUNT in operations and not facets & GRAPH_FACETS:
        return RouterDecision(
            signal=BranchSignal.EMPTY.value,
            reason="phép đếm này chưa có capability tương ứng",
            **common,
        )
    if facets & GRAPH_FACETS:
        branch = Branch.GRAPH
    elif facets == {Facet.GENERAL_INFO.value} and resolution.ma:
        branch = Branch.FACT_LOOKUP
    else:
        branch = Branch.HYBRID
    return RouterDecision(
        branch=branch.value,
        signal=BranchSignal.OK.value,
        reason=f"QuestionFrame -> {branch.value}: {', '.join(sorted(facets)) or 'unknown'}",
        **common,
    )


__all__ = [
    "CACHE_MAX",
    "PARSER_TIMEOUT_S",
    "ParseResult",
    "QuestionParserError",
    "SYSTEM_PROMPT",
    "build_messages",
    "build_user_message",
    "cache_stats",
    "clear_cache",
    "close_client",
    "enabled",
    "parse_frame",
    "parse_question",
    "to_router_decision",
]
