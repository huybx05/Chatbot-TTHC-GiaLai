"""Hợp đồng **bằng chứng chung** cho ba nhánh truy xuất.

## Vì sao cần kiểu chung

Bốn nhánh đang trả bốn kiểu khác nhau: thuộc tính thủ tục từ PostgreSQL, bằng chứng đồ thị
từ Neo4j, đoạn văn từ Elasticsearch + Qdrant, và câu hỏi thường gặp từ Qdrant. Nếu bước sinh
câu trả lời đọc trực tiếp bốn kiểu đó thì nó phải có bốn nhánh rẽ — đúng loại lỗi đã làm
trang quản trị trắng ba lần khi có ba nơi cùng dựng phản hồi.

Nên mọi nhánh quy về **một** kiểu. Thêm nhánh mới về sau chỉ cần thêm một bộ chuyển, không
phải sửa bước sinh.

## Quan hệ với trạng thái workflow

Kiểu này được khai báo ở đây (không phải trong tệp trạng thái) vì nó là hợp đồng của tầng
truy xuất. Trạng thái chỉ **chứa** một danh sách những mục như vậy.

Bốn bộ chuyển từ kết quả thô của từng nhánh sang kiểu này thuộc việc 13.2.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Any, TypedDict

from backend.app.rag.contracts import ResultKind

if TYPE_CHECKING:
    #: Chỉ dùng cho gợi ý kiểu. Cố ý **không** nạp lúc chạy: tệp này là hợp đồng dữ liệu
    #: dùng chung, nạp bốn nhánh truy xuất vào đây sẽ tạo vòng import
    #: (nhánh → hợp đồng → nhánh).
    from backend.app.rag.fact_lookup import ProcedureFact
    from backend.app.rag.graph_query import GraphEvidence
    from backend.app.rag.types import Candidate


class Branch(StrEnum):
    """Bốn nhánh truy xuất. Danh sách **đóng** — router chỉ được trả một trong bốn.

    Khai báo ở tệp hợp đồng dữ liệu (không phải ở tầng workflow) vì mỗi mục bằng chứng phải
    ghi được nó đã do nhánh nào tạo ra. Trạng thái workflow nạp lại từ đây, nên chỉ có một
    nguồn sự thật.
    """

    FACT_LOOKUP = "fact_lookup"
    GRAPH = "graph"
    HYBRID = "hybrid"


class EvidenceKind(StrEnum):
    """Bằng chứng thuộc loại nào — quyết định cách bước sinh câu trả lời đọc nó."""

    #: Sáu thuộc tính định danh của một thủ tục (mã, tên, cấp, cơ quan, số quyết định…).
    FACT = "fact"
    #: Quan hệ trong đồ thị tri thức (cơ quan, văn bản căn cứ, kết quả, phân loại…).
    GRAPH = "graph"
    #: Đoạn văn tìm được bằng từ khoá, vector, hoặc trộn hai cách.
    CHUNK = "chunk"
    #: **Ứng viên**, không phải bằng chứng. Chỉ để kiểm tra hợp đồng: bước sinh câu trả lời
    #: phải bỏ qua loại này, không bao giờ đưa vào ngữ cảnh.
    CANDIDATE = "candidate"
    #: **Mục nội dung lấy thẳng từ PostgreSQL theo khía cạnh câu hỏi** — bước bổ sung cho câu
    #: nhiều ý. Khác ``FACT`` (sáu trường định danh) và khác ``CHUNK`` (kết quả tìm kiếm).
    SECTION = "section"


class Provenance(StrEnum):
    """Bằng chứng được **lấy ra từ đâu** — khác ``source`` (nhánh nào tạo ra nó)."""

    POSTGRES = "postgres"
    NEO4J = "neo4j"
    ES_QDRANT = "es+qdrant"


class EvidenceItem(TypedDict, total=False):
    """Một mục bằng chứng, đã chuẩn hoá.

    Mọi trường đều không bắt buộc vì bốn nhánh có lượng thông tin khác nhau, nhưng
    ``kind`` là trường **bắt buộc trên thực tế**: bước sinh câu trả lời dựa vào nó để
    biết đang đọc loại gì.
    """

    #: Bắt buộc. Xem :class:`EvidenceKind`.
    kind: str
    procedure_code: str
    procedure_name: str
    #: Mã văn bản/quyết định khi evidence là văn bản pháp lý.
    document_code: str
    #: Đường dẫn nguồn trên cổng dịch vụ công — **không bao giờ** để mô hình tự tạo.
    detail_url: str
    #: Loại mục của đoạn văn (``FEE``, ``STEPS``…) hoặc loại thông tin của bằng chứng đồ thị.
    section_type: str
    title: str
    content: str
    score: float
    #: Nhánh đã tạo ra mục này (trùng với ``Branch`` trong trạng thái).
    source: str
    #: Đoạn này do nhánh từ khoá tìm ra — giao diện dùng để hiện nhãn nguồn.
    by_keyword: bool
    #: Đoạn này do nhánh vector tìm ra.
    by_vector: bool
    #: Thứ hạng trong **nhánh từ khoá** (1 = cao nhất); ``None`` = nhánh đó không tìm ra.
    keyword_rank: int | None
    #: Thứ hạng trong **nhánh vector**; ``None`` = nhánh đó không tìm ra.
    vector_rank: int | None
    #: Xem :class:`Provenance`.
    provenance: str
    #: Câu hỏi nhiều ý: mục này thuộc phần thứ mấy (bắt đầu từ 1; 0 = không chia phần).
    part_index: int
    #: Tiêu đề phần, để bước sinh câu trả lời đặt đúng mục ("Cơ quan liên quan"…).
    part_title: str
    #: Hai lớp kết quả theo hợp đồng: ``verified_evidence`` hoặc ``discovery``.
    result_kind: str
    #: ``True`` = đã neo vào mã/thực thể thật rồi truy xuất có ràng buộc.
    verified: bool
    #: Vì sao mục này được coi là đã kiểm (mã thủ tục, section theo mã, Graph theo neo…).
    verification: str
    #: Metadata block/case của chunk (``case_order``, ``case_name``...).
    metadata: dict[str, Any]
    #: Quan hệ thành phần: tên thành phần tại thời điểm nối (khác tên proc hiện hành).
    component_name: str
    #: Mã nguồn của quan hệ, dùng khi mã cũ đã được thay bằng mã mới.
    source_code: str
    #: URL của trang DVC ghi nhận quan hệ thành phần.
    source_url: str


# ══════════════════════════════════════════════════════════════════════════
# BỐN BỘ CHUYỂN — từ kết quả thô của mỗi nhánh sang kiểu chung
# ══════════════════════════════════════════════════════════════════════════


def _items(kind: EvidenceKind, nhan: list[EvidenceItem]) -> list[EvidenceItem]:
    """Gắn ``kind`` cho mọi mục rồi trả lại — tránh lặp ở cả bốn bộ chuyển."""
    for muc in nhan:
        muc["kind"] = kind.value
    return nhan


def _content_tu_cot(row: dict[str, str], columns: Sequence[tuple[str, str, bool]]) -> str:
    """Ghép nội dung một dòng theo **nhãn tiếng Việt** của cột.

    Không dùng tên khoá thô: bằng chứng là thứ mô hình sẽ đọc, để ``vai_tro`` trong đó là
    mời mô hình viết ra ``vai_tro`` trong câu trả lời.
    """
    nhan = {khoa: nhan_cot for khoa, nhan_cot, _tach in columns}
    phan = [
        f"{nhan.get(khoa, khoa)}: {gia_tri}"
        for khoa, gia_tri in row.items()
        if gia_tri and khoa != "detail_url"
    ]
    return " · ".join(phan)


def from_fact(fact: ProcedureFact) -> list[EvidenceItem]:
    """Thuộc tính định danh của một thủ tục → **một** mục bằng chứng.

    Giữ đủ sáu trường trong một mục (thay vì sáu mục) vì chúng luôn được dùng cùng nhau:
    nêu mã mà không nêu tên thì người đọc không đối chiếu được, nêu tên mà không có đường
    dẫn thì không kiểm chứng được.
    """
    dong = [
        f"Mã thủ tục: {fact.ma_thu_tuc}",
        f"Tên thủ tục: {fact.ten_thu_tuc}",
        f"Cấp thực hiện: {', '.join(fact.cap_thuc_hien)}" if fact.cap_thuc_hien else "",
        f"Cơ quan ban hành: {fact.co_quan_ban_hanh}" if fact.co_quan_ban_hanh else "",
        f"Số quyết định: {fact.so_quyet_dinh}" if fact.so_quyet_dinh else "",
        # Đường dẫn phải nằm **trong** bằng chứng: đó là chỗ mọi nhánh đều đi qua, nên câu
        # trả lời luôn có link để đối chiếu — kể cả nhánh thuộc tính.
        f"Xem chi tiết: {fact.detail_url}" if fact.detail_url else "",
    ]
    return _items(
        EvidenceKind.FACT,
        [
            EvidenceItem(
                procedure_code=fact.ma_thu_tuc,
                procedure_name=fact.ten_thu_tuc,
                document_code="",
                detail_url=fact.detail_url,
                section_type="METADATA",
                title=fact.ten_thu_tuc,
                content="\n".join(d for d in dong if d),
                score=0.0,
                source=Branch.FACT_LOOKUP.value,
                by_keyword=False,
                by_vector=False,
                provenance=Provenance.POSTGRES.value,
                part_index=0,
                part_title="",
                result_kind=ResultKind.VERIFIED.value,
                verified=True,
                verification="postgres_fact_by_code",
                metadata={},
                component_name="",
                source_code="",
                source_url="",
            )
        ],
    )


def _graph_identity(
    row: dict[str, Any],
    *,
    subject: str,
    evidence: Any,
) -> dict[str, str]:
    """Chuẩn hóa định danh một dòng Graph, kể cả dòng thành phần.

    Thủ tục thành phần có ``ma_thanh_phan``/``ten_thanh_phan``; thủ tục cha
    (chiều ngược) có ``ma_thu_tuc``/``ten``. Không dùng tên node cha làm tên
    của thủ tục con.
    """
    code = str(
        row.get("ma_thanh_phan")
        or row.get("ma_thu_tuc")
        or row.get("ma")
        or getattr(evidence, "procedure_code", "")
        or ""
    )
    name = str(
        row.get("ten_thanh_phan")
        or row.get("ten")
        or subject
        or ""
    )
    return {
        "procedure_code": code,
        "procedure_name": name,
        "detail_url": str(
            row.get("detail_url") or getattr(evidence, "detail_url", "") or ""
        ),
        "component_name": str(row.get("ten_goi") or ""),
        "source_code": str(row.get("source_code") or ""),
        "source_url": str(row.get("source_url") or ""),
    }


def _graph_metadata(evidence: Any, subject: str) -> dict[str, str]:
    if (getattr(evidence, "template", "") or getattr(evidence, "intent", "")) != (
        "PROCEDURE_RELATIONS"
    ):
        return {}
    return {
        "subject_code": str(getattr(evidence, "procedure_code", "") or ""),
        "subject_name": subject,
    }


def from_graph(evidence: GraphEvidence) -> list[EvidenceItem]:
    """Bằng chứng đồ thị → danh sách mục, giữ **nhãn phần** khi câu hỏi nhiều ý.

    Câu hỏi nhiều ý sinh ra bằng chứng nhiều phần (cơ quan / phân loại / kết quả…). Nếu trải
    phẳng mà bỏ nhãn phần thì bước sinh câu trả lời không biết mục nào thuộc ý nào, và sẽ
    gộp chúng thành một đoạn văn — đúng lỗi ta vừa sửa ở tầng đồ thị.

    Bằng chứng rỗng (đồ thị từ chối, hỏi lại, thiếu định danh) trả danh sách rỗng: đó là
    thông tin "không có bằng chứng", không phải lỗi.
    """
    ra: list[EvidenceItem] = []
    subject = str(getattr(evidence, "subject", "") or "")

    if evidence.parts:
        for chi_so, part in enumerate(evidence.parts, start=1):
            for row in part.rows:
                identity = _graph_identity(row, subject=subject, evidence=evidence)
                ra.append(
                    EvidenceItem(
                        procedure_code=identity["procedure_code"],
                        procedure_name=identity["procedure_name"],
                        detail_url=identity["detail_url"],
                        document_code=str(
                            row.get("document_code") or evidence.document_code or ""
                        ),
                        section_type=part.intent,
                        title=part.title,
                        content=_content_tu_cot(row, part.columns),
                        score=0.0,
                        source=Branch.GRAPH.value,
                        by_keyword=False,
                        by_vector=False,
                        provenance=Provenance.NEO4J.value,
                        part_index=chi_so,
                        part_title=part.title,
                        result_kind=ResultKind.VERIFIED.value,
                        verified=True,
                        verification="graph_template_with_anchor",
                        metadata=_graph_metadata(evidence, subject),
                        component_name=identity["component_name"],
                        source_code=identity["source_code"],
                        source_url=identity["source_url"],
                    )
                )
        return _items(EvidenceKind.GRAPH, ra)

    for row in evidence.rows:
        identity = _graph_identity(row, subject=subject, evidence=evidence)
        ra.append(
            EvidenceItem(
                procedure_code=identity["procedure_code"],
                procedure_name=identity["procedure_name"],
                detail_url=identity["detail_url"],
                document_code=str(
                    row.get("document_code") or evidence.document_code or ""
                ),
                section_type=evidence.template or evidence.intent,
                title=evidence.title,
                content=_content_tu_cot(row, evidence.columns),
                score=0.0,
                source=Branch.GRAPH.value,
                by_keyword=False,
                by_vector=False,
                provenance=Provenance.NEO4J.value,
                part_index=0,
                part_title="",
                result_kind=ResultKind.VERIFIED.value,
                verified=True,
                verification="graph_template_with_anchor",
                metadata=_graph_metadata(evidence, subject),
                component_name=identity["component_name"],
                source_code=identity["source_code"],
                source_url=identity["source_url"],
            )
        )
    return _items(EvidenceKind.GRAPH, ra)


def from_chunks(candidates: Sequence[Candidate]) -> list[EvidenceItem]:
    """Đoạn văn tìm được → danh sách mục, **giữ** hai cờ từ khoá/vector.

    Giữ cờ vì giao diện đang hiện nhãn nguồn và vì chúng là bằng chứng cho việc tune trọng
    số trộn: một đoạn chỉ do vector tìm ra khác hẳn một đoạn cả hai bên cùng tìm ra.
    """
    ra: list[EvidenceItem] = []
    for c in candidates:
        if not c.chunk_id:
            continue
        ra.append(
            EvidenceItem(
                procedure_code=c.procedure_code,
                procedure_name=c.procedure_name,
                document_code="",
                detail_url=c.detail_url,
                section_type=c.section_type,
                title=c.title,
                content=c.content,
                score=float(c.score),
                source=Branch.HYBRID.value,
                by_keyword=bool(c.by_keyword),
                by_vector=bool(c.by_vector),
                keyword_rank=c.keyword_rank,
                vector_rank=c.vector_rank,
                provenance=Provenance.ES_QDRANT.value,
                part_index=0,
                part_title="",
                # Đoạn văn tìm được **chưa** phải bằng chứng cho tới khi được neo vào một mã
                # thủ tục đã xác thực (executor nâng cấp bằng ``mark_verified``).
                result_kind=ResultKind.DISCOVERY.value,
                verified=False,
                verification="chunk_search_without_anchor",
                metadata={},
                component_name="",
                source_code="",
                source_url="",
            )
        )
    return _items(EvidenceKind.CHUNK, ra)


def from_sections(rows: Sequence[dict[str, Any]]) -> list[EvidenceItem]:
    """Mục nội dung đọc từ PostgreSQL theo khía cạnh → mục bằng chứng.

    ``section_type`` giữ **nguyên** giá trị dữ liệu (``PROCESSING_TIME``…), để bước kiểm phủ so
    khớp được với khía cạnh mà router yêu cầu.
    """
    ra: list[EvidenceItem] = []
    for r in rows:
        noi_dung = " ".join(str(r.get("content") or "").split())
        if not noi_dung:
            continue
        ra.append(
            EvidenceItem(
                procedure_code=str(r.get("procedure_code") or ""),
                procedure_name=str(r.get("procedure_name") or ""),
                document_code="",
                detail_url=str(r.get("detail_url") or ""),
                section_type=str(r.get("section_type") or ""),
                title=str(r.get("title") or ""),
                content=noi_dung,
                score=0.0,
                source=Branch.HYBRID.value,
                by_keyword=False,
                by_vector=False,
                provenance=Provenance.POSTGRES.value,
                part_index=0,
                part_title="",
                result_kind=ResultKind.VERIFIED.value,
                verified=True,
                verification="postgres_section_by_code_and_facet",
                metadata=dict(r.get("metadata") or {}),
                component_name="",
                source_code="",
                source_url="",
            )
        )
    return _items(EvidenceKind.SECTION, ra)


#: Nguồn có bằng chứng trực tiếp/đã neo được ưu tiên hơn kết quả tìm kiếm.
_SOURCE_PRIORITY = {
    Branch.FACT_LOOKUP.value: 4,
    Branch.GRAPH.value: 4,
    Branch.HYBRID.value: 3,
    "section": 3,
    "chunk": 2,
}


def _dedup_key(item: EvidenceItem) -> tuple[str, ...]:
    return (
        str(item.get("procedure_code") or ""),
        str(item.get("section_type") or ""),
        " ".join(str(item.get("content") or "").split()),
        str(item.get("component_name") or ""),
        str(item.get("source_url") or ""),
        str(item.get("part_index") or 0),
    )


def deduplicate_evidence(items: Sequence[EvidenceItem]) -> list[EvidenceItem]:
    """Hợp nhất bằng chứng trùng, giữ nguồn có độ tin cậy cao hơn.

    Không gộp hai thủ tục khác nhau hoặc hai khía cạnh khác nhau. Các cờ
    ``by_keyword``/``by_vector`` và rank được hợp nhất để không mất provenance
    của nhánh còn lại.
    """
    chosen: dict[tuple[str, ...], EvidenceItem] = {}
    order: list[tuple[str, ...]] = []

    for item in items:
        key = _dedup_key(item)
        current = chosen.get(key)
        if current is None:
            chosen[key] = dict(item)
            order.append(key)
            continue

        current_priority = _SOURCE_PRIORITY.get(str(current.get("source") or ""), 0)
        item_priority = _SOURCE_PRIORITY.get(str(item.get("source") or ""), 0)
        if item_priority > current_priority:
            chosen[key] = dict(item)
            current = chosen[key]
        current["by_keyword"] = bool(current.get("by_keyword")) or bool(
            item.get("by_keyword")
        )
        current["by_vector"] = bool(current.get("by_vector")) or bool(
            item.get("by_vector")
        )
        if current.get("keyword_rank") is None:
            current["keyword_rank"] = item.get("keyword_rank")
        if current.get("vector_rank") is None:
            current["vector_rank"] = item.get("vector_rank")
        if not current.get("component_name"):
            current["component_name"] = item.get("component_name", "")
        if not current.get("source_code"):
            current["source_code"] = item.get("source_code", "")
        if not current.get("source_url"):
            current["source_url"] = item.get("source_url", "")

    return [chosen[key] for key in order]
