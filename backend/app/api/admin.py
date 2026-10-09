"""Read-only admin endpoints for the monitoring UI."""

from typing import Any

from elasticsearch import Elasticsearch
from fastapi import APIRouter, Query
from qdrant_client import QdrantClient
from sqlalchemy import text

from backend.app.config import settings
from backend.app.db.neo4j import driver
from backend.app.db.postgres import engine

router = APIRouter(tags=["admin"])


def _ok(**extra: Any) -> dict[str, Any]:
    return {"ready": True, "error": "", **extra}


def _fail(exc: Exception, **extra: Any) -> dict[str, Any]:
    return {"ready": False, "error": str(exc), **extra}


def _make_es_client() -> Elasticsearch:
    basic_auth = None
    if settings.elastic_user and settings.elastic_password:
        basic_auth = (settings.elastic_user, settings.elastic_password)
    return Elasticsearch(
        settings.elasticsearch_host,
        basic_auth=basic_auth,
        request_timeout=settings.elastic_request_timeout,
    )


def _make_qdrant_client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_host, api_key=settings.qdrant_api_key or None)


@router.get("/system/status")
def system_status() -> dict[str, Any]:
    services: dict[str, Any] = {"api": _ok()}

    try:
        with engine.connect() as conn:
            counts = conn.execute(
                text(
                    """
                    SELECT
                      (SELECT COUNT(*) FROM procedures)::int AS procedures,
                      (SELECT COUNT(*) FROM procedure_sections)::int AS sections,
                      (SELECT COUNT(*) FROM faq)::int AS faq,
                      (SELECT COUNT(*) FROM faq WHERE status = 'ready')::int AS faq_ready
                    """
                )
            ).mappings().one()
        services["postgresql"] = _ok(counts=dict(counts))
    except Exception as exc:  # pragma: no cover - status endpoint must not crash UI
        services["postgresql"] = _fail(exc, counts={})

    try:
        with driver.session(database=settings.neo4j_database) as session:
            counts = session.run(
                """
                MATCH (n)
                WITH count(n) AS nodes
                MATCH ()-[r]->()
                RETURN nodes, count(r) AS relationships
                """
            ).single()
        services["neo4j"] = _ok(counts=dict(counts) if counts else {})
    except Exception as exc:  # pragma: no cover
        services["neo4j"] = _fail(exc, counts={})

    try:
        es = _make_es_client()
        index = settings.elasticsearch_index or "chatbot_tthc"
        exists = bool(es.indices.exists(index=index))
        documents = int(es.count(index=index)["count"]) if exists else 0
        services["elasticsearch"] = _ok(index=index, exists=exists, documents=documents)
    except Exception as exc:  # pragma: no cover
        services["elasticsearch"] = _fail(
            exc,
            index=settings.elasticsearch_index or "chatbot_tthc",
            exists=False,
            documents=0,
        )

    try:
        qdrant = _make_qdrant_client()
        names = {collection.name for collection in qdrant.get_collections().collections}
        semantic = settings.qdrant_collection_semantic or "semantic_search"
        faq = settings.qdrant_collection_faq or "faq_search"

        def collection_count(name: str) -> dict[str, Any]:
            if name not in names:
                return {"exists": False, "points": 0}
            return {"exists": True, "points": int(qdrant.count(name, exact=True).count)}

        services["qdrant"] = _ok(
            collections={
                "semantic": {"name": semantic, **collection_count(semantic)},
                "faq": {"name": faq, **collection_count(faq)},
            }
        )
    except Exception as exc:  # pragma: no cover
        services["qdrant"] = _fail(exc, collections={})

    return {"services": services}


@router.get("/procedures")
def list_procedures(q: str = "", limit: int = Query(default=50, le=200)) -> dict[str, Any]:
    sql = text(
        """
        SELECT
            p.procedure_code AS code,
            p.procedure_name AS name,
            p.domain_group,
            p.source_field,
            p.canonical_field,
            p.administrative_levels,
            p.issuing_agency,
            p.status,
            p.detail_url,
            p.updated_at,
            COUNT(s.section_id)::int AS section_count
        FROM procedures p
        LEFT JOIN procedure_sections s ON s.procedure_code = p.procedure_code
        WHERE (:q = '' OR p.procedure_code ILIKE :pattern OR p.procedure_name ILIKE :pattern)
        GROUP BY p.procedure_code
        ORDER BY p.procedure_code
        LIMIT :limit
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"q": q, "pattern": f"%{q}%", "limit": limit}).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.get("/procedures/{code}")
def get_procedure(code: str) -> dict[str, Any]:
    sql = text(
        """
        SELECT
            p.*,
            COALESCE(a.agencies, '[]'::json) AS agencies
        FROM procedures p
        LEFT JOIN LATERAL (
            SELECT json_agg(
                json_build_object(
                    'agency_name', agency_name,
                    'role', role,
                    'is_inferred', is_inferred
                )
                ORDER BY role, agency_name
            ) AS agencies
            FROM procedure_agencies
            WHERE procedure_code = p.procedure_code
        ) a ON TRUE
        WHERE p.procedure_code = :code
        LIMIT 1
        """
    )
    with engine.connect() as conn:
        row = conn.execute(sql, {"code": code}).mappings().first()
    return {"item": dict(row) if row else None}


@router.get("/procedures/{code}/sections")
def list_sections(code: str) -> dict[str, Any]:
    sql = text(
        """
        SELECT
            section_id,
            section_id AS chunk_id,
            section_type,
            title,
            content,
            chunk_order,
            detail_url,
            created_at
        FROM procedure_sections
        WHERE procedure_code = :code
        ORDER BY chunk_order, section_type
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"code": code}).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.get("/qa")
def list_qa(procedure_code: str = "", limit: int = Query(default=100, le=500)) -> dict[str, Any]:
    sql = text(
        """
        SELECT
            faq_id::text AS id,
            faq_id::text AS faq_id,
            procedure_code,
            procedure_name,
            domain_group,
            source_field,
            detail_url,
            source_file,
            question,
            answer,
            intent,
            source_section,
            source_text,
            tags,
            confidence,
            COALESCE(confidence, 0)::float AS score,
            status,
            priority,
            hit_count,
            last_used_at,
            created_by,
            reviewed_by,
            created_at,
            updated_at
        FROM faq
        WHERE (:procedure_code = '' OR procedure_code = :procedure_code)
        ORDER BY priority DESC, confidence DESC NULLS LAST, created_at DESC
        """
    )
    with engine.connect() as conn:
        rows = conn.execute(
            sql,
            {"procedure_code": procedure_code, "limit": limit},
        ).mappings().all()
    return {"items": [dict(row) for row in rows]}


