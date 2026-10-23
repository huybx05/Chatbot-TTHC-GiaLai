from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from elasticsearch import Elasticsearch, helpers
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sqlalchemy import create_engine, text

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from backend.app.config import settings  # noqa: E402

EMBEDDING_API_MAX_BATCH_SIZE = 20


def stable_point_id(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, value))


def embedding_batch_size() -> int:
    return min(settings.embedding_batch_size, EMBEDDING_API_MAX_BATCH_SIZE)


def make_pg_engine():
    url = settings.database_url.strip()
    if not url:
        url = (
            f"postgresql+psycopg://{settings.database_user}:{settings.database_password}"
            f"@{settings.database_host}:{settings.database_port}/{settings.database_db}"
        )
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    return create_engine(url, pool_pre_ping=True)


def fetch_chunks(limit: int | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT
            s.section_id,
            s.procedure_code,
            p.procedure_name,
            p.domain_group,
            p.source_field,
            p.canonical_field,
            s.section_type,
            s.title,
            s.content,
            s.chunk_order,
            s.detail_url
        FROM procedure_sections s
        JOIN procedures p ON p.procedure_code = s.procedure_code
        ORDER BY s.procedure_code, s.chunk_order
    """
    params: dict[str, Any] = {}
    if limit:
        sql += " LIMIT :limit"
        params["limit"] = limit

    engine = make_pg_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def fetch_faqs(limit: int | None = None) -> list[dict[str, Any]]:
    sql = """
        SELECT
            faq_id::text,
            procedure_code,
            procedure_name,
            domain_group,
            source_field,
            detail_url,
            question,
            answer,
            intent,
            source_section,
            source_text,
            tags,
            confidence,
            status,
            priority
        FROM faq
        WHERE status = 'ready'
        ORDER BY priority DESC, procedure_code, created_at
    """
    params: dict[str, Any] = {}
    if limit:
        sql += " LIMIT :limit"
        params["limit"] = limit

    engine = make_pg_engine()
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(row) for row in rows]


def make_es_client() -> Elasticsearch:
    basic_auth = None
    if settings.elastic_user and settings.elastic_password:
        basic_auth = (settings.elastic_user, settings.elastic_password)

    return Elasticsearch(
        settings.elasticsearch_host,
        basic_auth=basic_auth,
        request_timeout=settings.elastic_request_timeout,
    )


def ensure_es_index(es: Elasticsearch, recreate: bool = False) -> None:
    index = settings.elasticsearch_index or "chatbot_tthc"

    if recreate and es.indices.exists(index=index):
        es.indices.delete(index=index)

    if es.indices.exists(index=index):
        return

    es.indices.create(
        index=index,
        mappings={
            "properties": {
                "section_id": {"type": "keyword"},
                "procedure_code": {"type": "keyword"},
                "procedure_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "domain_group": {"type": "keyword"},
                "source_field": {"type": "keyword"},
                "canonical_field": {"type": "keyword"},
                "section_type": {"type": "keyword"},
                "title": {"type": "text"},
                "content": {"type": "text"},
                "chunk_order": {"type": "integer"},
                "detail_url": {"type": "keyword"},
            }
        },
    )


def index_elasticsearch(chunks: list[dict[str, Any]], recreate: bool = False) -> None:
    es = make_es_client()
    ensure_es_index(es, recreate=recreate)

    index = settings.elasticsearch_index or "chatbot_tthc"

    actions = [
        {
            "_op_type": "index",
            "_index": index,
            "_id": chunk["section_id"],
            "_source": chunk,
        }
        for chunk in chunks
    ]

    helpers.bulk(es, actions, chunk_size=500)
    es.indices.refresh(index=index)


def make_embedding_client() -> OpenAI:
    return OpenAI(
        base_url=settings.qwen_base_url,
        api_key=settings.qwen_api_key,
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    client = make_embedding_client()
    response = client.embeddings.create(
        model=settings.embedding_model_name,
        input=texts,
    )
    return [item.embedding for item in response.data]


def make_qdrant_client() -> QdrantClient:
    return QdrantClient(
        url=settings.qdrant_host,
        api_key=settings.qdrant_api_key or None,
    )


def ensure_qdrant_collection(
    qdrant: QdrantClient,
    collection: str,
    recreate: bool = False,
) -> None:
    existing = {item.name for item in qdrant.get_collections().collections}

    if recreate and collection in existing:
        qdrant.delete_collection(collection_name=collection)
        existing.remove(collection)

    if collection in existing:
        return

    qdrant.create_collection(
        collection_name=collection,
        vectors_config=VectorParams(
            size=settings.embedding_dim,
            distance=Distance.COSINE,
        ),
    )


def index_qdrant_chunks(chunks: list[dict[str, Any]], recreate: bool = False) -> None:
    qdrant = make_qdrant_client()
    collection = settings.qdrant_collection_semantic or "semantic_search"
    ensure_qdrant_collection(qdrant, collection=collection, recreate=recreate)

    batch_size = embedding_batch_size()

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        texts = [chunk["content"] for chunk in batch]
        vectors = embed_texts(texts)

        points = []
        for chunk, vector in zip(batch, vectors, strict=True):
            payload = {
                "type": "chunk",
                "section_id": chunk["section_id"],
                "procedure_code": chunk["procedure_code"],
                "procedure_name": chunk["procedure_name"],
                "domain_group": chunk["domain_group"],
                "source_field": chunk["source_field"],
                "canonical_field": chunk["canonical_field"],
                "section_type": chunk["section_type"],
                "title": chunk["title"],
                "content": chunk["content"],
                "chunk_order": chunk["chunk_order"],
                "detail_url": chunk["detail_url"],
            }

            points.append(
                PointStruct(
                    id=stable_point_id(f"chunk:{chunk['section_id']}"),
                    vector=vector,
                    payload=payload,
                )
            )

        qdrant.upsert(collection_name=collection, points=points)
        print(f"Indexed chunk vectors: {min(start + batch_size, len(chunks))}/{len(chunks)}")
        time.sleep(0.5)


def faq_embedding_text(faq: dict[str, Any]) -> str:
    tags = ", ".join(faq.get("tags") or [])
    return "\n".join(
        [
            f"Câu hỏi: {faq['question']}",
            f"Thủ tục: {faq.get('procedure_name') or ''}",
            f"Lĩnh vực: {faq.get('source_field') or ''}",
            f"Từ khóa: {tags}",
        ]
    )


def index_qdrant_faqs(faqs: list[dict[str, Any]], recreate: bool = False) -> None:
    qdrant = make_qdrant_client()
    collection = settings.qdrant_collection_faq or "faq_search"
    ensure_qdrant_collection(qdrant, collection=collection, recreate=recreate)

    batch_size = embedding_batch_size()

    for start in range(0, len(faqs), batch_size):
        batch = faqs[start : start + batch_size]
        texts = [faq_embedding_text(faq) for faq in batch]
        vectors = embed_texts(texts)

        points = []
        for faq, vector in zip(batch, vectors, strict=True):
            payload = {
                "type": "faq",
                "faq_id": faq["faq_id"],
                "procedure_code": faq["procedure_code"],
                "procedure_name": faq["procedure_name"],
                "domain_group": faq["domain_group"],
                "source_field": faq["source_field"],
                "detail_url": faq["detail_url"],
                "question": faq["question"],
                "answer": faq["answer"],
                "intent": faq["intent"],
                "source_section": faq["source_section"],
                "source_text": faq["source_text"],
                "tags": faq["tags"],
                "confidence": float(faq["confidence"]) if faq["confidence"] is not None else None,
                "status": faq["status"],
                "priority": faq["priority"],
            }

            points.append(
                PointStruct(
                    id=stable_point_id(f"faq:{faq['faq_id']}"),
                    vector=vector,
                    payload=payload,
                )
            )

        qdrant.upsert(collection_name=collection, points=points)
        print(f"Indexed FAQ vectors: {min(start + batch_size, len(faqs))}/{len(faqs)}")
        time.sleep(0.5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target",
        choices=["all", "elasticsearch", "qdrant-chunks", "qdrant-faqs"],
        default="all",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--recreate", action="store_true")
    args = parser.parse_args()

    if args.target in {"all", "elasticsearch"}:
        chunks = fetch_chunks(limit=args.limit)
        print(f"Loaded chunks from PostgreSQL: {len(chunks)}")
        index_elasticsearch(chunks, recreate=args.recreate)
        print("Elasticsearch indexed")

    if args.target in {"all", "qdrant-chunks"}:
        chunks = fetch_chunks(limit=args.limit)
        print(f"Loaded chunks from PostgreSQL: {len(chunks)}")
        index_qdrant_chunks(chunks, recreate=args.recreate)
        print("Qdrant chunk collection indexed")

    if args.target in {"all", "qdrant-faqs"}:
        faqs = fetch_faqs(limit=args.limit)
        print(f"Loaded ready FAQ from PostgreSQL: {len(faqs)}")
        index_qdrant_faqs(faqs, recreate=args.recreate)
        print("Qdrant FAQ collection indexed")


if __name__ == "__main__":
    main()
