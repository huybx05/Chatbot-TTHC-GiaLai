"""Nhánh ``HYBRID_SEARCH`` — BM25 + vector + RRF fusion + rerank.

## Vì sao cần hybrid

Đo thật trên câu hỏi *"Phí chuyển nhượng quyền sử dụng đất là bao nhiêu?"*:

* **BM25 một mình**: trả 3 chunk của thủ tục ``1.115369`` — ``REQUIRED_DOCUMENTS``,
  ``RESULT``, ``GENERAL_INFO`` — **không có chunk FEE nào**. Cả ba cùng điểm
  ``14.384`` vì chúng khớp ``procedure_name`` (giống nhau giữa mọi chunk của cùng thủ
  tục) chứ không khớp nội dung. BM25 giỏi **tìm đúng thủ tục**, dở **tìm đúng mục**.
* **Vector một mình**: tìm đúng mục theo ngữ nghĩa nhưng bỏ sót từ khoá hiếm — mã thủ
  tục, số quyết định, thuật ngữ pháp lý đặc thù, và các từ không dấu.

Hybrid lấy điểm mạnh của cả hai; reranker sửa nốt thứ tự.

## RRF — Reciprocal Rank Fusion

    score(d) = Σ_i  1 / (k + rank_i(d))

với ``k = RRF_K_CONSTANT = 60``. Vì chỉ dùng **thứ hạng**, RRF gộp được hai thang điểm
khác hẳn nhau (BM25 không có cận trên; cosine trong 0..1) mà không cần chuẩn hoá. Đó
là lý do chọn RRF thay vì cộng điểm có trọng số.

Tài liệu không có mặt trong một danh sách thì không được cộng gì cho danh sách đó —
hành vi đúng, không phải lỗi. Tài liệu có mặt ở **cả hai** danh sách được cộng hai lần
và vì vậy luôn lên đầu: đó là tín hiệu mạnh nhất mà RRF tạo ra.

## Khoá gộp

``section_id``. Nó là ``_id`` trong Elasticsearch **và** ``section_id`` trong payload
Qdrant, nên gộp chính xác, không cần khớp mờ.

## Ba hàm

``keyword_only`` và ``vector_only`` **không phải chiến lược trả lời**. Chúng tồn tại
để (1) trộn thành ``hybrid``, và (2) kiểm thử riêng từng tín hiệu trên trang
``/admin/rag-playground``. Vì vậy cả ba nằm cùng file: chúng chia sẻ kiểu ``Candidate``
và cách map payload.

## Kế thừa vector

``hybrid`` **nhận** ``vector`` từ tầng gọi, không tự nhúng. Tầng FAQ đã nhúng câu hỏi
rồi; nhúng lại là trả tiền hai lần (~350 ms).
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from elasticsearch import Elasticsearch
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny

from backend.app.config import settings
from backend.app.rag.types import Candidate, RetrievalOutcome

logger = logging.getLogger(__name__)


#: Số candidate mỗi nhánh lấy về trước khi trộn, đọc từ ``HYBRID_BRANCH_K``.
#:
#: Đổi giá trị trong ``.env`` rồi **khởi động lại backend** (``settings`` được đọc một
#: lần lúc import, có ``lru_cache``). Đây là thông số quyết định **recall**: câu khó bị
#: bỏ sót thì tăng lên. Giữ 30 vì RRF cần đủ nguyên liệu trộn mà không làm rerank (nếu
#: bật) chạm giới hạn 500 item của API.
DEFAULT_BRANCH_K = settings.hybrid_branch_k

#: Số tài liệu **cổng từ chối** chấm mỗi lần. Lấy **điểm cao nhất** trong số đó.
#:
#: Vì sao không chấm 1: đo được RRF hạng 1 chưa chắc là rerank tốt nhất. Một câu hỏi
#: hợp lệ hai ý có RRF hạng 1 = ``REQUIRED_DOCUMENTS`` (rerank 0,5983) còn ``RESULT`` ở
#: hạng 2 lại được 0,6219. Chấm 1 tài liệu → cổng thấy 0,5983 < 0,60 → **từ chối oan**,
#: dù ngay trong danh sách có chunk đạt 0,6219.
#:
#: Vì sao không chấm nhiều hơn: 3 là đủ để bắt được chunk đúng trong thực nghiệm, và
#: token vẫn chỉ ~750 mỗi lượt (so với ~3.750 khi rerank đủ 15). Độ trễ gần như không
#: đổi vì thời gian gọi API chiếm phần lớn, không phải số tài liệu.
GATE_SCORE_N = 3

#: Trường và trọng số cho BM25.
#:
#: ## Đã thử ``["title^6", "content^1.2"]`` và PHẢI HOÀN LẠI
#:
#: Giả thuyết ban đầu: hạ trọng số ``procedure_name`` để BM25 hết trả 5 chunk cùng điểm.
#: Đo lại trên 30 câu thì **tệ hơn hẳn**:
#:
#:     cấu hình                      nhóm A (10 câu)   độ chính xác mục
#:     ["title^6", "content^1.2"]    6 đúng / 3 sai    2/7
#:     ["title^2", "content", ...]   9 đúng / 0 sai    4/7
#:
#: Nguyên nhân: khi tiêu đề mục không khớp (câu nêu tên thủ tục, không nêu mục), tín hiệu
#: còn lại là ``content``, và BM25 thưởng rất mạnh cho chunk **ngắn** (length
#: normalization). Kết quả: chunk ngắn nhất của thủ tục ``1.001699`` (Bảo trợ xã hội)
#: thắng cả câu hỏi về "xóa ghi nợ tiền sử dụng đất" và "cấp giấy phép xây dựng" — sai
#: hẳn lĩnh vực.
#:
#: ``procedure_name^1.5`` vì thế là **cần thiết**: nó là tín hiệu để tìm đúng thủ tục khi
#: câu hỏi nêu tên thủ tục. Cái giá phải trả là hiện tượng đồng điểm trong cùng thủ tục —
#: muốn hết thì phải tách header ra khỏi ``content`` khi index (reindex), không sửa được
#: bằng trọng số.
ES_FIELDS = ["title^2", "content", "procedure_name^1.5"]

#: Các trường lấy từ Elasticsearch — chỉ những gì ``Candidate`` cần.
ES_SOURCE = [
    "section_id",
    "procedure_code",
    "procedure_name",
    "section_type",
    "title",
    "content",
    "detail_url",
]

#: Mã thủ tục, dạng ``1.115374``.
#:
#: Dùng để **lọc cứng** thay vì để BM25 tự đoán. Lý do đo được: mã thủ tục **không**
#: nằm trong header của chunk (header chỉ có tên thủ tục, lĩnh vực, nguồn), và
#: ``1.115374`` chỉ xuất hiện trong content của **1/7** chunk của nó. Vì vậy khi câu hỏi
#: vừa có mã vừa có từ chung, từ chung thắng:
#:
#:     "1.115374"            → khớp 1.115374 / GENERAL_INFO    =  8,53
#:     "thời hạn giải quyết"  → khớp PROCESSING_TIME 5 thủ tục = 18,42  ← thắng
#:
#: Kết quả: hỏi "Thủ tục 1.115374 có thời hạn giải quyết bao lâu?" lại trả về
#: ``1.001699``. Lọc bằng ``term`` trên trường ``keyword`` là chính xác tuyệt đối.
CODE_PATTERN = re.compile(r"\b\d{1,2}\.\d{6}\b")


def extract_codes(question: str) -> list[str]:
    """Lấy các mã thủ tục có trong câu hỏi, giữ thứ tự, bỏ trùng.

    Tách thành hàm công khai để **mọi mode dùng cùng một cách trích mã**. Trước đây chỉ
    nhánh BM25 lọc mã còn nhánh vector thì không, nên hybrid trộn hai phạm vi khác nhau
    và trả về thủ tục khác hẳn (đo được: hỏi ``1.115374``, hybrid trả ``1.115345``).
    """
    return list(dict.fromkeys(CODE_PATTERN.findall(question)))


def _build_query(question: str, codes: list[str] | None = None) -> dict[str, Any]:
    """Dựng query BM25; nếu câu hỏi có mã thủ tục thì **lọc cứng** theo các mã đó.

    Người dùng nêu mã là đã chỉ định thủ tục, nên lọc là hành vi đúng — trả về chunk
    của thủ tục khác mới là sai.

    Không dùng ``multi_match`` cho ``procedure_code``: trường đó là ``keyword``, nên
    ``multi_match`` chỉ khớp khi **cả chuỗi** đúng bằng giá trị — điều không bao giờ
    xảy ra với câu hỏi tự nhiên ("Thủ tục 1.115374 có thời hạn...").

    Dùng ``terms`` (OR) chứ không ``term`` (một mã) vì người dùng có thể nêu **hai** mã
    trong câu so sánh — "1.115362 khác gì 1.115369?". Lọc một mã sẽ giấu hẳn thủ tục
    kia, không trả lời được câu hỏi.
    """
    chung: dict[str, Any] = {
        "multi_match": {
            "query": question,
            "fields": ES_FIELDS,
            "type": "best_fields",
        }
    }

    loc = codes if codes is not None else extract_codes(question)
    if not loc:
        return chung

    return {
        "bool": {
            "must": [chung],
            "filter": [{"terms": {"procedure_code": loc}}],
        }
    }


# ── Client lười theo event loop ──────────────────────────────────────────
# Cùng lý do như ``faq_cache._client()``: client async giữ connection pool gắn với
# event loop đã dùng nó lần đầu; loop đóng thì dùng lại sẽ ném
# ``RuntimeError: Event loop is closed``. Gắn với loop hiện tại và tạo lại khi đổi.

_es: Elasticsearch | None = None
_qdrant: AsyncQdrantClient | None = None
_qdrant_loop: asyncio.AbstractEventLoop | None = None


def _es_client() -> Elasticsearch:
    """Client Elasticsearch **đồng bộ**, gọi qua ``asyncio.to_thread``.

    ## Vì sao không dùng ``AsyncElasticsearch``

    ``AsyncElasticsearch`` được bọc trên ``aiohttp``, và ``aiohttp.ClientSession`` gắn
    với event loop đã tạo nó. Khi loop đóng (mỗi request của ``TestClient`` là một
    loop), session không đóng được nữa và Python in ra::

        Unclosed client session
        Unclosed connector

    Đã gặp thật khi chạy 4 mode liên tiếp. ``httpx`` chỉ in cảnh báo, còn ``aiohttp``
    giữ nguyên kết nối — ồn hơn và khó bỏ qua hơn.

    Client đồng bộ **không gắn với loop nào**, và BM25 chỉ mất ~40–50 ms nên đẩy sang
    thread bằng ``asyncio.to_thread`` là đủ tốt, đồng thời khớp với cách ``admin.py``
    đang dùng ``Elasticsearch`` cho endpoint trạng thái.
    """
    global _es
    if _es is None:
        basic_auth = None
        if settings.elastic_user and settings.elastic_password:
            basic_auth = (settings.elastic_user, settings.elastic_password)
        _es = Elasticsearch(
            settings.elasticsearch_host,
            basic_auth=basic_auth,
            request_timeout=settings.elastic_request_timeout,
        )
    return _es


def _qdrant_client() -> AsyncQdrantClient:
    global _qdrant, _qdrant_loop
    loop = asyncio.get_running_loop()
    if _qdrant is None or _qdrant_loop is not loop:
        _qdrant = AsyncQdrantClient(
            url=settings.qdrant_host,
            api_key=settings.qdrant_api_key or None,
        )
        _qdrant_loop = loop
    return _qdrant


async def close() -> None:
    """Đóng các client. Gọi trong lifespan shutdown của FastAPI."""
    global _es, _qdrant, _qdrant_loop
    if _es is not None:
        _es.close()
    if _qdrant is not None:
        await _qdrant.close()
    _es, _qdrant, _qdrant_loop = None, None, None


# ── Hai nhánh ────────────────────────────────────────────────────────────


def _search_es(question: str, top_k: int, codes: list[str] | None = None) -> dict[str, Any]:
    """Chạy BM25 **đồng bộ**. Tách ra để ``asyncio.to_thread`` gọi được.

    Nếu câu hỏi có mã thủ tục mà mã đó không tồn tại (gõ sai), lọc cứng sẽ trả **rỗng**.
    Khi đó tìm lại **không lọc mã** để câu hỏi vẫn có ngữ cảnh thay vì mất trắng — im
    lặng trả rỗng sẽ khiến người dùng tưởng "không có dữ liệu" trong khi chỉ là gõ nhầm.
    """
    client = _es_client()
    index = settings.elasticsearch_index or "chatbot_tthc"
    loc = codes if codes is not None else extract_codes(question)

    response = client.search(
        index=index,
        query=_build_query(question, loc),
        size=int(top_k),
        _source=ES_SOURCE,
    )

    if not response["hits"]["hits"] and loc:
        logger.info("Không thủ tục nào khớp mã trong câu hỏi, tìm lại không lọc mã")
        response = client.search(
            index=index,
            query={
                "multi_match": {
                    "query": question,
                    "fields": ES_FIELDS,
                    "type": "best_fields",
                }
            },
            size=int(top_k),
            _source=ES_SOURCE,
        )

    return dict(response)


async def keyword_only(
    question: str,
    *,
    top_k: int = DEFAULT_BRANCH_K,
    codes: list[str] | None = None,
    errors: list[str] | None = None,
) -> list[Candidate]:
    """BM25 trên Elasticsearch. Không cần embedding.

    Chạy trong thread (``asyncio.to_thread``) vì client Elasticsearch là đồng bộ —
    xem ``_es_client()``. BM25 chỉ mất ~40–50 ms nên không đáng dựng thêm một client
    async chỉ để tránh thread.

    ``codes``: mã thủ tục để **lọc cứng**. ``None`` = tự trích từ câu hỏi; truyền vào
    khi tầng gọi đã trích một lần và muốn dùng chung cho cả nhánh vector.
    """
    if not question.strip():
        return []

    try:
        response = await asyncio.to_thread(_search_es, question, int(top_k), codes)
    except Exception as exc:  # noqa: BLE001 — một nhánh hỏng thì nhánh kia vẫn chạy
        logger.warning("Tìm Elasticsearch lỗi: %s", exc)
        if errors is not None:
            errors.append(f"Elasticsearch: {type(exc).__name__}: {str(exc)[:100]}")
        return []

    ket_qua: list[Candidate] = []
    for hang, hit in enumerate(response["hits"]["hits"], start=1):
        src: dict[str, Any] = hit["_source"]
        ket_qua.append(
            Candidate(
                chunk_id=str(src.get("section_id") or hit["_id"]),
                procedure_code=str(src.get("procedure_code") or ""),
                procedure_name=str(src.get("procedure_name") or ""),
                section_type=str(src.get("section_type") or ""),
                title=str(src.get("title") or ""),
                content=str(src.get("content") or ""),
                detail_url=str(src.get("detail_url") or ""),
                score=float(hit["_score"] or 0.0),
                source="keyword",
                # Nhánh này chỉ có BM25 — dùng cho nhãn nguồn trên UI.
                by_keyword=True,
                keyword_rank=hang,
            )
        )
    return ket_qua


async def vector_only(
    vector: list[float],
    *,
    top_k: int = DEFAULT_BRANCH_K,
    codes: list[str] | None = None,
    errors: list[str] | None = None,
) -> list[Candidate]:
    """Cosine trên Qdrant ``semantic_search``. Nhận vector có sẵn, không tự nhúng.

    ## Vì sao phải lọc được theo ``codes``

    Đo thực nghiệm: câu ``"Thủ tục 1.115374 có thời hạn giải quyết bao lâu?"`` — nhánh
    BM25 lọc đúng mã nên trả toàn chunk của ``1.115374``, nhưng nhánh vector **không
    lọc** nên trả ``1.013229`` (thủ tục cấp phép xây dựng). Cosine không "đọc" được
    chuỗi mã, nên nó coi câu hỏi chỉ gồm các từ chung.

    Hệ quả khi RRF trộn hai nhánh: kết quả hybrid là ``1.115345`` — **sai**, trong khi
    BM25 một mình đã đúng. Lọc cùng một bộ mã cho cả hai nhánh thì mới trộn được.
    """
    collection = settings.qdrant_collection_semantic or "semantic_search"

    query_filter = None
    if codes:
        # ``MatchAny`` = OR trên nhiều mã, cần cho câu so sánh hai thủ tục.
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="procedure_code",
                    match=MatchAny(any=list(codes)),
                )
            ]
        )

    try:
        client = _qdrant_client()
        response = await client.query_points(
            collection_name=collection,
            query=vector,
            limit=int(top_k),
            with_payload=True,
            query_filter=query_filter,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tìm Qdrant lỗi: %s", exc)
        if errors is not None:
            errors.append(f"Qdrant: {type(exc).__name__}: {str(exc)[:100]}")
        return []

    ket_qua: list[Candidate] = []
    for hang, point in enumerate(response.points, start=1):
        p: dict[str, Any] = point.payload or {}
        ket_qua.append(
            Candidate(
                chunk_id=str(p.get("section_id") or ""),
                procedure_code=str(p.get("procedure_code") or ""),
                procedure_name=str(p.get("procedure_name") or ""),
                section_type=str(p.get("section_type") or ""),
                title=str(p.get("title") or ""),
                content=str(p.get("content") or ""),
                detail_url=str(p.get("detail_url") or ""),
                score=float(point.score),
                source="vector",
                # Nhánh này chỉ có vector.
                by_vector=True,
                vector_rank=hang,
            )
        )
    return ket_qua


# ── Trộn ─────────────────────────────────────────────────────────────────


def reciprocal_rank_fusion(
    keyword_hits: list[Candidate],
    vector_hits: list[Candidate],
    *,
    k: int | None = None,
    keyword_weight: float | None = None,
    vector_weight: float | None = None,
) -> list[Candidate]:
    """Gộp hai danh sách **đã xếp hạng** bằng RRF có trọng số.

    ``score(d) = w_kw / (k + rank_kw) + w_vc / (k + rank_vc)``
    với ``k = RRF_K_CONSTANT`` (60).

    ## Trọng số KHÔNG để bằng nhau — đo được là sai

    Công thức RRF trong tài liệu dùng trọng số bằng nhau. Đo trên 30 câu câu hỏi
    TTHC thì **cân bằng 50/50 tệ hơn vector đơn thuần**:

    | Cách trộn | Mã đúng /25 | **Mục đúng /7** | A | B | C |
    |---|---:|---:|---|---|---|
    | keyword only | 21 | 4/7 | 9/9 | 2/6 | 10/10 |
    | vector only | 23 | **7/7** | 9/9 | 5/6 | 9/10 |
    | **RRF 50/50** | 23 | **5/7** | 9/9 | 4/6 | 10/10 |
    | RRF 30/70 | 23 | 6/7 | 9/9 | 4/6 | 10/10 |
    | **RRF 20/80** | **23** | **7/7** | 9/9 | 4/6 | **10/10** |
    | RRF 70/30 | 23 | 5/7 | 9/9 | 4/6 | 10/10 |

    Nguyên nhân: BM25 cho **mọi chunk của cùng một thủ tục cùng điểm** (header chunk
    chứa tên thủ tục, xem ``ES_FIELDS``). Với trọng số ngang nhau, 5 chunk đồng điểm đó
    đẩy ``STEPS``/``SUBMISSION_METHOD`` lên ngang mục đúng:

        A3 "Thẩm định phương án sử dụng đất mất bao nhiêu ngày?"
           vector only → PROCESSING_TIME ✅
           RRF 50/50   → STEPS           ❌
           RRF 20/80   → PROCESSING_TIME ✅

    Hạ keyword xuống **0,2** thì RRF bằng vector ở cả hai chỉ số, và **hơn** ở nhóm C
    (10/10 so 9/10). ``0,2`` là mức cao nhất còn giữ được 7/7 mục — ``0,3`` đã mất A3.

    Vẫn giữ nhánh keyword vì nó là nguồn **từ khoá chính xác** (mã thủ tục, số văn bản)
    mà cosine không nắm được; chỉ là nó phải yếu, không được ngang hàng vector.
    """
    hang_so = settings.rrf_k_constant if k is None else int(k)
    w_kw = settings.rrf_keyword_weight if keyword_weight is None else float(keyword_weight)
    w_vc = settings.rrf_vector_weight if vector_weight is None else float(vector_weight)

    gop: dict[str, Candidate] = {}
    diem: dict[str, float] = {}
    #: Nhánh nào đã tìm ra chunk — để UI cho biết chunk đến từ BM25, vector hay cả hai.
    nguon: dict[str, set[str]] = {}
    #: Thứ hạng trong từng nhánh. Trên bộ dữ liệu nhỏ, cờ đúng/sai không phân biệt được
    #: (cả hai nhánh đều tìm ra gần như mọi chunk) nên phải giữ thứ hạng.
    hang_nhanh: dict[str, dict[str, int]] = {}

    for nhanh, danh_sach, trong_so in (
        ("keyword", keyword_hits, w_kw),
        ("vector", vector_hits, w_vc),
    ):
        for hang, candidate in enumerate(danh_sach, start=1):
            if not candidate.chunk_id:
                continue
            diem[candidate.chunk_id] = diem.get(candidate.chunk_id, 0.0) + trong_so / (
                hang_so + hang
            )
            nguon.setdefault(candidate.chunk_id, set()).add(nhanh)
            hang_nhanh.setdefault(candidate.chunk_id, {})[nhanh] = hang
            # Giữ bản ghi đầu tiên gặp; nội dung hai bên giống nhau vì cùng chunk.
            gop.setdefault(candidate.chunk_id, candidate)

    ket_qua = [
        Candidate(
            chunk_id=cu.chunk_id,
            procedure_code=cu.procedure_code,
            procedure_name=cu.procedure_name,
            section_type=cu.section_type,
            title=cu.title,
            content=cu.content,
            detail_url=cu.detail_url,
            score=diem[chunk_id],
            source="hybrid",
            by_keyword="keyword" in nguon[chunk_id],
            by_vector="vector" in nguon[chunk_id],
            keyword_rank=hang_nhanh[chunk_id].get("keyword"),
            vector_rank=hang_nhanh[chunk_id].get("vector"),
        )
        for chunk_id, cu in gop.items()
    ]
    ket_qua.sort(key=lambda c: c.score, reverse=True)
    return ket_qua


async def hybrid(
    question: str,
    *,
    vector: list[float],
    top_k: int = DEFAULT_BRANCH_K,
    codes: list[str] | None = None,
    use_rerank: bool = False,
    rerank_top_n: int | None = None,
    chunk_filter_min_score: float | None = None,
    use_gate: bool = False,
    gate_min_score: float | None = None,
) -> RetrievalOutcome:
    """BM25 + vector → RRF (→ rerank nếu bật) → (cổng từ chối nếu bật).

    Hai nhánh chạy **đồng thời** bằng ``asyncio.gather``: BM25 ~60–120 ms, Qdrant
    ~10–30 ms. Chạy song song thì tổng gần bằng nhánh chậm hơn, không phải tổng hai
    nhánh.

    ``codes`` được trích **một lần** rồi truyền cho **cả hai** nhánh. Trước đây chỉ
    nhánh BM25 lọc mã, nhánh vector thì không, nên RRF trộn hai phạm vi khác nhau và
    kết quả ra thủ tục khác hẳn — đo được: hỏi ``1.115374``, hybrid trả ``1.115345``.

    ## Vì sao ``use_rerank`` mặc định **TẮT**

    Đo trên 7 câu có mục kỳ vọng rõ, cùng cấu hình RRF 20/80:

        không rerank  →  7/7 mục đúng
        có rerank     →  4/7 mục đúng

    Rerank còn **hạ điểm một cách sai rõ rệt**. Câu *"Thủ tục 1.115374 có thời hạn giải
    quyết bao lâu?"*, nó chọn ``GENERAL_INFO`` với 0,7282 — chunk đó chỉ có mã, tên, số
    quyết định, cấp, lĩnh vực, cơ quan, trạng thái, **không có một chữ nào về thời hạn**
    — và đẩy ``PROCESSING_TIME`` (chứa *"43 Ngày ... Không quá 33 ngày làm việc"*) xuống.

    Rerank chấm "tài liệu này có liên quan đến chủ đề không", không chấm "mục này có
    loại thông tin được hỏi không". Với dữ liệu có nhiều mục cùng nói về một thủ tục,
    hai câu hỏi đó khác nhau.

    ## ``use_gate`` — cổng từ chối, việc **khác** với rerank

    Rerank dở ở việc chọn mục nhưng **giỏi** ở việc biết câu hỏi có trong phạm vi không.
    Đo trên 31 câu **ngắn, một ý**:

        câu trong phạm vi : 0,6306 – 0,9548
        câu ngoài phạm vi : 0,4493 – 0,5389     ← tách hoàn toàn ở 0,60

    Cosine **không** làm được: dải của nó chồng nhau (hợp lệ thấp nhất **0,5250** < rác
    cao nhất **0,5837**), nên không ngưỡng nào tách được.

    Cách dùng: chấm **đúng một** tài liệu (candidate đầu) rồi so với
    ``RERANKER_GATE_MIN_SCORE``. Vì không đổi thứ tự RRF nên **không** làm hỏng độ chính
    xác mục (điều rerank đầy đủ đã làm), và chỉ tốn ~200 token thay vì ~3.000.

    ## Cổng **bị bỏ qua** khi đã định danh được thủ tục

    Đo được một phản hồi: câu hỏi hợp lệ **hai ý** (*"… cần mang theo giấy tờ gì và kết
    quả nhận được là gì"*) chỉ làm candidate đầu đạt **0,6219** — cách ngưỡng 0,60 đúng
    **0,0219**. Câu càng dài, nhiều khía cạnh thì điểm càng bị chia nhỏ, nên cổng dễ từ
    chối oan **đúng những câu có giá trị nhất**.

    Lập luận: nếu câu hỏi đã nêu **mã thủ tục tồn tại** thì câu hỏi **mặc nhiên trong
    phạm vi** — không cần chấm gì để biết điều đó. Bỏ cổng trong trường hợp này vừa
    chính xác hơn, vừa tiết kiệm ~250 token và ~400 ms mỗi câu.

    Cờ ``gate_skipped`` trong ``RetrievalOutcome`` cho biết cổng bị **bỏ qua có chủ ý**,
    để UI phân biệt với trường hợp cổng **không chấm được** vì API lỗi.

    ## Hai ngưỡng khác nhau

    ``gate_min_score`` (cổng vào, áp cho 1 tài liệu) và ``chunk_filter_min_score`` (lọc
    từng chunk) **không được dùng lẫn**. Đo được chunk hồ sơ đúng chỉ 0,5966 — dưới
    ngưỡng cổng. Nếu lọc chunk theo ngưỡng cổng thì mất dữ liệu âm thầm.
    """
    # Hai việc khác nhau, hai nguồn khác nhau:
    #
    # * ``loc`` — **lọc tìm kiếm**. Không có mã xác thực thì vẫn lọc theo mã khớp hình dạng
    #   trong câu: mã bịa sẽ khớp 0 đoạn, và đó là kết quả đúng. Bỏ bước lọc này thì câu
    #   *"thủ tục 1.999999 nộp ở đâu"* trả về đoạn của **thủ tục khác** — lỗi đã đo được sau
    #   khi sửa cổng.
    # * ``da_dinh_danh`` — **quyền bỏ cổng**. Chỉ mã đã xác thực (tầng ① tra PostgreSQL) mới
    #   có quyền đó.
    loc = list(codes) if codes else extract_codes(question)

    # ── ĐÃ ĐỊNH DANH ĐƯỢC THỦ TỤC → câu hỏi mặc nhiên trong phạm vi, bỏ cổng ──
    # ① có mã thủ tục tồn tại (đã tra PostgreSQL ở tầng trên).
    # ② (sẽ thêm) khớp tên thủ tục rất chắc — chờ router Giai đoạn 13, vì trên bộ
    #    49 thủ tục thì pg_trgm dễ dãi giả tạo, sẽ vỡ khi nạp 1.909 thủ tục
    #    ("Cấp lại" / "Cấp đổi" / "Cấp mới" rất gần nhau).
    #
    # Tính **trước** khi tìm kiếm: nếu hai nhánh đều lỗi (ES/Qdrant tắt) thì hàm trả
    # sớm, nhưng vẫn phải báo đúng là cổng bị bỏ qua — nếu không UI sẽ hiện "cổng không
    # chấm được" và người kiểm thử tưởng API hỏng.
    # Bỏ cổng chỉ khi mã **đã được xác thực** ở tầng trên (truyền vào ``codes``).
    # ``loc`` có thể chứa chuỗi khớp regex mà **không tồn tại** trong PostgreSQL — đo được:
    # *"thủ tục 9.999999 cần gì"* vẫn làm cổng bị bỏ qua, vì regex thấy đúng hình dạng mã.
    # Mã đúng/sai chỉ trả lời được bằng bảng ``procedures``, không bằng hình dạng chuỗi.
    da_dinh_danh = bool(codes)
    chay_cong = use_gate and not da_dinh_danh
    bo_qua_cong = use_gate and not chay_cong

    loi: list[str] = []
    keyword_hits, vector_hits = await asyncio.gather(
        keyword_only(question, top_k=top_k, codes=loc, errors=loi),
        vector_only(vector, top_k=top_k, codes=loc or None, errors=loi),
    )

    fused = reciprocal_rank_fusion(keyword_hits, vector_hits)
    if not fused:
        return RetrievalOutcome(candidates=[], gate_skipped=bo_qua_cong, errors=loi)

    # Import trong hàm để ``reranker`` không bị nạp khi chỉ cần keyword/vector.
    from backend.app.rag import reranker

    nguong_cong = settings.reranker_gate_min_score if gate_min_score is None else gate_min_score
    nguong_loc = (
        settings.chunk_filter_min_score
        if chunk_filter_min_score is None
        else chunk_filter_min_score
    )

    # ── Xếp hạng + điểm cho cổng, chỉ MỘT lần gọi rerank ─────────────────
    if use_rerank:
        # Rerank đầy đủ: vừa xếp hạng lại, vừa có điểm của top-1 để làm cổng.
        kq = await reranker.rerank(
            question,
            fused,
            top_n=rerank_top_n,
            chunk_filter_min_score=nguong_loc,
        )
        candidates = kq.candidates
        rerank_used = kq.rerank_used
        rerank_error = kq.rerank_error
        gate_score = candidates[0].score if (chay_cong and kq.rerank_used and candidates) else None
    else:
        candidates = fused
        rerank_used = False
        rerank_error = ""
        gate_score = None

        if chay_cong:
            # Chấm **đúng một** tài liệu: đủ để biết câu hỏi có trong phạm vi không,
            # rẻ hơn ~15 lần so với rerank 15 tài liệu, và **không đổi thứ tự** RRF
            # nên không làm hỏng độ chính xác mục.
            #
            # Chấm **GATE_SCORE_N** tài liệu đầu rồi lấy **điểm cao nhất**, không chỉ
            # chấm hạng 1. Đo được: RRF hạng 1 là ``REQUIRED_DOCUMENTS`` (rerank 0,5983)
            # còn ``RESULT`` ở hạng 2 lại được 0,6219 — **top-1 của RRF không phải top-1
            # của reranker**. Chấm một tài liệu thì câu hỏi hợp lệ bị từ chối oan
            # (0,5983 < 0,60) dù trong danh sách có chunk đạt 0,6219.
            kiem = await reranker.rerank(
                question,
                fused[:GATE_SCORE_N],
                top_n=GATE_SCORE_N,
                chunk_filter_min_score=0.0,
            )
            rerank_used = kiem.rerank_used
            rerank_error = kiem.rerank_error
            if kiem.rerank_used and kiem.candidates:
                gate_score = max(c.score for c in kiem.candidates)
        elif use_gate:
            logger.info(
                "Bỏ cổng vì đã định danh được thủ tục %s — câu hỏi mặc nhiên trong phạm vi",
                ", ".join(loc),
            )

    # ── Cổng từ chối ─────────────────────────────────────────────────────
    # Chỉ chặn khi **chấm được** điểm. Rerank lỗi thì ``gate_score is None`` → cho đi
    # tiếp (fail open): thà trả ngữ cảnh có thể chưa đủ liên quan, còn hơn chặn oan
    # mọi câu hỏi chỉ vì API ngoài hỏng.
    if chay_cong and gate_score is not None and gate_score < nguong_cong:
        logger.info("Cổng từ chối chặn: %.4f < %.2f — %r", gate_score, nguong_cong, question[:60])
        return RetrievalOutcome(
            candidates=[],
            rerank_used=rerank_used,
            rerank_error=rerank_error,
            gate_score=gate_score,
            refused=True,
            errors=loi,
        )

    return RetrievalOutcome(
        candidates=candidates,
        rerank_used=rerank_used,
        rerank_error=rerank_error,
        gate_score=gate_score,
        # Cổng bị **bỏ qua có chủ ý** (đã định danh được), khác với cổng không chấm
        # được vì API lỗi. UI phải phân biệt hai trường hợp này.
        gate_skipped=bo_qua_cong,
    )
