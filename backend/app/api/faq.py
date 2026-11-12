from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import text

from backend.app.db.postgres import engine

router = APIRouter(prefix="/faq", tags=["faq"])


#: 9 khía cạnh dữ liệu gốc + ``none`` cho câu hỏi ngoài phạm vi TTHC.
FAQ_INTENTS: dict[str, str] = {
    "required_documents": "Hồ sơ, giấy tờ",
    "steps": "Trình tự thực hiện",
    "submission_method": "Cách nộp hồ sơ",
    "processing_time": "Thời hạn giải quyết",
    "fee": "Phí, lệ phí",
    "result": "Kết quả nhận được",
    "legal_basis": "Căn cứ pháp lý",
    "requirements": "Điều kiện thực hiện",
    "general_info": "Thông tin chung",
    "none": "Không",
}

#: QuestionFrame facet → intent đang dùng trong bảng ``faq``.
FACET_TO_FAQ_INTENT: dict[str, str] = {
    "required_documents": "required_documents",
    "steps": "steps",
    "submission_method": "submission_method",
    "receiving_agency": "submission_method",
    "processing_time": "processing_time",
    "fee": "fee",
    "result": "result",
    "result_delivery": "result",
    "legal_basis": "legal_basis",
    "requirements": "requirements",
    "general_info": "general_info",
}


class FaqIntent(BaseModel):
    value: str
    label: str


class FaqSuggestion(BaseModel):
    id: str
    question: str


class FaqSuggestionList(BaseModel):
    items: list[FaqSuggestion]


@router.get("/intents", response_model=list[FaqIntent])
def list_faq_intents() -> list[FaqIntent]:
    return [
        FaqIntent(value=value, label=label)
        for value, label in FAQ_INTENTS.items()
    ]


@router.get("/suggestions", response_model=FaqSuggestionList)
def list_faq_suggestions(
    limit: int = Query(default=3, ge=1, le=20),
) -> FaqSuggestionList:
    """FAQ toàn cục dùng cho màn hình chào.

    Không trả FAQ gắn thủ tục ở đây; các FAQ đó chỉ xuất hiện dưới dạng
    gợi ý sau câu trả lời RAG.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT faq_id::text AS id, question
                FROM faq
                WHERE status = 'ready'
                  AND NULLIF(procedure_code, '') IS NULL
                ORDER BY priority DESC, updated_at DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).mappings().all()

    return FaqSuggestionList(
        items=[
            FaqSuggestion(id=row["id"], question=row["question"])
            for row in rows
        ]
    )


def _normalize_question(question: str) -> str:
    return " ".join(question.casefold().split())


def _is_placeholder_answer(answer: str) -> bool:
    normalized = _normalize_question(answer)
    return normalized in {"", "không biết", "khong biet", "chưa có dữ liệu", "chua co du lieu"}


def suggest_ready_faqs(
    procedure_code: str | None,
    *,
    facets: Iterable[str] = (),
    exclude_question: str = "",
    exclude_questions: Iterable[str] = (),
    limit: int = 3,
) -> list[dict[str, str]]:
    """FAQ gợi ý theo thủ tục hoặc FAQ toàn cục, bỏ facet đã hỏi và câu trùng.

    Có ``procedure_code``: lọc FAQ cùng thủ tục.
    Không có ``procedure_code``: lấy FAQ không gắn thủ tục, ưu tiên priority
    và cập nhật gần nhất. Không dùng so khớp token.
    """
    if limit <= 0:
        return []

    excluded_intents = {
        FACET_TO_FAQ_INTENT.get(str(facet), str(facet))
        for facet in facets
        if str(facet).strip()
    }
    target = _normalize_question(exclude_question)
    excluded_questions = {
        _normalize_question(item)
        for item in exclude_questions
        if _normalize_question(item)
    }
    if target:
        excluded_questions.add(target)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT faq_id::text AS id, question, answer, intent
                  FROM faq
                 WHERE status = 'ready'
                   AND (
                        (CAST(:procedure_code AS VARCHAR) IS NULL
                         AND NULLIF(procedure_code, '') IS NULL)
                        OR procedure_code = CAST(:procedure_code AS VARCHAR)
                   )
                 ORDER BY priority DESC, updated_at DESC
                """
            ),
            {"procedure_code": procedure_code},
        ).mappings().all()

    candidates: list[dict[str, str]] = []
    seen_questions: set[str] = set()
    for row in rows:
        question = str(row["question"] or "").strip()
        normalized = _normalize_question(question)
        intent = str(row["intent"] or "")
        if not question or not normalized or normalized in seen_questions:
            continue
        if normalized in excluded_questions or intent in excluded_intents:
            continue
        if _is_placeholder_answer(str(row["answer"] or "")):
            continue
        seen_questions.add(normalized)
        candidates.append(
            {"id": str(row["id"]), "question": question, "intent": intent}
        )

    selected: list[dict[str, str]] = []
    used_intents: set[str] = set()
    for item in candidates:
        if item["intent"] in used_intents:
            continue
        selected.append({"id": item["id"], "question": item["question"]})
        used_intents.add(item["intent"])
        if len(selected) >= limit:
            return selected

    for item in candidates:
        if any(chosen["id"] == item["id"] for chosen in selected):
            continue
        selected.append({"id": item["id"], "question": item["question"]})
        if len(selected) >= limit:
            break
    return selected


def find_ready_faq_by_id(faq_id: UUID) -> dict[str, Any] | None:
    """Lấy FAQ đã duyệt theo ID người dùng đã chọn.

    Không dùng để tự khớp câu hỏi gõ tay. Luôn đọc lại từ DB và kiểm tra
    ``status = 'ready'``; client không bao giờ cung cấp nội dung trả lời.
    """
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT f.faq_id::text AS id,
                       f.question,
                       f.answer,
                       f.intent,
                       f.procedure_code,
                       f.procedure_name,
                       COALESCE(f.detail_url, p.detail_url) AS detail_url
                  FROM faq AS f
                  LEFT JOIN procedures AS p
                    ON p.procedure_code = f.procedure_code
                 WHERE f.faq_id = :faq_id
                   AND f.status = 'ready'
                """
            ),
            {"faq_id": faq_id},
        ).mappings().first()

    return dict(row) if row is not None else None