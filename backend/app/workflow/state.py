"""Trạng thái workflow — **một** cấu trúc cho toàn bộ luồng Phase 13.

## Vì sao một cấu trúc duy nhất

Mỗi bước trong luồng (định danh, chọn nhánh, chạy nhánh, sinh câu trả lời, kiểm chứng) cần
đọc một phần kết quả của bước trước. Nếu truyền tham số rời rạc thì chữ ký hàm phình ra và
mỗi lần thêm thông tin là phải sửa mọi bước. Một trạng thái dùng chung giữ cho các bước chỉ
phụ thuộc vào **hợp đồng dữ liệu**, không phụ thuộc vào nhau.

## Sáu nhóm trường

    câu hỏi      | nội dung gốc, nội dung đã bỏ dấu, số thứ tự lượt
    định danh    | mã thủ tục, văn bản, thực thể đóng, kết quả định danh theo tên
    truy xuất    | bằng chứng, nhánh đã chọn, lý do, tín hiệu nhánh, cổng từ chối, hỏi lại
    sinh & kiểm  | câu trả lời cuối, trích dẫn, kết quả kiểm chứng
    điều khiển   | số lần leo thang, giới hạn, lỗi, nhánh đã đi qua, kết cục
    số đo        | thời gian từng bước, token, cờ nhúng, nguồn quyết định router

## Ba ràng buộc quan trọng

1. **Ghi lại được.** Trạng thái phải chuyển thẳng sang JSON mà không cần hàm đặc biệt — để
   ghi vết, để phát lại khi không có mạng, và để người chấm đọc lại được. Có bài kiểm riêng
   khẳng định điều này (``test_state_ghi_duoc_ra_json``).
2. **Mặc định đầy đủ.** :func:`new_state` cho ra trạng thái dùng được ngay, nên không bước nào
   phải tự kiểm tra "trường này có tồn tại chưa".
3. **Không có bộ nhớ hội thoại.** Theo quyết định của dự án: mỗi câu hỏi độc lập. Không có
   trường lịch sử các lượt trước, không có bộ lưu trạng thái giữa các lượt.

## Điều KHÔNG đặt ở đây

Vector thô của câu hỏi không nằm trong trạng thái (1024 số thực ≈ 10 KB mỗi lượt). Trạng thái
chỉ giữ **dấu vết** vector; vector thật nằm ở kho ngoài, tra theo dấu vết khi cần.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TypedDict

from backend.app.rag.evidence import Branch as Branch  # tái xuất cho tầng trên
from backend.app.rag.evidence import EvidenceItem
from backend.app.workflow.question_frame import (
    QUESTION_FRAME_SCHEMA_VERSION,
    AmbiguityInfo,
    AmbiguityKind,
    QuestionFrame,
    QuestionScope,
)


class RouterSource(StrEnum):
    """Quyết định chọn nhánh do đâu mà có.

    Cần phân biệt để đo: nếu phần lớn câu rơi vào ``RULE`` thì mô hình đang không dùng được;
    nếu phần lớn là ``LLM`` thì chi phí mô hình là chi phí thật của hệ thống.
    """

    NONE = ""
    LLM = "llm"
    RULE = "rule"


class BranchSignal(StrEnum):
    """Nhánh vừa chạy **trả lời được** hay **nói rằng nó không phù hợp**.

    Đây là đầu vào của bước leo thang: nhánh không tự quyết định chuyển sang nhánh khác,
    nó chỉ báo tín hiệu, và luật leo thang ở tầng trên đọc tín hiệu đó.
    """

    OK = "ok"
    #: Đồ thị nói câu hỏi thuộc nhóm **nội dung** — nên đi tìm kiếm lai.
    NOT_GRAPH = "not_graph"
    #: Đúng loại quan hệ nhưng thiếu mã thủ tục / số hiệu văn bản để bắt đầu.
    NEED_IDENTITY = "need_identity"
    #: Nhiều thủ tục cùng khớp — phải hỏi lại, không đoán.
    CLARIFY = "clarify"
    #: Chạy được nhưng không có dòng nào (khác với lỗi).
    EMPTY = "empty"
    ERROR = "error"


class Outcome(StrEnum):
    """Kết cục của **cả câu hỏi**, sau khi đã chạy hết luồng.

    Năm kết cục đều hợp lệ. Chỉ ``ANSWERED`` mới có câu trả lời cho người dùng; ba kết cục
    giữa đều có thông báo riêng, và ``ERROR`` là lỗi kỹ thuật.
    """

    ANSWERED = "answered"
    CLARIFY = "clarify"
    NEED_IDENTITY = "need_identity"
    ABSTAINED = "abstained"
    ERROR = "error"


class VerificationStatus(StrEnum):
    """Kết quả kiểm chứng sau khi sinh câu trả lời."""

    #: Chưa chạy (ví dụ kết cục là hỏi lại nên không có gì để kiểm).
    SKIPPED = "skipped"
    PASSED = "passed"
    #: Có chi tiết không khớp bằng chứng → chặn, không gửi cho người dùng.
    BLOCKED = "blocked"


class EntityRef(TypedDict):
    """Thực thể đóng khớp trong câu hỏi (cơ quan / cấp / lĩnh vực / nhóm lĩnh vực)."""

    kind: str
    value: str
    label: str


class Alternative(TypedDict):
    """Một lựa chọn khi định danh thủ tục bị mơ hồ."""

    code: str
    name: str
    score: float


class ResolutionInfo(TypedDict):
    """Kết quả **định danh thủ tục theo tên**, chạy một lần ở đầu luồng."""

    #: Mã người dùng **đã nêu** nhưng không tồn tại (đã chuẩn hoá). Dùng để nói đúng mã
    #: thay vì câu từ chối chung chung.
    asked: list[str]
    code: str
    name: str
    #: ``code`` · ``exact_name`` · ``vector`` · ``""`` (chưa xác định).
    method: str
    confidence: float
    #: ``True`` = nhiều thủ tục cùng khớp → phải hỏi lại.
    ambiguous: bool
    alternatives: list[Alternative]
    #: Ghi chú kỹ thuật (lý do mơ hồ, lỗi tìm vector…).
    note: str


class GateInfo(TypedDict):
    """Trạng thái cổng từ chối của nhánh tìm kiếm lai."""

    score: float
    #: ``True`` khi câu hỏi đã định danh được nên bỏ qua cổng để tiết kiệm.
    skipped: bool
    refused: bool
    reason: str


class ClarifyOption(TypedDict):
    """Một lựa chọn đưa cho người dùng khi phải hỏi lại."""

    value: str
    label: str
    hint: str


class ClarifyInfo(TypedDict):
    """Nội dung câu hỏi lại."""

    question: str
    options: list[ClarifyOption]


#: Chín khía cạnh dữ liệu hệ thống có — đúng bằng các giá trị ``section_type`` trong PostgreSQL.
#:
#: Danh sách **đóng** là chủ ý: mô hình chỉ được chọn trong đây, còn mã nguồn ánh xạ thẳng sang
#: ``section_type`` để truy xuất. Dữ liệu có thêm mục mới thì thêm một giá trị vào đây — đó là
#: cập nhật theo **dữ liệu**, không phải viết thêm luật đoán câu hỏi.
NEED_HOP_LE: tuple[str, ...] = (
    "required_documents",
    "steps",
    "submission_method",
    "processing_time",
    "fee",
    "result",
    "legal_basis",
    "requirements",
    "general_info",
)


class PartSpec(TypedDict):
    """Một ý trong câu hỏi: nội dung ngắn + khía cạnh cần truy xuất."""

    text: str
    need: tuple[str, ...]


class Citation(TypedDict):
    """Một nguồn được trích trong câu trả lời cuối."""

    procedure_code: str
    procedure_name: str
    detail_url: str
    #: Số hiệu văn bản pháp lý nếu trích dẫn là văn bản.
    document_code: str
    #: Mục nội dung của nguồn ("Phí, lệ phí"…), rỗng khi không xác định.
    section: str


class VerificationInfo(TypedDict):
    """Kết quả kiểm chứng sau sinh."""

    status: str
    #: Chi tiết từng chi tiết bị chặn — ghi cho người vận hành, không hiện cho người dân.
    issues: list[str]


class Timings(TypedDict):
    """Thời gian từng bước, tính bằng mili giây. Để biết chỗ nào chậm."""

    resolve_ms: int
    router_ms: int
    branch_ms: int
    generate_ms: int
    total_ms: int


class Tokens(TypedDict):
    """Số token đã dùng cho câu này. Nhúng **không** tính ở đây (xem ``embedding_used``)."""

    input: int
    output: int


class AgentState(TypedDict, total=False):
    """Trạng thái đi qua mọi bước của luồng.

    Mọi trường đều không bắt buộc ở mức kiểu, vì trạng thái được dựng dần trong luồng; dùng
    :func:`new_state` để có trạng thái đầy đủ ngay từ đầu.
    """

    # ── câu hỏi ──────────────────────────────────────────────────────────
    question: str
    #: Nội dung đã bỏ dấu, viết thường — dùng cho so khớp từ khoá.
    normalized_question: str
    turn_index: int

    # ── định danh (chạy MỘT lần, trước khi chọn nhánh) ───────────────────
    #: Mã thủ tục tìm được trong câu hỏi, theo thứ tự xuất hiện.
    codes: list[str]
    #: Mã văn bản pháp lý tìm được (đã chuẩn hoá).
    documents: list[str]
    #: Thực thể đóng khớp được; ``None`` khi không có.
    entity: EntityRef | None
    #: Có **nhiều** thực thể cùng khớp — cần hỏi lại. Bộ định danh đặt ``entity = None``
    #: trong trường hợp này, nên phải có cờ riêng, nếu không router không phân biệt được
    #: "câu không nêu thực thể" với "câu nêu nhiều thực thể".
    entity_ambiguous: bool
    #: Câu dùng đại từ chỉ định ("thủ tục này"…) mà không nêu thủ tục nào trước đó — cần hỏi
    #: lại, không được định danh bừa.
    needs_antecedent: bool
    resolution: ResolutionInfo

    # ── phân tích ý (do semantic parser trả) ─────────────────────────────
    #: Câu hỏi tách thành các ý, mỗi ý kèm khía cạnh cần truy xuất. Rỗng = câu một ý.
    parts: list[PartSpec]
    #: Biểu diễn ngữ nghĩa do semantic parser sinh; không chứa quyết định tool.
    question_frame: QuestionFrame
    #: Kết quả grounding từng mention của frame: mã thật, trạng thái, phương án.
    groundings: list[dict]
    #: RetrievalPlan do planner tất định sinh: ``{"tasks": [...], "unsupported": [...]}``.
    plan: dict
    #: Độ phủ theo từng request do executor tính: ``covered``/``empty``/``failed``/``unsupported``.
    coverage: list[dict]
    #: Ứng viên (giả thuyết) do grounding/resolver sinh — **không phải** bằng chứng.
    discovery: list[dict]
    #: Nhãn nguồn lực cho cả lượt: direct/composed/discovery/unsupported/clarify/out_of_scope.
    plan_class: str
    #: Vì sao chọn nhãn đó (để đọc trace, không hiện cho người dân).
    plan_class_reason: str
    #: Nhãn cho từng ý, cùng bộ giá trị — giữ chi tiết khi câu nhiều ý bị trộn trạng thái.
    request_plan_class: list[dict]
    #: Mã thủ tục mà câu hỏi nói tới, nếu mô hình xác định được.
    subjects: list[str]
    #: Khía cạnh **đã hỏi mà không có dữ liệu** — do mã nguồn tính, không do mô hình suy ra.
    thieu: list[str]
    #: ``True`` = **không** sinh câu trả lời trong đồ thị. Dùng cho đường streaming: đồ thị chạy
    #: tới bằng chứng, rồi nơi gọi tự stream bước sinh ra ngoài — nếu sinh trong đồ thị thì
    #: sinh hai lần, một lần bị bỏ.
    skip_generate: bool
    #: Dấu vết vector của câu hỏi; ``""`` = câu này không cần nhúng.
    vector_hash: str

    # ── truy xuất ────────────────────────────────────────────────────────
    evidence: list[EvidenceItem]
    #: Nhánh đã chọn; ``""`` = chưa chọn.
    branch: str
    #: Lý do chọn, dạng chuỗi ngắn đọc được.
    branch_reason: str
    #: Xem :class:`BranchSignal`.
    branch_signal: str
    gate: GateInfo
    clarify: ClarifyInfo
    #: Lời **từ chối** đọc được, chỉ có khi kết cục là "không trả lời được".
    #:
    #: Tách khỏi ``clarify`` là chủ ý: hỏi lại là *"tôi cần biết thêm"*, từ chối là *"dữ liệu
    #: của tôi không có"*. Gộp chung một trường thì giao diện không phân biệt được, và người
    #: dùng nhận một câu hỏi thay vì một lời giải thích.
    refusal: str

    # ── sinh & kiểm ──────────────────────────────────────────────────────
    #: Câu trả lời cho người dân, sinh từ **bằng chứng** (việc 13.13). Rỗng = chưa sinh.
    answer: str
    #: Vì sao không sinh được câu trả lời — để giao diện nói đúng lý do thay vì khung trống.
    answer_error: str
    final_answer: str
    #: Nguồn đã trích, **cùng thứ tự** với số hiệu ``[1]``, ``[2]``… trong ``answer``.
    citations: list[Citation]
    verification: VerificationInfo

    # ── điều khiển ───────────────────────────────────────────────────────
    retry_count: int
    max_retry: int
    error: str
    #: Các nhánh đã chạy qua, theo thứ tự — dùng để cấm leo thang vòng tròn.
    fallback_from: list[str]
    outcome: str

    # ── số đo ────────────────────────────────────────────────────────────
    timings: Timings
    tokens: Tokens
    #: ``True`` = câu này có nhúng câu hỏi (tối đa một lần).
    embedding_used: bool
    #: Xem :class:`RouterSource`.
    router_source: str
    #: Khi quyết định cuối cùng đến từ luật dự phòng, đây là lý do.
    router_fallback_reason: str


def new_state(question: str, *, turn_index: int = 1) -> AgentState:
    """Trạng thái đầy đủ cho một câu hỏi mới.

    Mọi trường đều có giá trị, nên không bước nào phải kiểm tra "trường này có chưa". Cố ý
    **không** tự chuẩn hoá câu hỏi ở đây: việc bỏ dấu thuộc tầng chuẩn hoá, và để nguyên ở
    bước này giúp phát hiện chỗ nào quên gọi chuẩn hoá.
    """
    return AgentState(
        question=question,
        normalized_question="",
        turn_index=turn_index,
        codes=[],
        documents=[],
        entity=None,
        entity_ambiguous=False,
        needs_antecedent=False,
        parts=[],
        groundings=[],
        plan={},
        coverage=[],
        discovery=[],
        plan_class="",
        plan_class_reason="",
        request_plan_class=[],
        question_frame=QuestionFrame(
            schema_version=QUESTION_FRAME_SCHEMA_VERSION,
            scope=QuestionScope.UNKNOWN,
            subject_mentions=[],
            requests=[],
            ambiguity=AmbiguityInfo(
                present=False,
                kind=AmbiguityKind.NONE,
                reason="",
            ),
        ),
        subjects=[],
        thieu=[],
        skip_generate=False,
        resolution=ResolutionInfo(
            asked=[],
            code="",
            name="",
            method="",
            confidence=0.0,
            ambiguous=False,
            alternatives=[],
            note="",
        ),
        vector_hash="",
        evidence=[],
        branch="",
        branch_reason="",
        branch_signal=BranchSignal.OK.value,
        gate=GateInfo(score=0.0, skipped=False, refused=False, reason=""),
        refusal="",
        clarify=ClarifyInfo(question="", options=[]),
        answer="",
        answer_error="",
        final_answer="",
        citations=[],
        verification=VerificationInfo(status=VerificationStatus.SKIPPED.value, issues=[]),
        retry_count=0,
        max_retry=2,
        error="",
        fallback_from=[],
        outcome=Outcome.ERROR.value,
        timings=Timings(resolve_ms=0, router_ms=0, branch_ms=0, generate_ms=0, total_ms=0),
        tokens=Tokens(input=0, output=0),
        embedding_used=False,
        router_source=RouterSource.NONE.value,
        router_fallback_reason="",
    )


#: Danh sách trường của trạng thái, cố định. Có bài kiểm so khớp để việc vô tình xoá một
#: trường bị phát hiện ngay — xoá trường là mất thông tin mà không ai báo lỗi.
STATE_FIELDS: frozenset[str] = frozenset(AgentState.__annotations__)
