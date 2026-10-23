"""Kiểu dữ liệu dùng chung cho mọi tầng truy xuất.

## Vì sao có file này

``Candidate`` là **một định nghĩa duy nhất** cho ``hybrid``, ``fact_lookup``,
``graph_query`` và tầng API admin. Nếu mỗi module tự khai kiểu riêng thì tầng API
phải viết nhiều hàm chuyển đổi và chúng sẽ lệch nhau.

Đặt ở file riêng thay vì trong ``retrieval.py``: ``retrieval.py`` sẽ import
``hybrid``, còn ``hybrid`` cần ``Candidate`` — để trong ``retrieval.py`` là **vòng
lặp import**.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Candidate:
    """Một đơn vị nội dung được truy xuất — một chunk của ``procedure_sections``.

    Trường ``score`` mang ý nghĩa khác nhau tuỳ ``source``:

    * ``keyword`` — BM25 score của Elasticsearch (không có cận trên, không so được
      với cosine)
    * ``vector``  — cosine trong ``0..1``
    * ``hybrid``  — điểm RRF, xem ``hybrid.reciprocal_rank_fusion``
    * ``rerank``  — ``relevance_score`` của ``qwen3-rerank``

    Vì các thang điểm này khác nhau, **không** so sánh ``score`` giữa hai ``source``
    khác nhau. So sánh chỉ có nghĩa trong cùng một lần truy xuất.
    """

    #: ``section_id`` — là ``_id`` trong Elasticsearch **và** ``section_id`` trong
    #: payload Qdrant, nên gộp được hai danh sách mà không cần khớp mờ.
    chunk_id: str
    procedure_code: str
    procedure_name: str
    section_type: str
    title: str
    content: str
    detail_url: str

    score: float = 0.0
    source: str = ""
    #: Chunk này do **BM25** tìm ra. Ở mode ``keyword`` luôn ``True``; ở ``hybrid`` cho
    #: biết nhánh nào đã đóng góp chunk vào kết quả trộn.
    by_keyword: bool = False
    #: Chunk này do **vector (Qdrant)** tìm ra.
    #:
    #: Vì sao cần hai cờ riêng thay vì ``source``: ``source`` bị RRF ghi đè thành
    #: ``"hybrid"``, nên mất thông tin chunk đến từ nhánh nào. Đo được là thông tin
    #: hữu ích: một chunk chỉ do BM25 tìm ra thường là nhờ trùng chuỗi chính xác (mã,
    #: số hiệu văn bản), còn chỉ do vector là nhờ ngữ nghĩa; cả hai là tín hiệu mạnh.
    by_vector: bool = False
    #: **Thứ hạng trong nhánh BM25** (1 = đứng đầu). ``None`` = nhánh này không tìm ra.
    #:
    #: Cần thứ hạng chứ không chỉ cờ đúng/sai: trên bộ dữ liệu nhỏ, hai nhánh lấy 30
    #: chunk mỗi bên nên **gần như mọi chunk đều có mặt ở cả hai** — cờ sẽ luôn là
    #: ``True/True`` và không phân biệt được gì. Thứ hạng cho biết chunk mạnh ở nhánh
    #: nào: ``BM25 #1 / vector #18`` khác hẳn ``BM25 #18 / vector #1``.
    keyword_rank: int | None = None
    #: **Thứ hạng trong nhánh vector**. ``None`` = nhánh này không tìm ra.
    vector_rank: int | None = None

    def as_dict(self) -> dict[str, Any]:
        """Dạng trả qua API admin.

        ``intent`` được gán bằng ``section_type`` để kiểu ``RetrievalCandidate`` phía
        frontend dùng được cho cả FAQ (``intent`` thật) và chunk (``section_type``)
        mà không phải thêm trường mới.
        """
        return {
            "id": self.chunk_id,
            "source": self.source,
            "score": round(self.score, 4),
            "passed": True,
            "intent": self.section_type,
            "section_type": self.section_type,
            "title": self.title,
            "content": self.content,
            "procedure_code": self.procedure_code,
            "procedure_name": self.procedure_name,
            "detail_url": self.detail_url,
            # Nguồn gốc từng nhánh — UI hiện hai nhãn "keyword" / "vector" kèm hạng.
            "by_keyword": self.by_keyword,
            "by_vector": self.by_vector,
            "keyword_rank": self.keyword_rank,
            "vector_rank": self.vector_rank,
        }


@dataclass(frozen=True, slots=True)
class RetrievalOutcome:
    """Kết quả một lần truy xuất, **kèm trạng thái của các bước phụ**.

    ## Vì sao cần ``rerank_used``

    Rerank là bước phụ thuộc API ngoài: nó có thể hỏng vì 403/rate limit, hết quota,
    hoặc timeout. Khi hỏng, ``reranker.rerank`` **giữ nguyên thứ tự trước đó** và chỉ
    ghi log — nhờ vậy truy vấn không chết. Nhưng hệ quả là **chất lượng giảm âm thầm**:

        câu ngoài phạm vi B9:  0,4493 (đã rerank)  →  0,0317 (rerank lỗi, điểm RRF)

    Điểm đổi 14 lần mà không có gì báo. Nếu không có cờ này, người kiểm thử sẽ ghi vào
    báo cáo những số liệu "hybrid" mà thực ra **chưa qua rerank**. Đó là loại sai lệch
    khó phát hiện nhất, nên phải hiện lên UI.

    ## ``gate_score`` và ``refused``

    Cổng từ chối dùng reranker để chấm **đúng một** tài liệu — candidate đứng đầu — rồi
    so với ``RERANKER_MIN_SCORE``. Đo trên 31 câu:

        câu trong phạm vi : 0,6306 – 0,9548
        câu ngoài phạm vi : 0,4493 – 0,5389

    Tách hoàn toàn ở 0,60. Cosine **không** làm được việc này: dải của nó chồng nhau
    (hợp lệ thấp nhất 0,5250 < rác cao nhất 0,5837), nên không ngưỡng nào tách được.

    Chỉ chấm 1 tài liệu nên tốn khoảng **200 token** mỗi câu, rẻ hơn ~15 lần so với
    rerank đầy đủ (15 tài liệu). Và vì **không đổi thứ tự** RRF, nó không làm hỏng độ
    chính xác mục — điều mà rerank đầy đủ đã làm (7/7 → 4/7).
    """

    candidates: list[Candidate]
    #: ``True`` nếu rerank đã chạy **thành công**. ``False`` = kết quả là thứ tự trước
    #: rerank (RRF hoặc điểm gốc).
    rerank_used: bool = False
    #: Thông báo lỗi của rerank (rỗng nếu không lỗi). Hiện lên UI để người kiểm thử biết.
    rerank_error: str = ""
    #: Điểm liên quan **cao nhất** trong ``GATE_SCORE_N`` tài liệu đầu (cổng từ chối).
    #: ``None`` = chưa chấm được, hoặc cổng bị bỏ qua có chủ ý. Đây là điểm cao nhất
    #: trong vài tài liệu đầu, **không** phải điểm của riêng tài liệu hạng 1 — RRF hạng 1
    #: chưa chắc là rerank tốt nhất.
    gate_score: float | None = None
    #: ``True`` = cổng từ chối đã chặn: ``candidates`` rỗng vì điểm liên quan quá thấp.
    refused: bool = False
    #: ``True`` = cổng **bị bỏ qua có chủ ý** vì câu hỏi đã định danh được thủ tục
    #: (nêu mã thủ tục tồn tại). Khác với ``gate_score is None`` do rerank lỗi — hai
    #: trường hợp này phải hiện khác nhau trên UI, nếu không người kiểm thử sẽ tưởng
    #: cổng hỏng.
    gate_skipped: bool = False
    #: Lỗi của từng nhánh tìm kiếm (ES/Qdrant). Rỗng = cả hai chạy bình thường.
    #: ``candidates=[]`` + ``errors`` khác nghĩa với "không có kết quả": executor phải
    #: ghi ``failed`` chứ không phải ``empty``.
    errors: list[str] = field(default_factory=list)
