"""Rerank bằng ``qwen3-rerank`` — xếp lại candidate trước khi sinh câu trả lời.

## API

Endpoint **riêng**, không dùng ``/compatible-mode/v1`` (rerank không thuộc chuẩn
OpenAI). Khai báo qua ``RERANKER_BASE_URL``, định dạng **DashScope text-rerank**:

    POST {RERANKER_BASE_URL}
    {
      "model": "qwen3-rerank",
      "input": {"query": "...", "documents": ["...", "..."]},
      "parameters": {"return_documents": false, "top_n": 15}
    }

    → {"output": {"results": [{"index": 0, "relevance_score": 0.477}, ...]},
       "usage": {"total_tokens": 143}}

Đã gọi thật và xác nhận HTTP 200 với định dạng này.

## Điểm rerank THẤP hơn trực giác

Đo thật một câu hỏi về phí, 3 tài liệu:

    đúng chủ đề (phí, lệ phí)      → 0.477
    không liên quan (thời hạn)     → 0.382
    không liên quan (hồ sơ)        → 0.318

Ba điểm nằm sát nhau trong dải 0,3–0,5. Vì vậy **không dùng ngưỡng để lọc chunk**:
ngưỡng 0,35 sẽ giữ lại chunk 0,382 là chunk sai chủ đề, còn nếu đặt cao hơn thì loại
chunk đúng. Ngưỡng lọc chunk mặc định là **0,0** (``CHUNK_FILTER_MIN_SCORE``).

Ngưỡng 0,60 chỉ dùng cho **cổng vào** (``RERANKER_GATE_MIN_SCORE``) — áp cho một tài
liệu duy nhất, nơi dải điểm của câu ngoài phạm vi (0,45–0,58) tách được khỏi câu trong
phạm vi (0,63–0,95).

Trang kiểm thử truyền ``chunk_filter_min_score=0.0`` để thấy **toàn bộ dải điểm**, nhờ
vậy mới dựng được bảng "ngưỡng nào giữ đúng / loại sai".

## Giới hạn của API

| Giới hạn | Giá trị |
|---|---|
Token mỗi item | **4.000** |
Số item mỗi request | **500** |
Tổng token mỗi request | **120.000** |

Vượt là **HTTP 400, API KHÔNG tự cắt**. Số đo hiện tại: ``MAX_CHARS_PER_CHUNK`` =
4500 ký tự → **1.194 token** (đo bằng API thật), tỉ lệ 3,77 ký tự/token, còn ~70% dư.
Chạm 4.000 token phải tới ≈ 15.080 ký tự nên hiện tại không có nguy cơ ở mỗi item.
Giới hạn số item được chặn bằng ``RERANKER_TOP_N`` (15) — không bao giờ gửi 500.

## Vì sao tạo ``httpx.AsyncClient`` mỗi lần gọi

Rerank chạy **một** request cho mỗi câu hỏi. Giữ client lâu dài buộc phải xử lý chuyện
event loop đổi (như ``embeddings.py``) mà lợi ích gần bằng không: mở connection chỉ
vài ms so với ~300–600 ms của chính lần rerank.
"""

from __future__ import annotations

import logging

import httpx

from backend.app.config import settings
from backend.app.rag.types import Candidate, RetrievalOutcome

logger = logging.getLogger(__name__)


def _rerank_text(candidate: Candidate) -> str:
    """Văn bản gửi rerank: **tiêu đề mục + toàn bộ nội dung chunk**.

    ## Đã thử cắt header và PHẢI HOÀN LẠI

    Giả thuyết: mọi chunk cùng một thủ tục có header giống hệt nhau —

    ```
    Tên thủ tục: Thẩm định, phê duyệt phương án sử dụng đất    ← 1.115362 dài 569 ký tự
    Thời hạn giải quyết
    Lĩnh vực: Đất đai · Cấp thực hiện: Cấp tỉnh
    Nguồn: https://dichvucong.gov.vn/...
    ---
    ```

    — nên reranker bị "neo" vào tên thủ tục thay vì nội dung. Đã thử chỉ gửi phần sau
    ``---``.

    **Kết quả đo trên 30 câu: không cải thiện, có dấu hiệu tệ hơn.**

    Độ chính xác cấp mục của hybrid: ``5/7`` (gửi nguyên) → ``3/7`` (cắt header).
    Cụ thể mất hai câu: A1 (``PROCESSING_TIME`` → ``GENERAL_INFO``) và C4
    (``PROCESSING_TIME`` → ``REQUIRED_DOCUMENTS``); chỉ được lại một câu về mã thủ tục.

    Lý do có thể: header chứa **tiêu đề mục** và cách trình bày thống nhất, là tín hiệu
    hữu ích cho reranker. Cắt đi thì ``GENERAL_INFO`` (thân ngắn, chung chung) trông
    "khớp" với nhiều câu hỏi hơn.

    **Lưu ý về phép đo:** lần A/B riêng cho thay đổi này bị API trả ``403 Forbidden``
    (gọi quá nhiều lần trong thời gian ngắn) nên **không hợp lệ** — khi rerank lỗi, hàm
    giữ nguyên thứ tự RRF và mọi cấu hình cho kết quả giống nhau. Muốn kết luận chắc
    phải chạy lại A/B khi API hồi phục.

    Giữ ``title`` ở đầu vì tiêu đề mục ngắn và chính là tín hiệu phân biệt.
    """
    return f"{candidate.title}\n{candidate.content}"


