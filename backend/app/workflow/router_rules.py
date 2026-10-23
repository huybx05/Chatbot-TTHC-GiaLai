"""Router bằng **luật** — đường dự phòng, đồng thời là mốc so sánh cho router mô hình.

## Vì sao vẫn cần router bằng luật

Quyết định của dự án: router dùng mô hình ngôn ngữ **trước**, luật chỉ chạy khi mô hình lỗi,
quá thời gian chờ, hoặc trả nhãn ngoài danh sách. Nhưng luật vẫn phải **đầy đủ**, vì:

* là bản dự phòng khi mạng hỏng — hệ thống vẫn phải trả lời được,
* là **mốc so sánh**: không có nó thì không biết router mô hình đáng chi phí hay không,
* là chỗ ghi lại **vì sao** một câu đi nhánh đó, để đọc lại và gỡ lỗi.

## Bảng quyết định

Xét **theo thứ tự**, dừng ở dòng đầu tiên khớp. Mỗi dòng kiểm được bằng code, không có
"tuỳ trường hợp".

| # | Điều kiện | Nhánh | Chắc? |
|---|---|---|---|
| 1 | Câu hỏi thuộc nhóm **nội dung** (hồ sơ, phí, thời hạn, trình tự…) | tìm kiếm lai | có |
| 2 | Có **mã thủ tục** và câu khớp một loại **quan hệ** của đồ thị | đồ thị | có |
| 3 | Có **mã thủ tục** và câu hỏi kiểu **"thủ tục này là gì"** | tra thuộc tính | có |
| 4 | Có **mã thủ tục**, nhưng câu không khớp loại nào ở trên | tìm kiếm lai | có |
| 5 | Không có mã; câu nêu **nhiều văn bản** cùng khớp | **hỏi lại** | có |
| 6 | Không có mã; câu nêu **nhiều thực thể** cùng khớp | **hỏi lại** | có |
| 7 | Không có mã; câu khớp một loại **quan hệ** (nhờ văn bản / thực thể / thống kê) | đồ thị | có |
| 8 | Không có mã, nhưng **định danh được đúng một thủ tục** theo tên | quay lại 2–4 | có |
| 9 | Không có mã; **nhiều thủ tục** cùng khớp tên | **hỏi lại** | có |
| 10 | Còn lại | tìm kiếm lai | **không chắc** |

## Vì sao thứ tự này

* **Nội dung trước tiên.** Đồ thị từ chối câu nội dung, nên đưa câu nội dung vào đó là
  chắc chắn hỏng. Đo được: câu *"thủ tục này cần hồ sơ gì"* rơi vào đồ thị thì trả
  ``NOT_GRAPH`` rồi phải leo thang — mất một vòng.
* **Có mã thì mã thắng.** Mã là định danh chắc chắn nhất; khi đã có mã thì chuyện "nhiều văn
  bản cùng khớp" không còn quan trọng.
* **Mơ hồ thì hỏi lại, không đoán.** Nhiều văn bản hoặc nhiều thủ tục cùng khớp mà tự chọn
  một cái là trả lời về sai đối tượng — kiểu sai nguy hiểm nhất vì trông như đã trả lời.
* **"Thủ tục này là gì" mới đi tra thuộc tính.** Câu hỏi có mã mà khớp được một loại quan hệ
  thì đồ thị trả lời **đúng thứ được hỏi** và gọn hơn: *"do cơ quan nào ban hành"* chỉ trả
  một dòng, thay vì cả sáu trường định danh.
* **Dòng cuối là chỗ duy nhất "không chắc".** Nếu tỉ lệ câu rơi vào đây cao thì mô hình ngôn
  ngữ có việc thật để làm — và đó là con số cần đo.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.app.rag import graph_query
from backend.app.rag.evidence import Branch
from backend.app.rag.graph_query import EntityMatch
from backend.app.rag.resolve import Resolution
from backend.app.workflow.state import (
    BranchSignal,
    ClarifyInfo,
    ClarifyOption,
    PartSpec,
)

#: Cụm từ cho thấy người dùng hỏi **thông tin định danh** của một thủ tục, không hỏi một
#: quan hệ cụ thể. Chỉ dùng khi **không** khớp loại quan hệ nào — nhờ vậy câu *"do cơ quan
#: nào ban hành"* vẫn đi đồ thị (trả lời gọn hơn), còn *"thủ tục này là gì"* đi tra thuộc tính.
METADATA_SIGNALS: tuple[str, ...] = (
    "la gi",
    "thong tin",
    "gioi thieu",
    "tom tat",
    "so quyet dinh",
    "link",
    "duong dan",
    "chi tiet",
    "tra cuu",
)


@dataclass(slots=True)
class RouterDecision:
    """Kết quả chọn nhánh. Không bao giờ ném lỗi — luôn có lý do."""

    #: Một trong bốn nhánh; ``""`` = không nhánh nào, phải hỏi lại.
    branch: str = ""
    #: Xem ``BranchSignal``. ``CLARIFY`` = phải hỏi lại trước khi chạy nhánh nào.
    signal: str = BranchSignal.OK.value
    #: Lý do đọc được, ghi vào dòng vết. Đây là thứ để gỡ lỗi định tuyến.
    reason: str = ""
    #: ``False`` = luật không chắc, nên để mô hình quyết định (khi có mô hình).
    confident: bool = True
    #: Nội dung câu hỏi lại, chỉ có khi ``signal`` là ``CLARIFY``.
    clarify: ClarifyInfo = field(default_factory=lambda: ClarifyInfo(question="", options=[]))

    # ── nguồn và chi phí (chỉ có nghĩa với router mô hình) ───────────────
    #: ``"llm"`` hoặc ``"rule"``. Ghi lại để biết câu nào đã phải dùng mô hình.
    source: str = "rule"
    #: Độ trễ của lần gọi mô hình (0 với router luật).
    ms: int = 0
    #: Token vào/ra lấy từ ``usage`` của API. 0 nếu không có.
    tokens_in: int = 0
    tokens_out: int = 0
    #: Phần ``tokens_in`` được phục vụ từ **prompt cache** của nhà cung cấp.
    #:
    #: Đo được trên endpoint Qwen MaaS: 3 200 / 3 375 token vào (95%) đến từ cache sau hai
    #: lần gọi đầu. Không ghi lại thì không biết cache có tác dụng hay không, và cũng không
    #: biết khi nào nó **mất** tác dụng (ví dụ ai đó chèn ngày giờ vào đầu prompt).
    tokens_cached: int = 0
    #: Tên mô hình đã dùng — để biết kết quả thuộc phiên bản nào.
    model: str = ""
    #: Câu hỏi được tách thành các ý, mỗi ý kèm khía cạnh cần truy xuất. Rỗng = không tách
    #: (câu một ý, hoặc mô hình không trả về). Phần tử dạng ``{"text", "need"}``.
    parts: tuple[PartSpec, ...] = ()
    #: Mã thủ tục mà câu hỏi nói tới, nếu mô hình xác định được (tối đa 3).
    subjects: tuple[str, ...] = ()
    #: ``True`` = quyết định này lấy từ **cache**, không gọi mô hình lần nữa. Khi đó ``ms``,
    #: ``tokens_in``, ``tokens_out`` đều bằng 0 vì lượt này **không tốn gì**.
    cached: bool = False

    @property
    def can_chay(self) -> bool:
        """Có nhánh để chạy hay phải hỏi lại trước."""
        return bool(self.branch)


def _nhanh(branch: Branch, reason: str, *, confident: bool = True) -> RouterDecision:
    return RouterDecision(
        branch=branch.value,
        signal=BranchSignal.OK.value,
        reason=reason,
        confident=confident,
        source="rule",
    )


def _hoi_lai(reason: str, question: str, options: list[ClarifyOption]) -> RouterDecision:
    return RouterDecision(
        branch="",
        signal=BranchSignal.CLARIFY.value,
        reason=reason,
        confident=True,
        clarify=ClarifyInfo(question=question, options=options),
    )


def _entity_match(entity: dict[str, str] | None) -> EntityMatch | None:
    if not entity:
        return None
    return EntityMatch(
        kind=str(entity.get("kind") or ""),
        value=str(entity.get("value") or ""),
        label=str(entity.get("label") or ""),
    )


def _phuong_an_van_ban(documents: list[str]) -> list[ClarifyOption]:
    """Mỗi văn bản cùng khớp thành một lựa chọn để người dùng chọn."""
    return [ClarifyOption(value=ma, label=ma, hint="văn bản pháp lý") for ma in documents[:5]]


def _phuong_an_thu_tuc(resolution: Resolution) -> list[ClarifyOption]:
    """Mỗi thủ tục cùng khớp thành một lựa chọn."""
    return [
        ClarifyOption(value=ma, label=(ten or ma), hint=f"mã {ma}")
        for ma, ten, _diem in resolution.procedure.alternatives[:5]
    ]


def decide(resolution: Resolution, *, question: str | None = None) -> RouterDecision:
    """Chọn nhánh cho một câu hỏi đã định danh.

    Nhận :class:`~backend.app.rag.resolve.Resolution` thay vì trạng thái workflow, để kiểm
    thử được trước khi đồ thị tồn tại (việc 13.6).
    """
    cau = question if question is not None else resolution.question

    # ── Dòng 0: đại từ chỉ định không có tiền ngữ → hỏi lại ──────────────
    #
    # Hệ thống không có bộ nhớ hội thoại, nên "thủ tục này" không trỏ vào đâu được. Đo được:
    # câu *"Thủ tục này cần những giấy tờ nào?"* từng bị gán cho thủ tục hôn nhân và trả 51
    # đoạn văn về hôn nhân. Hỏi lại là câu trả lời duy nhất đúng.
    if resolution.needs_antecedent:
        return _hoi_lai(
            "câu dùng đại từ chỉ định nhưng không nêu thủ tục nào trước đó",
            "Bạn muốn hỏi thủ tục nào? Hãy cho tôi mã hoặc tên thủ tục.",
            [],
        )

    # ── Dòng 1: câu nội dung luôn đi tìm kiếm lai ────────────────────────
    if graph_query.is_content_question(cau):
        return _nhanh(
            Branch.HYBRID,
            "câu hỏi thuộc nhóm nội dung (hồ sơ / phí / thời hạn / trình tự)",
        )

    # ── Dòng 2–4: đã có mã thủ tục ───────────────────────────────────────
    if resolution.ma:
        return _theo_ma(resolution, cau)

    # ── Dòng 5: nhiều văn bản cùng khớp → hỏi lại ────────────────────────
    if len(resolution.documents) > 1:
        return _hoi_lai(
            f"có {len(resolution.documents)} văn bản pháp lý cùng khớp",
            "Bạn muốn hỏi văn bản nào?",
            _phuong_an_van_ban(resolution.documents),
        )

    # ── Dòng 6: nhiều thực thể cùng khớp → hỏi lại ───────────────────────
    if resolution.entity_ambiguous:
        return _hoi_lai(
            "có nhiều thực thể cùng khớp",
            "Bạn muốn hỏi giá trị nào?",
            [],
        )

    # ── Dòng 7: khớp một loại quan hệ nhờ văn bản / thực thể / thống kê ──
    spec = _khop_quan_he(resolution, cau)
    if spec is not None:
        return _nhanh(
            Branch.GRAPH,
            f"khớp loại quan hệ **{spec.title}** (không cần mã thủ tục)",
        )

    # ── Dòng 9: nhiều thủ tục cùng khớp tên → hỏi lại ────────────────────
    if resolution.procedure.ambiguous:
        return _hoi_lai(
            "có nhiều thủ tục cùng khớp tên",
            "Bạn muốn hỏi thủ tục nào?",
            _phuong_an_thu_tuc(resolution),
        )

    # ── Dòng 10: không xác định được gì ──────────────────────────────────
    return _nhanh(
        Branch.HYBRID,
        "không khớp loại quan hệ nào — để tìm kiếm lai trả lời",
        confident=False,
    )


def _theo_ma(resolution: Resolution, cau: str) -> RouterDecision:
    """Dòng 2–4: đã có mã thủ tục (nêu trực tiếp, hoặc tìm được theo tên)."""
    nguon = "mã nêu trực tiếp" if resolution.codes else "mã tìm được theo tên"

    spec = _khop_quan_he(resolution, cau)
    if spec is not None:
        return _nhanh(
            Branch.GRAPH,
            f"{nguon}; khớp loại quan hệ **{spec.title}**",
        )

    if any(graph_query.has_phrase(cau, x) for x in METADATA_SIGNALS):
        return _nhanh(
            Branch.FACT_LOOKUP,
            f"{nguon}; hỏi thông tin định danh của thủ tục",
        )

    return _nhanh(
        Branch.HYBRID,
        f"{nguon}; không khớp loại quan hệ nào nên để tìm kiếm lai",
    )


def _khop_quan_he(resolution: Resolution, cau: str) -> graph_query.IntentSpec | None:
    """Loại quan hệ đầu tiên mà câu hỏi khớp, với những gì đã định danh được."""
    specs = graph_query.classify_all(
        cau,
        has_code=bool(resolution.ma),
        has_document=bool(resolution.documents),
        entity=_entity_match(resolution.entity),
    )
    if not specs:
        return None
    # Bỏ ``SUBGRAPH`` (không có từ khoá, khớp mọi câu) trừ khi nó là cái duy nhất **và**
    # đã có mã: lúc đó "cho tôi mọi quan hệ" là yêu cầu thật.
    # Chỉ nhận khi có hình dạng **có từ khoá** khớp thật. Không còn đường "không khớp gì thì
    # lấy cái cuối" — chính đường đó từng khiến câu "thủ tục 1.115374 là gì?" bị coi là hỏi
    # toàn cảnh quan hệ (``SUBGRAPH`` khi đó không có từ khoá nào nên khớp mọi câu).
    return specs[0] if specs else None


def decide_all(resolution: Resolution, *, question: str | None = None) -> list[str]:
    """Các nhánh **có thể** đúng, theo thứ tự ưu tiên — dùng khi cần leo thang.

    Không dùng để chạy: chỉ ``decide`` mới chọn một nhánh. Hàm này để bước leo thang biết
    nhánh nào còn đáng thử sau khi nhánh đầu không trả lời được.
    """
    cau = question if question is not None else resolution.question
    ra: list[str] = []
    if graph_query.is_content_question(cau):
        return [Branch.HYBRID.value]

    if _khop_quan_he(resolution, cau) is not None:
        ra.append(Branch.GRAPH.value)
    if resolution.ma:
        ra.append(Branch.FACT_LOOKUP.value)
    ra.append(Branch.HYBRID.value)
    return ra
