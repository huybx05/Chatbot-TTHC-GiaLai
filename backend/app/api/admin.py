"""Admin endpoints for the monitoring UI.

Hai loại endpoint:

* **Đọc** — số liệu hệ thống, danh sách thủ tục, FAQ, đồ thị Neo4j.
* **Kiểm thử** — ``POST /retrieval/test`` chạy một chiến lược truy xuất và trả về
  candidate kèm điểm, để tune ngưỡng trên giao diện `/admin/rag-playground`.

Không endpoint nào ghi vào nội dung nghiệp vụ. Riêng ``/qa/approve*`` cập nhật cột
``status`` của bảng ``faq`` — đó là trạng thái duyệt, không phải nội dung.
"""

import time
from typing import Any, Literal

from elasticsearch import Elasticsearch
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from sqlalchemy import text

from backend.app.config import settings
from backend.app.db.neo4j import driver
from backend.app.db.postgres import engine
from backend.app.rag import embeddings, fact_lookup, graph_query, hybrid
from backend.app.rag.resolver import LazyQuestionVector

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
            counts = (
                conn.execute(
                    text(
                        """
                    SELECT
                      (SELECT COUNT(*) FROM procedures)::int AS procedures,
                      (SELECT COUNT(*) FROM procedure_sections)::int AS sections,
                      (SELECT COUNT(*) FROM faq)::int AS faq,
                      (SELECT COUNT(*) FROM faq WHERE status = 'ready')::int AS faq_ready
                    """
                    )
                )
                .mappings()
                .one()
            )
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
def list_procedures(q: str = "") -> dict[str, Any]:
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

        """
    )
    with engine.connect() as conn:
        rows = conn.execute(sql, {"q": q, "pattern": f"%{q}%"}).mappings().all()
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
        rows = (
            conn.execute(
                sql,
                {"procedure_code": procedure_code, "limit": limit},
            )
            .mappings()
            .all()
        )
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


# ---------------------------------------------------------------------------
# Kiểm thử truy xuất — dùng cho trang /admin/rag-playground
# ---------------------------------------------------------------------------

RetrievalMode = Literal["keyword", "vector", "hybrid", "fact_lookup", "graph"]

#: Chế độ ĐÃ triển khai. Chế độ khác trả 503 kèm thông báo rõ, **không** trả số liệu
#: giả. Trang UI trước đây sinh dữ liệu mô phỏng cho cả 5 chế độ — rất dễ nhầm là kết
#: quả thật khi chụp màn hình đưa vào báo cáo.
IMPLEMENTED_MODES: frozenset[str] = frozenset(
    {"keyword", "vector", "hybrid", "fact_lookup", "graph"}
)


class RetrievalTestRequest(BaseModel):
    """Tham số một lần kiểm thử truy xuất."""

    question: str = Field(min_length=1, max_length=1000)
    mode: RetrievalMode = "hybrid"
    top_k: int = Field(default=5, ge=1, le=20)
    #: Rerank **đầy đủ** cho mode ``hybrid`` (xếp lại TOÀN BỘ danh sách). Mặc định
    #: **TẮT**: đo trên 7 câu, rerank đầy đủ làm giảm độ chính xác mục từ 7/7 xuống 4/7
    #: (xem ``hybrid.hybrid``).
    #:
    #: **Tắt ở đây KHÔNG có nghĩa là không dùng reranker.** Cổng từ chối vẫn gọi rerank
    #: cho ``GATE_SCORE_N`` tài liệu đầu (mặc định 3) để biết câu hỏi có trong phạm vi
    #: không — rẻ hơn ~5 lần và **không xếp lại** danh sách.
    use_rerank: bool = False
    #: Bật **cổng từ chối** cho mode ``hybrid``: chấm vài tài liệu đầu để biết câu hỏi
    #: có trong phạm vi không. Mặc định **BẬT** — cosine không tách được câu ngoài phạm vi
    #: (dải điểm chồng nhau: hợp lệ thấp nhất 0,5250 < rác cao nhất 0,5837).
    use_refusal_gate: bool = True
    #: Dành cho FAQ tương lai (người dùng tự soạn cặp hỏi–đáp). Hiện **không** dùng:
    #: FAQ đã được gỡ khỏi luồng truy xuất.
    generate_answer: bool = False


def _build_context(candidates: list[dict[str, Any]]) -> str:
    """Ghép context theo đúng định dạng Phase 14 sẽ đưa vào prompt.

    Giữ một định dạng duy nhất để khi làm generation không phải viết lại — và để
    admin thấy trước chính xác model sẽ đọc gì.
    """
    blocks: list[str] = []
    for index, candidate in enumerate(candidates, start=1):
        blocks.append(
            "\n".join(
                [
                    f"[Nguồn {index}]",
                    f"Mã thủ tục: {candidate['procedure_code']}",
                    f"Tên thủ tục: {candidate['procedure_name']}",
                    f"Mục: {candidate['title']}",
                    f"Nội dung: {candidate['content']}",
                    f"URL: {candidate['detail_url']}",
                ]
            )
        )
    return "\n\n".join(blocks)


async def _coverage(
    codes: list[str],
    candidates: list[Any],
) -> tuple[list[str], list[str]]:
    """Ngữ cảnh đang có **mục nào** của thủ tục, và **thiếu mục nào**.

    Trả ``(sections_present, sections_absent)``.

    Vì sao cần: câu hỏi nhiều ý (*"cần giấy tờ gì **và** kết quả nhận được là gì"*) cần
    hai mục khác nhau; ``top_k`` không đảm bảo có đủ cả hai. Nếu mục bị thiếu mà không
    nói ra, tầng sinh câu trả lời (Giai đoạn 14) sẽ tự nghĩ ra phần còn thiếu — đúng
    loại ảo giác nguy hiểm nhất.

    Đây là bản **chưa cần phát hiện ý**: nó chỉ so ngữ cảnh với **toàn bộ** mục mà thủ
    tục có, không phán đoán người dùng hỏi mục nào. Danh sách ``absent`` vì vậy thường
    dài — dùng để hiển thị, không phải để cảnh báo. Bản theo từng ý sẽ làm khi có router.

    Trả ``([], [])`` khi không xác định được mã thủ tục.
    """
    if not codes:
        return [], []

    facts = await fact_lookup.get_facts(codes)
    if not facts:
        return [], []

    tat_ca: set[str] = set()
    for f in facts:
        tat_ca.update(f.muc_co)

    co: set[str] = set()
    for c in candidates:
        ma = getattr(c, "procedure_code", None)
        muc = getattr(c, "section_type", None)
        if muc and ma in codes:
            co.add(str(muc))

    # Giữ thứ tự ổn định để UI không nhảy giữa các lần bấm.
    return sorted(co), sorted(tat_ca - co)


async def _retrieval_response(
    payload: RetrievalTestRequest,
    candidates: list[Any],
    started: float,
    *,
    threshold: float | None,
    rerank_used: bool | None = None,
    warning: str = "",
    refused: bool = False,
    gate_score: float | None = None,
    gate_skipped: bool = False,
    sections_present: list[str] | None = None,
    sections_absent: list[str] | None = None,
) -> dict[str, Any]:
    """Đóng gói ``list[Candidate]`` thành response của trang kiểm thử.

    Với chế độ **không có ngưỡng** (keyword, vector, hybrid): ``threshold = None`` và
    ``passed = True`` cho mọi candidate. UI dựa vào ``threshold === null`` để hiện điểm
    thay vì nhãn "đạt/trượt" — ba chế độ này không có ngưỡng chấp nhận nào để so.

    ``answer`` để **rỗng**: chưa có tầng sinh câu trả lời (Giai đoạn 14). Trả rỗng
    trung thực hơn là trả nội dung chunk như thể đó là câu trả lời.

    ``rerank_used``: ``None`` = chế độ không dùng rerank (keyword/vector/faq);
    ``True`` = rerank đã chạy; ``False`` = **rerank lỗi**, kết quả chỉ là thứ tự trước
    rerank. Trường này phải hiện lên UI — khi rerank lỗi, điểm đổi hẳn
    (``0,4493 → 0,0317``) nên nhìn số rất dễ tưởng là đã qua rerank.

    ``gate_skipped`` / ``sections_present`` / ``sections_absent``: xem ``_coverage`` và
    ``hybrid.hybrid``.
    """
    dong = [c.as_dict() for c in candidates]
    cau_tra_loi, trich_dan, loi_sinh = await _sinh_neu_duoc_hoi(payload, dong)
    return {
        "mode": payload.mode,
        "top_k": payload.top_k,
        "threshold": threshold,
        "passed": bool(dong),
        "candidate_count": len(dong),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "answer": cau_tra_loi,
        "answer_error": loi_sinh,
        "citations": trich_dan,
        "context": _build_context(dong),
        "candidates": dong,
        "rerank_used": rerank_used,
        "warning": warning,
        # ``refused=True``: hệ thống **chủ động không trả lời** vì điểm liên quan của
        # kết quả tốt nhất dưới ngưỡng. ``gate_score`` là con số dẫn đến quyết định đó,
        # hiện lên UI để thấy ngưỡng đang chặn ở đâu.
        "refused": refused,
        "gate_score": None if gate_score is None else round(gate_score, 4),
        "gate_skipped": gate_skipped,
        # Mục nào của thủ tục đang có trong ngữ cảnh / còn thiếu. Rỗng khi không có mã.
        "sections_present": sections_present or [],
        "sections_absent": sections_absent or [],
    }


async def _sinh_neu_duoc_hoi(
    payload: RetrievalTestRequest, dong: list[dict[str, Any]]
) -> tuple[str, list[dict[str, str]], str]:
    """Sinh câu trả lời cho một chế độ truy xuất, nếu người kiểm thử bật ô đó.

    Trả ``(câu trả lời, trích dẫn, lỗi)``. Không ném lỗi: đây là trang kiểm thử, một lần sinh
    hỏng không được làm hỏng kết quả truy xuất đã có.
    """
    if not payload.generate_answer or not dong:
        return "", [], ""

    from backend.app.workflow import answer as sinh

    if not sinh.dang_bat():
        return "", [], "chưa cấu hình mô hình sinh câu trả lời"

    # Đổi candidate sang cùng kiểu dict mà luồng chính dùng, để **một** bộ dựng ngữ cảnh phục
    # vụ cả hai đường — nếu mỗi bên tự dựng, hai chỗ sẽ trích số hiệu khác nhau.
    bang_chung = [
        {
            "kind": "faq" if muc.get("intent") else "chunk",
            "procedure_code": muc.get("procedure_code") or "",
            "procedure_name": muc.get("procedure_name") or "",
            "detail_url": muc.get("detail_url") or "",
            "title": muc.get("title") or muc.get("section_type") or "",
            "content": muc.get("content") or "",
        }
        for muc in dong[:8]
    ]

    try:
        ket_qua = await sinh.sinh(payload.question, bang_chung)
    except sinh.AnswerError as exc:
        return "", [], exc.reason
    return ket_qua.text, list(ket_qua.citations), ""


def _graph_response(
    payload: "RetrievalTestRequest",
    evidence: "graph_query.GraphEvidence",
    started: float,
) -> dict[str, Any]:
    """Đóng gói ``GraphEvidence`` thành response của trang kiểm thử.

    **Một hàm chung cho mọi template** — không có nhánh riêng theo intent. Cột hiển thị
    lấy từ chính ``evidence.rows`` do nhánh graph đã chuẩn hoá, nên thêm template mới
    là trang kiểm thử tự hiện đúng mà không phải sửa file này.

    Mỗi dòng bằng chứng thành một "candidate" để dùng lại đúng thẻ hiển thị sẵn có
    (mã thủ tục, tên, URL, nội dung).
    """
    candidates: list[dict[str, Any]] = []

    # Câu hỏi nhiều ý → evidence có nhiều **phần** (mỗi phần một hình dạng). Trải phẳng
    # để UI và `candidate_count` vẫn đọc được như cũ, nhưng mỗi candidate gắn nhãn phần
    # của nó để người kiểm thử biết dòng nào thuộc ý nào.
    for phan in evidence.parts:
        nhan = phan.columns
        for row in phan.rows:
            tieu_de = next((row.get(k) for k, _n, _s in nhan if row.get(k)), "")
            candidates.append(
                {
                    "id": f"graph-{len(candidates) + 1}",
                    "source": "graph",
                    "score": 0.0,
                    "passed": True,
                    "intent": phan.intent,
                    "section_type": "GRAPH",
                    "title": str(tieu_de),
                    "content": "\n".join(
                        f"{nhan_cot}: {row[khoa]}"
                        for khoa, nhan_cot, _tach in nhan
                        if row.get(khoa)
                    ),
                    "procedure_code": str(row.get("ma_thu_tuc") or ""),
                    "procedure_name": str(row.get("ten") or ""),
                    "detail_url": str(row.get("detail_url") or ""),
                    "by_keyword": False,
                    "by_vector": False,
                    "keyword_rank": None,
                    "vector_rank": None,
                }
            )

    for chi_so, row in enumerate(evidence.rows, start=1):
        nhan = graph_query.COLUMNS.get(evidence.template, ())
        tieu_de = next((row.get(k) for k, _n, _s in nhan if row.get(k)), "")
        candidates.append(
            {
                "id": f"graph-{len(candidates) + 1}",
                "source": "graph",
                "score": 0.0,
                "passed": True,
                "intent": evidence.intent,
                "section_type": "GRAPH",
                "title": str(tieu_de),
                "content": "\n".join(
                    f"{nhan_cot}: {row[khoa]}" for khoa, nhan_cot, _tach in nhan if row.get(khoa)
                ),
                "procedure_code": str(row.get("ma_thu_tuc") or ""),
                "procedure_name": str(row.get("ten") or ""),
                "detail_url": str(row.get("detail_url") or ""),
                # Nhánh graph không đi qua BM25/vector.
                "by_keyword": False,
                "by_vector": False,
                "keyword_rank": None,
                "vector_rank": None,
            }
        )
        del chi_so

    return {
        "mode": payload.mode,
        "top_k": payload.top_k,
        "threshold": None,
        "passed": evidence.found,
        "candidate_count": len(candidates),
        "elapsed_ms": evidence.latency_ms or int((time.perf_counter() - started) * 1000),
        "answer": graph_query.render(evidence),
        "context": graph_query.render(evidence),
        "candidates": candidates,
        "rerank_used": None,
        "warning": evidence.note,
        "refused": False,
        "gate_score": None,
        # Nhánh graph không dùng cổng và không lọc theo mã thủ tục. **Ba trường này phải
        # có mặt** dù giá trị rỗng: frontend đọc thẳng `sections_present` và
        # `gate_score`, thiếu một trường là React ném lỗi và cả trang trắng.
        "gate_skipped": False,
        "sections_present": [],
        "sections_absent": [],
        # Hai trường riêng của nhánh graph, để UI hiện được template/intent đã chọn.
        "graph_template": evidence.template,
        "graph_intent": evidence.intent,
        # Hỏi lại khi mơ hồ: không trả lời, không từ chối — mời người dùng chọn.
        "clarify": evidence.clarify,
        "clarify_question": evidence.clarify_question,
        "clarify_options": evidence.options,
    }


class WorkflowAskRequest(BaseModel):
    """Yêu cầu chạy **trọn luồng** cho một câu hỏi.

    Khác ``RetrievalTestRequest``: yêu cầu này không có ``mode`` — người dùng **không** chọn
    nhánh, luồng tự chọn. Đó chính là thứ cần kiểm: quyết định định tuyến có đúng không.
    """

    question: str = Field(min_length=1, max_length=1000)


@router.post("/workflow/ask")
async def workflow_ask(payload: WorkflowAskRequest) -> dict[str, Any]:
    """Chạy một câu hỏi qua **cả đồ thị** và trả bằng chứng tìm được.

    Đây là lối vào dùng chung với ``api/chat.py`` (cùng một hàm), nhờ vậy trang kiểm thử
    không thể lệch với luồng thật.

    ⚠️ Mốc 1 **chưa sinh câu trả lời**: ``has_answer`` luôn là ``false``, ``outcome`` là
    *"tìm được bằng chứng"* chứ không phải *"đã trả lời"*.
    """
    # Nạp trong hàm: ``workflow`` kéo theo ``langgraph`` và cả bốn động cơ truy xuất; trang
    # admin không cần chúng ở mọi lần gọi khác.
    from backend.app.rag import retrieval

    ket_qua = await retrieval.retrieve_full(payload.question)
    du_lieu = ket_qua.to_dict()
    du_lieu["summary"] = retrieval.tom_tat(ket_qua)
    return du_lieu


@router.post("/retrieval/test")
async def retrieval_test(payload: RetrievalTestRequest) -> dict[str, Any]:
    """Chạy **một** chiến lược truy xuất trên câu hỏi admin nhập.

    Mỗi lần gọi chỉ chạy đúng chế độ trong ``payload.mode`` — không chạy lẫn các chế
    độ khác, để so sánh được từng tín hiệu một cách độc lập.

    Trả **top-K kèm điểm** chứ không chỉ top-1: người tune ngưỡng cần thấy cả candidate
    dưới ngưỡng, để phân biệt "trượt vì 0,74" với "trượt vì 0,50".
    """
    if payload.mode not in IMPLEMENTED_MODES:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Chế độ {payload.mode!r} chưa triển khai. Hiện có: "
                f"{', '.join(sorted(IMPLEMENTED_MODES))}."
            ),
        )

    started = time.perf_counter()

    # ── ĐỊNH DANH: tra mã thủ tục trong câu hỏi (kể cả mã thiếu dấu chấm) ──
    # Làm **một lần** rồi dùng cho mọi mode. Đây là bước *định danh*, không phải tìm
    # kiếm: người dùng nêu mã thì hoặc mã tồn tại, hoặc báo không có — không đoán.
    lookup = await fact_lookup.resolve_codes(payload.question)

    if lookup.not_found:
        # Gõ thiếu/thừa chữ số → báo thẳng, KHÔNG tìm bằng từ khoá. Đo trên 1.909 mã:
        # không có hai mã nào trùng khi bỏ dấu chấm, nên không có chuyện "gần đúng".
        ma = ", ".join(lookup.asked)
        return await _retrieval_response(
            payload,
            [],
            started,
            threshold=None,
            warning=(
                f"Không có thủ tục nào mang mã {ma}. "
                "Kiểm tra lại số trong mã (mã có dạng 1.001699)."
            ),
        )

    # Mã đã xác nhận dạng chuẩn; nếu PG lỗi thì dùng regex dự phòng (chỉ bắt được mã
    # có dấu chấm) để câu hỏi vẫn chạy thay vì hỏng hoàn toàn.
    codes = list(lookup.matched) or hybrid.extract_codes(payload.question)

    # ── GRAPH QUERY — Cypher Template, KHÔNG qua LLM ──────────────────────
    # Nhánh này tự định danh mã/số hiệu văn bản nên không cần ``codes`` ở trên, nhưng
    # truyền vào để khỏi tra PostgreSQL hai lần.
    #
    # ``LazyQuestionVector``: câu hỏi chỉ được **nhúng khi thật sự cần** (khi không có
    # mã, không có số hiệu văn bản, không khớp tên chính xác, không neo được vào thực
    # thể đóng). Nhờ vậy đường nhanh của Graph giữ nguyên ~12 ms thay vì ~370 ms; và
    # cả request vẫn chỉ có **một** lần nhúng, dùng lại được nếu chuyển sang hybrid.
    if payload.mode == "graph":
        evidence = await graph_query.answer(
            payload.question,
            codes=codes,
            limit=max(payload.top_k, 1),
            get_vector=LazyQuestionVector(payload.question).get,
        )
        return _graph_response(payload, evidence, started)

    # ── FACT LOOKUP — metadata từ PostgreSQL, KHÔNG qua LLM ──────────────
    if payload.mode == "fact_lookup":
        if not codes:
            # Tra metadata cần biết **thủ tục nào**. Không có mã thì phải khớp tên
            # (pg_trgm) — đó là việc của router ở Giai đoạn 13, không phải nhánh này.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Chế độ Fact lookup cần mã thủ tục trong câu hỏi "
                    "(ví dụ: 1.115374 hoặc 1115374). "
                    "Tra theo tên thủ tục sẽ làm ở Giai đoạn 13."
                ),
            )

        facts = await fact_lookup.get_facts(codes)
        if not facts:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Không đọc được metadata cho mã: {', '.join(codes)}.",
            )

        tra_loi = fact_lookup.render_answer(facts)
        dong = [f.as_dict() for f in facts]
        return {
            "mode": payload.mode,
            "top_k": payload.top_k,
            "threshold": None,
            "passed": True,
            "candidate_count": len(dong),
            # Câu trả lời ghép từ template, **mọi chi tiết đều từ 6 trường whitelist**.
            "answer": tra_loi,
            "context": tra_loi,
            # Mỗi thủ tục là một "candidate" để UI hiện bảng trường có cấu trúc.
            "candidates": [
                {
                    "id": f["ma_thu_tuc"],
                    "source": "fact_lookup",
                    "score": 0.0,
                    "passed": True,
                    "intent": "metadata",
                    "section_type": "METADATA",
                    "title": f["ten_thu_tuc"],
                    "content": "\n".join(f"{k}: {v}" for k, v in f.items() if k != "ten_thu_tuc"),
                    "procedure_code": f["ma_thu_tuc"],
                    "procedure_name": f["ten_thu_tuc"],
                    "detail_url": f["detail_url"],
                    # Fact lookup đọc thẳng PostgreSQL — không qua BM25/vector.
                    "by_keyword": False,
                    "by_vector": False,
                    "keyword_rank": None,
                    "vector_rank": None,
                }
                for f in dong
            ],
            "rerank_used": None,
            "warning": "",
            "refused": False,
            "gate_score": None,
            # Fact lookup không dùng cổng và không lọc theo mã thủ tục. Ba trường này
            # **phải có mặt** dù rỗng — frontend đọc thẳng, thiếu là cả trang trắng.
            "gate_skipped": False,
            "sections_present": [],
            "sections_absent": [],
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }

    # ── KEYWORD — chỉ BM25, KHÔNG cần embedding ──────────────────────────
    if payload.mode == "keyword":
        ket_qua = await hybrid.keyword_only(
            payload.question, top_k=payload.top_k, codes=codes or None
        )
        muc_co, muc_thieu = await _coverage(codes, ket_qua)
        return await _retrieval_response(
            payload,
            ket_qua,
            started,
            threshold=None,
            sections_present=muc_co,
            sections_absent=muc_thieu,
        )

    # ── VECTOR và HYBRID — cần embedding ─────────────────────────────────
    if not embeddings.enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chưa cấu hình QWEN_API_KEY nên không nhúng được câu hỏi.",
        )
    try:
        vector = await embeddings.embed(payload.question)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Không gọi được API embedding: {exc}",
        ) from exc

    if payload.mode == "vector":
        # Lọc theo mã thủ tục nếu câu hỏi có mã — cùng lý do như nhánh BM25: cosine
        # không "đọc" được chuỗi mã, nên không lọc thì trả thủ tục khác hẳn.
        ket_qua = await hybrid.vector_only(
            vector,
            top_k=payload.top_k,
            codes=codes or None,
        )
        muc_co, muc_thieu = await _coverage(codes, ket_qua)
        return await _retrieval_response(
            payload,
            ket_qua,
            started,
            threshold=None,
            sections_present=muc_co,
            sections_absent=muc_thieu,
        )

    # ── HYBRID — BM25 + vector → RRF (→ rerank nếu bật) ──────────────────
    # Mỗi nhánh lấy rộng hơn ``top_k`` để RRF có nguyên liệu trộn; sau rerank
    # mới cắt về ``top_k``.
    ket_qua = await hybrid.hybrid(
        payload.question,
        vector=vector,
        top_k=max(payload.top_k * 3, hybrid.DEFAULT_BRANCH_K),
        codes=codes or None,
        use_rerank=payload.use_rerank,
        use_gate=payload.use_refusal_gate,
        # Phải >= top_k, nếu không thì đặt top_k=20 sẽ chỉ nhận được 15 candidate
        # (rerank trả tối đa rerank_top_n) và UI hiện "15/20".
        rerank_top_n=max(payload.top_k, settings.reranker_top_n),
        # 0.0 = KHÔNG lọc chunk: trang kiểm thử phải thấy TOÀN BỘ dải điểm rerank để
        # dựng bảng "ngưỡng nào giữ đúng / loại sai". Đây là ngưỡng **lọc chunk**,
        # hoàn toàn khác ngưỡng **cổng vào** (``RERANKER_GATE_MIN_SCORE``).
        chunk_filter_min_score=0.0,
    )

    # ── Phủ mục: ngữ cảnh có những mục nào của thủ tục, thiếu mục nào ──────
    hien_co = [c for c in ket_qua.candidates[: payload.top_k]]
    muc_co, muc_thieu = await _coverage(codes, hien_co)

    canh_bao = ""
    if ket_qua.refused:
        canh_bao = (
            f"Không tìm thấy thông tin phù hợp trong dữ liệu: điểm liên quan của kết quả "
            f"tốt nhất chỉ {ket_qua.gate_score:.4f} "
            f"(ngưỡng cổng {settings.reranker_gate_min_score:.2f}). "
            "Hệ thống từ chối trả lời thay vì đưa ngữ cảnh không liên quan vào câu trả lời."
        )
    elif payload.use_rerank and not ket_qua.rerank_used:
        canh_bao = (
            "Rerank KHÔNG chạy được nên kết quả dưới đây chỉ là thứ tự RRF, "
            f"chưa qua chấm lại: {ket_qua.rerank_error or 'không rõ nguyên nhân'}. "
            "Đừng dùng số liệu này để so sánh với lần có rerank."
        )
    elif ket_qua.gate_skipped:
        # Cổng bị bỏ qua **có chủ ý** — không phải lỗi. Không cảnh báo, chỉ ghi nhận.
        canh_bao = (
            "Cổng từ chối được BỎ QUA vì câu hỏi đã nêu mã thủ tục tồn tại — câu hỏi "
            "mặc nhiên trong phạm vi. Tiết kiệm một lượt rerank; không phải lỗi."
        )
    elif payload.use_refusal_gate and ket_qua.gate_score is None:
        canh_bao = (
            "Cổng từ chối KHÔNG chấm được (rerank lỗi) nên câu hỏi này **chưa được "
            f"kiểm tra phạm vi**: {ket_qua.rerank_error or 'không rõ nguyên nhân'}. "
            "Kết quả vẫn hiện nhưng có thể là ngữ liệu ngoài phạm vi."
        )

    if not ket_qua.refused and codes and not muc_co:
        # Có mã thủ tục nhưng không lấy được đoạn nào của chính thủ tục đó — dấu hiệu
        # chỉ mục lệch, không phải câu hỏi khó. Phải nói rõ, không để người dùng
        # tưởng đó là câu trả lời.
        canh_bao = (
            (canh_bao + " " if canh_bao else "")
            + f"Không lấy được đoạn văn nào thuộc thủ tục {', '.join(codes)}. "
            "Kết quả dưới đây là từ thủ tục khác nên KHÔNG dùng để trả lời câu hỏi này."
        )

    return await _retrieval_response(
        payload,
        ket_qua.candidates[: payload.top_k],
        started,
        threshold=None,
        # None khi không bật: UI chỉ hiện nhãn "Đã rerank"/"CHƯA rerank" ở lần có bật,
        # để không gây hiểu nhầm là mode này luôn đi qua rerank.
        rerank_used=ket_qua.rerank_used if payload.use_rerank else None,
        warning=canh_bao,
        refused=ket_qua.refused,
        gate_score=ket_qua.gate_score,
        gate_skipped=ket_qua.gate_skipped,
        sections_present=muc_co,
        sections_absent=muc_thieu,
    )