def enabled() -> bool:
    """Rerank có cấu hình không."""
    return bool(settings.reranker_base_url.strip() and settings.qwen_api_key.strip())


async def rerank(
    question: str,
    candidates: list[Candidate],
    *,
    top_n: int | None = None,
    chunk_filter_min_score: float = 0.0,
) -> RetrievalOutcome:
    """Chấm lại ``candidates`` theo độ liên quan thật với ``question``.

    Args:
        question: câu hỏi người dùng.
        candidates: danh sách đầu vào, **đã xếp hạng** bởi tầng trước.
        top_n: số candidate gửi đi chấm. Mặc định ``RERANKER_TOP_N`` (15) — cũng là
            giới hạn an toàn, vì API nhận tối đa 500 item mỗi request.
        chunk_filter_min_score: loại candidate có ``relevance_score`` thấp hơn. Mặc
            định **0, tức không lọc**, và gần như luôn phải để 0.

    ## Vì sao tên tham số là ``chunk_filter_min_score`` chứ không phải ``min_score``

    Ngưỡng cổng vào (``RERANKER_GATE_MIN_SCORE``) và ngưỡng lọc từng chunk là **hai
    chuyện khác nhau**. Đo được: một câu hỏi hợp lệ hai ý có chunk hồ sơ đúng chỉ đạt
    **0,5966** — dưới ngưỡng cổng 0,60. Nếu ai đó truyền 0,60 vào tham số này thì chunk
    đúng bị **loại âm thầm**, không có log, không có cảnh báo.

    Đặt tên khác hẳn để không thể truyền nhầm; cổng dùng ngưỡng riêng của nó.

    Returns:
        ``RetrievalOutcome`` với ``rerank_used`` cho biết rerank có **thực sự chạy và
        thành công** không. Cờ này phải hiện lên UI: khi rerank lỗi, danh sách giữ
        nguyên thứ tự cũ nhưng điểm đổi hẳn (0,4493 → 0,0317), nên nhìn số rất dễ tưởng
        là rerank đã chạy.

    Nếu rerank không cấu hình hoặc lỗi mạng, trả lại ``candidates`` **nguyên thứ tự**
    (cắt còn ``top_n``) với ``rerank_used=False``. Rerank là bước cải thiện, không phải
    đường bắt buộc — một lần gọi API hỏng không được làm cả truy vấn hỏng.
    """
    limit = max(1, settings.reranker_top_n if top_n is None else int(top_n))

    if not candidates or not enabled():
        return RetrievalOutcome(candidates=candidates[:limit], rerank_used=False)

    gui_di = candidates[:limit]

    body = {
        "model": settings.reranker_model_name,
        "input": {
            "query": question,
            # Bỏ header của chunk trước khi gửi — xem ``_rerank_text()``.
            "documents": [_rerank_text(c) for c in gui_di],
        },
        "parameters": {"return_documents": False, "top_n": len(gui_di)},
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                settings.reranker_base_url,
                headers={
                    "Authorization": f"Bearer {settings.qwen_api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
        response.raise_for_status()
        results = response.json()["output"]["results"]
    except Exception as exc:  # noqa: BLE001 — rerank hỏng không được chặn truy xuất
        logger.warning("Rerank lỗi, giữ nguyên thứ tự trước đó: %s", exc)
        return RetrievalOutcome(
            candidates=gui_di,
            rerank_used=False,
            rerank_error=str(exc)[:300],
        )

    ket_qua: list[Candidate] = []
    for item in sorted(results, key=lambda r: r["relevance_score"], reverse=True):
        chi_so = int(item["index"])
        if not 0 <= chi_so < len(gui_di):  # pragma: no cover - phòng thủ
            continue
        diem = float(item["relevance_score"])
        if diem < chunk_filter_min_score:
            continue
        goc = gui_di[chi_so]
        ket_qua.append(
            Candidate(
                chunk_id=goc.chunk_id,
                procedure_code=goc.procedure_code,
                procedure_name=goc.procedure_name,
                section_type=goc.section_type,
                title=goc.title,
                content=goc.content,
                detail_url=goc.detail_url,
                score=diem,
                source="rerank",
                # Giữ nguyên nguồn gốc: reranker **chấm lại** chunk chứ không tạo chunk
                # mới, nên thông tin "do BM25 hay vector tìm ra" vẫn đúng.
                by_keyword=goc.by_keyword,
                by_vector=goc.by_vector,
                keyword_rank=goc.keyword_rank,
                vector_rank=goc.vector_rank,
            )
        )

    if not ket_qua:
        logger.warning(
            "Rerank không trả candidate nào vượt chunk_filter_min_score=%.2f, giữ nguyên thứ tự",
            chunk_filter_min_score,
        )
        return RetrievalOutcome(
            candidates=gui_di,
            rerank_used=True,
            rerank_error=(
                f"chunk_filter_min_score={chunk_filter_min_score:.2f} loại hết candidate"
            ),
        )
    return RetrievalOutcome(candidates=ket_qua, rerank_used=True)
