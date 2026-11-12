"""FAQ toàn cục: collection Qdrant riêng và auto-match trước RAG.

Chỉ FAQ có ``status = 'ready'`` và ``procedure_code`` rỗng mới được đưa vào
collection ``faq_global``. Câu trả lời không nằm trong Qdrant; sau khi tìm được
``faq_id``, luôn đọc lại PostgreSQL để lấy nội dung mới nhất.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from sqlalchemy import text

from backend.app.config import settings
from backend.app.db.postgres import engine
from backend.app.rag import embeddings

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "faq_global"
DEFAULT_THRESHOLD = 0.66
DEFAULT_MARGIN = 0.05


def collection_name() -> str:
    return settings.qdrant_collection_faq_global or DEFAULT_COLLECTION


def _client() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_host,
        api_key=settings.qdrant_api_key or None,
        timeout=10,
    )


def _normalize(value: str) -> str:
    text = str(value or "").casefold().strip()
    text = re.sub(r"[^\w\s]", " ", text)
    return " ".join(text.split())


def _global_rows() -> list[dict[str, Any]]:
    with engine.connect() as conn:
        return [
            dict(row)
            for row in conn.execute(
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
                     WHERE f.status = 'ready'
                       AND NULLIF(f.procedure_code, '') IS NULL
                    """
                )
            ).mappings()
        ]


def ensure_collection(*, recreate: bool = False) -> None:
    client = _client()
    try:
        exists = client.collection_exists(collection_name())
        if recreate and exists:
            client.delete_collection(collection_name())
            exists = False
        if not exists:
            client.create_collection(
                collection_name=collection_name(),
                vectors_config=qdrant_models.VectorParams(
                    size=settings.embedding_dim,
                    distance=qdrant_models.Distance.COSINE,
                ),
            )
    finally:
        client.close()


async def index_global_faqs(*, recreate: bool = True) -> int:
    """Reindex toàn bộ FAQ toàn cục vào Qdrant."""
    rows = _global_rows()
    ensure_collection(recreate=recreate)
    if not rows:
        return 0

    points: list[qdrant_models.PointStruct] = []
    for row in rows:
        question = str(row.get("question") or "").strip()
        if not question:
            continue
        vector = await embeddings.embed(question)
        points.append(
            qdrant_models.PointStruct(
                id=str(row["id"]),
                vector=vector,
                payload={
                    "faq_id": str(row["id"]),
                    "scope": "global",
                    "question": question,
                    "status": "ready",
                },
            )
        )

    client = _client()
    try:
        if points:
            client.upsert(collection_name=collection_name(), points=points)
        else:
            ensure_collection(recreate=True)
    finally:
        client.close()
    return len(points)


def _read_by_id(faq_id: str) -> dict[str, Any] | None:
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
                   AND NULLIF(f.procedure_code, '') IS NULL
                """
            ),
            {"faq_id": faq_id},
        ).mappings().first()
    return dict(row) if row is not None else None


async def find_global_faq(
    question: str,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    margin: float = DEFAULT_MARGIN,
) -> dict[str, Any] | None:
    """Trả FAQ toàn cục khớp câu hỏi; lỗi Qdrant thì trả None để đi RAG."""
    query = _normalize(question)
    if not query:
        return None

    # Exact match trước, không cần embedding.
    rows = _global_rows()
    for row in rows:
        if _normalize(str(row.get("question") or "")) == query:
            row["match"] = "exact"
            return row

    if not embeddings.enabled():
        return None

    if not settings.faq_global_semantic_enabled:
        return None

    try:
        vector = await embeddings.embed(question)
        client = _client()
        try:
            if not client.collection_exists(collection_name()):
                return None
            result = client.query_points(
                collection_name=collection_name(),
                query=vector,
                limit=3,
                with_payload=True,
            )
        finally:
            client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("FAQ toàn cục Qdrant lỗi: %s", exc)
        return None

    points = list(result.points or [])
    if not points:
        return None
    top = points[0]
    score = float(top.score or 0.0)
    if score < threshold:
        return None
    if len(points) > 1:
        second = float(points[1].score or 0.0)
        if score - second < margin:
            return None

    payload = top.payload or {}
    faq_id = str(payload.get("faq_id") or top.id or "")
    faq = _read_by_id(faq_id)
    if faq is None:
        return None
    faq["match"] = "semantic"
    faq["score"] = score
    return faq