@router.post("/qa/approve-all")
def approve_all_qa(procedure_code: str = "") -> dict[str, Any]:
    sql = text(
        """
        UPDATE faq
        SET status = 'ready',
            reviewed_by = COALESCE(reviewed_by, 'admin')
        WHERE status <> 'ready'
          AND (:procedure_code = '' OR procedure_code = :procedure_code)
        """
    )
    with engine.begin() as conn:
        result = conn.execute(sql, {"procedure_code": procedure_code})
    return {"updated": result.rowcount or 0}


@router.post("/qa/{faq_id}/approve")
def approve_qa(faq_id: str) -> dict[str, Any]:
    sql = text(
        """
        UPDATE faq
        SET status = 'ready',
            reviewed_by = COALESCE(reviewed_by, 'admin')
        WHERE faq_id = :faq_id
        """
    )
    with engine.begin() as conn:
        result = conn.execute(sql, {"faq_id": faq_id})
    return {"updated": result.rowcount or 0}


@router.get("/graph/stats")
def graph_stats() -> dict[str, Any]:
    query = """
    MATCH (n)
    WITH labels(n)[0] AS label, count(n) AS count
    RETURN label, count
    ORDER BY count DESC
    """
    rel_query = """
    MATCH ()-[r]->()
    WITH type(r) AS type, count(r) AS count
    RETURN type, count
    ORDER BY count DESC
    """
    with driver.session(database=settings.neo4j_database) as session:
        nodes = session.run(query).data()
        relationships = session.run(rel_query).data()
    return {"nodes": nodes, "relationships": relationships}


def _rows_to_graph(rows: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    for row in rows:
        source_id = row["source_id"]
        if not source_id:
            continue
        source = str(source_id)
        nodes[source] = {
            "id": source,
            "label": row["source_label"],
            "name": row["source_name"],
            "properties": row.get("source_properties") or {},
        }

        target_id = row["target_id"]
        if not target_id:
            continue
        target = str(target_id)
        nodes[target] = {
            "id": target,
            "label": row["target_label"],
            "name": row["target_name"],
            "properties": row.get("target_properties") or {},
        }
        edges.append({"source": source, "target": target, "type": row["relationship"]})

    return {"nodes": list(nodes.values()), "edges": edges}


@router.get("/graph")
def full_graph(limit: int = Query(default=1000, le=5000)) -> dict[str, Any]:
    query = """
    MATCH (a)-[r]->(b)
    RETURN
      elementId(a) AS source_id,
      labels(a)[0] AS source_label,
      coalesce(a.ten, a.name, a.ma, a.key) AS source_name,
      properties(a) AS source_properties,
      type(r) AS relationship,
      elementId(b) AS target_id,
      labels(b)[0] AS target_label,
      coalesce(b.name, b.ten, b.ma, b.key) AS target_name,
      properties(b) AS target_properties
    LIMIT $limit
    """
    with driver.session(database=settings.neo4j_database) as session:
        rows = session.run(query, limit=limit).data()
    return _rows_to_graph(rows)


@router.get("/graph/procedures/{code}")
def procedure_graph(code: str) -> dict[str, Any]:
    query = """
    MATCH (p:ThuTuc)
    WHERE p.key = $code OR p.ma = $code
    OPTIONAL MATCH (p)-[r]-(n)
    RETURN
      elementId(p) AS source_id,
      labels(p)[0] AS source_label,
      coalesce(p.ten, p.name, p.ma, p.key) AS source_name,
      properties(p) AS source_properties,
      type(r) AS relationship,
      elementId(n) AS target_id,
      labels(n)[0] AS target_label,
      coalesce(n.name, n.ten, n.ma, n.key) AS target_name,
      properties(n) AS target_properties
    LIMIT 120
    """
    with driver.session(database=settings.neo4j_database) as session:
        rows = session.run(query, code=code).data()

    return _rows_to_graph(rows)
