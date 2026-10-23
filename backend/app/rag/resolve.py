"""Bộ định danh **thống nhất** — chạy một lần cho mỗi câu hỏi.

## Vì sao phải gom về một chỗ

Bốn khả năng định danh đang nằm rải ở ba tệp khác nhau:

* nhận mã thủ tục — ``fact_lookup`` (regex + PostgreSQL),
* nhận số hiệu và tên văn bản pháp lý — ``graph_query`` (RAM, 74 văn bản),
* nhận thực thể đóng: cơ quan / cấp / lĩnh vực / nhóm — ``graph_query`` (RAM),
* định danh thủ tục theo tên — ``resolver`` (khớp nguyên tên, rồi vector).

Nếu router và từng nhánh tự gọi lại các bước đó thì mỗi câu có thể **nhúng nhiều lần** và
các bước có thể ra kết quả khác nhau. Gộp lại thành một lần chạy không chỉ nhanh hơn: nó
làm cho "câu này nói về thủ tục nào" trở thành **một sự thật duy nhất** trong suốt lượt.

## Nơi duy nhất được nhúng câu hỏi

Quyết định của dự án: vector thô **không** nằm trong trạng thái (1024 số thực ≈ 10 KB mỗi
lượt). Trạng thái chỉ giữ **dấu vết**; vector thật nằm trong kho nhỏ ở tệp này, tra theo dấu
vết. Nhờ vậy:

* trạng thái ghi vết và phát lại được,
* nhánh tìm kiếm lai dùng lại đúng vector đã tính, **không nhúng lần hai**,
* đếm được số lần nhúng cho mỗi câu (phải là 0 hoặc 1).

## Điều kiện dừng của từng bước

Định danh theo đúng thứ tự **rẻ trước, đắt sau**, dừng ngay khi đủ:

    ① mã thủ tục có trong câu            → 0 token, chắc chắn 100%
    ② khớp nguyên tên thủ tục trong RAM  → 0 token
    ③ vector top-10, gom theo thủ tục    → 1 lần nhúng, chỉ khi ① và ② đều trượt
"""

from __future__ import annotations

import hashlib
import logging
import struct
import time
from dataclasses import dataclass, field
from typing import Any

from backend.app.rag import fact_lookup, graph_query, resolver

logger = logging.getLogger(__name__)

#: Số vector giữ lại tối đa. Mỗi vector 1024 số thực ≈ 4 KB, nên 256 mục ≈ 1 MB — đủ cho
#: một phiên demo dài mà không phình bộ nhớ. Vượt thì bỏ mục cũ nhất.
VECTOR_CACHE_MAX = 256

_kho_vector: dict[str, list[float]] = {}
_thu_tu: list[str] = []


def vector_hash(vector: list[float]) -> str:
    """Dấu vết ngắn, tất định, của một vector.

    Dùng ``struct`` thay vì ``repr`` để dấu vết không phụ thuộc cách Python in số thực —
    cùng một vector phải luôn cho cùng dấu vết, nếu không thì việc tra lại trong kho sẽ
    trượt một cách ngẫu nhiên.
    """
    if not vector:
        return ""
    goi = struct.pack(f"{len(vector)}f", *vector)
    return hashlib.sha256(goi).hexdigest()[:16]


def get_vector(dau_vet: str) -> list[float] | None:
    """Lấy lại vector theo dấu vết. ``None`` = không còn trong kho (hoặc chưa từng có)."""
    return _kho_vector.get(dau_vet)


def remember_vector(vector: list[float]) -> str:
    """Cất vector vào kho và trả dấu vết của nó."""
    dau_vet = vector_hash(vector)
    if not dau_vet:
        return ""
    if dau_vet in _kho_vector:
        return dau_vet
    _kho_vector[dau_vet] = list(vector)
    _thu_tu.append(dau_vet)
    while len(_thu_tu) > VECTOR_CACHE_MAX:
        cu = _thu_tu.pop(0)
        _kho_vector.pop(cu, None)
    return dau_vet


def reset_vector_cache() -> None:
    """Xoá kho vector. Dùng cho bài kiểm và khi cần đo lại từ đầu."""
    _kho_vector.clear()
    _thu_tu.clear()


@dataclass(slots=True)
class Resolution:
    """Kết quả định danh của **một** câu hỏi.

    Đây là thứ router đọc để chọn nhánh, và là thứ các nhánh đọc để khỏi định danh lại.
    """

    question: str
    #: Mã thủ tục tìm được trong câu (thứ tự xuất hiện). Rỗng = câu không nêu mã.
    codes: list[str] = field(default_factory=list)
    #: Chuỗi mà người dùng **coi là** mã, đã chuẩn hoá. Khác ``codes``: đây là điều họ gõ,
    #: ``codes`` là điều **tồn tại**. Hai thứ khác nhau chính là lúc cần nói
    #: "không có mã thủ tục đó".
    asked_codes: list[str] = field(default_factory=list)
    #: Mã văn bản pháp lý khớp được. Rỗng = câu không nêu văn bản.
    documents: list[str] = field(default_factory=list)
    #: Thực thể đóng khớp được: ``{"kind", "value", "label"}``; ``None`` = không có.
    entity: dict[str, str] | None = None
    #: Kết quả định danh thủ tục theo tên (dùng cả khi đã có mã).
    procedure: resolver.ProcedureResolution = field(default_factory=resolver.ProcedureResolution)
    #: ``True`` = câu này có nhúng câu hỏi (tối đa một lần).
    embedding_used: bool = False
    #: Dấu vết vector; ``""`` = không nhúng.
    dau_vet_vector: str = ""
    #: Có nhiều thực thể cùng khớp — cần hỏi lại, và **không** đáng nhúng thêm.
    entity_ambiguous: bool = False
    #: Câu dùng đại từ chỉ định ("thủ tục này", "quy định này"…) mà **không** nêu thủ tục nào
    #: trước đó. Hệ thống không có bộ nhớ hội thoại, nên không có tiền ngữ nào để hiểu — phải
    #: hỏi lại, và **không** được định danh bừa theo tên.
    needs_antecedent: bool = False
    #: Mã thủ tục **cuối cùng** dùng để neo — gộp mã nêu trực tiếp và mã tìm theo tên.
    ma: str = ""
    #: Tên hiển thị của thủ tục đã neo (nếu biết).
    ten: str = ""
    #: Ghi chú kỹ thuật, chỉ để chẩn đoán — không hiện cho người dùng.
    notes: list[str] = field(default_factory=list)
    ms: int = 0

    @property
    def co_dinh_danh(self) -> bool:
        """Đã biết câu này nói về thủ tục nào chưa."""
        return bool(self.ma)

    def state_patch(self) -> dict[str, Any]:
        """Các trường trạng thái mà bước này điền.

        Giữ ánh xạ ở **một** chỗ: nếu mỗi bước tự viết ``state["..."] = ...`` thì việc đổi
        tên trường sẽ phải sửa rải rác, và trường nào quên điền thì không ai báo.
        """
        return {
            "codes": list(self.codes),
            "documents": list(self.documents),
            "entity": self.entity,
            "entity_ambiguous": self.entity_ambiguous,
            "needs_antecedent": self.needs_antecedent,
            "vector_hash": self.dau_vet_vector,
            "embedding_used": self.embedding_used,
            "resolution": {
                # Mã người dùng **đã nêu** nhưng không tồn tại — để bước sau nói đúng mã
                # thay vì câu từ chối chung chung.
                "asked": list(self.asked_codes),
                "code": self.procedure.code or "",
                "name": self.procedure.name or "",
                "method": self.procedure.method or "",
                "confidence": float(self.procedure.confidence),
                "ambiguous": bool(self.procedure.ambiguous),
                "alternatives": [
                    {"code": ma, "name": ten, "score": float(diem)}
                    for ma, ten, diem in self.procedure.alternatives
                ],
                "note": self.procedure.note or "",
            },
        }


async def resolve(
    question: str,
    *,
    only_anchors: bool = False,
    vector: list[float] | None = None,
) -> Resolution:
    """Định danh mọi thứ trong câu hỏi — gọi **một lần** cho mỗi lượt.

    Không bao giờ ném lỗi: hỏng bước nào thì ghi vào ``notes`` và đi tiếp với kết quả
    rỗng. Router cần biết "không định danh được" như một thông tin, không phải như một
    ngoại lệ.

    ## Hai tham số để chèn tầng kho đệm vào giữa

    ``only_anchors=True`` dừng ngay sau khi khớp mã / văn bản / thực thể, **chưa nhúng**.
    Dùng để biết "câu này đã có neo chưa" trước khi quyết định có đáng nhúng không.

    ``vector=...`` dùng lại vector đã tính thay vì nhúng lại. Dùng khi tầng kho đệm câu hỏi
    thường gặp đã nhúng một lần rồi (nó cần vector trước để tra), và giờ tới lượt định danh
    theo tên — vẫn đúng nguyên tắc "mỗi câu nhúng tối đa một lần".

    Nhờ hai tham số này, thứ tự chạy được là:

        neo (0 token) → [nếu chưa neo] nhúng một lần → kho đệm → định danh tên (dùng lại)
    """
    bat_dau = time.perf_counter()
    kq = Resolution(question=question)

    # ① mã thủ tục — regex + PostgreSQL
    try:
        tra_ma = await fact_lookup.resolve_codes(question)
        kq.codes = list(tra_ma.matched)
        kq.asked_codes = list(tra_ma.asked)
        if tra_ma.not_found:
            kq.notes.append("mã không tồn tại: " + ", ".join(tra_ma.not_found))
    except Exception as exc:  # noqa: BLE001 — định danh hỏng không được làm sập lượt
        logger.warning("Định danh mã lỗi: %s", exc)
        kq.notes.append(f"định danh mã lỗi: {str(exc)[:120]}")

    # ② + ③ văn bản và thực thể đóng — chỉ đọc RAM, không tốn token
    try:
        tu_dien = await graph_query.vocabulary()
        kq.documents = _documents(question, tu_dien)
        kq.entity, kq.entity_ambiguous = _entity(question, tu_dien)
        if kq.entity_ambiguous:
            kq.notes.append("nhiều thực thể cùng khớp — cần hỏi lại")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Khớp văn bản/thực thể lỗi: %s", exc)
        kq.notes.append(f"khớp văn bản/thực thể lỗi: {str(exc)[:120]}")

    # ④ tên thủ tục — chỉ chạy khi **chưa đủ neo**, và chỉ nhúng một lần
    #
    # Vì sao phải có điều kiện: đo trên 18 câu cho thấy nếu chạy vô điều kiện thì những câu
    # đã trả lời được bằng neo khác vẫn tốn một lần nhúng (~145 ms) mà không thu được gì:
    #
    #     "Nghị định 102/2024 là căn cứ của thủ tục nào?"  → đã có VĂN BẢN
    #     "Bộ Tư pháp ban hành những thủ tục nào?"         → đã có CƠ QUAN
    #     "Lĩnh vực nào nhiều thủ tục nhất?"               → câu thống kê, không cần thủ tục
    #
    # Ba trường hợp vẫn PHẢI định danh dù đã có neo: câu có cụm chỉ định ("thủ tục này"…)
    # vì nó nói về **một** thủ tục cụ thể; và câu mơ hồ thực thể, vì lúc đó cần hỏi lại chứ
    # không phải đoán thêm.
    if only_anchors:
        # Dừng trước bước định danh tên. Vector đi kèm (nếu có) vẫn được cất để tầng sau
        # dùng lại — chặng này chỉ **không chủ động** nhúng thêm.
        if vector:
            kq.dau_vet_vector = remember_vector(vector)
            kq.embedding_used = True
        kq.ma = kq.codes[0] if kq.codes else ""
        kq.ms = int((time.perf_counter() - bat_dau) * 1000)
        return kq

    lazy = resolver.LazyQuestionVector(question)

    # Định danh tên **trước**, rồi mới xét tiền ngữ: tiền ngữ của "thủ tục này" có thể là một
    # cách gọi khác ("giấy xác nhận độc thân"), nên chỉ bộ định danh mới biết có hay không.
    # Xét trước như bản cũ là so tên tuyệt đối — và đã trượt đúng câu đó.
    vi_tri = graph_query.demonstrative_position(question)
    co_dai_tu = vi_tri >= 0
    # Đại từ ở đầu câu: phía trước **không có gì** để trỏ vào. Đây là sự thật về câu, nên
    # không cần — và không được — định danh theo tên: làm vậy chính là đoán.
    thieu_han = co_dai_tu and vi_tri <= TIEN_NGU_TOI_THIEU

    if not thieu_han and _can_dinh_danh_ten(question, kq):
        try:
            if vector:
                # Vector đã có (tầng kho đệm vừa tra bằng nó) → dùng lại, không nhúng lại.
                kq.procedure = await resolver.resolve_procedure(
                    question, codes=None, get_vector=_vector_san(vector)
                )
            else:
                kq.procedure = await resolver.resolve_procedure(
                    question, codes=None, get_vector=lazy.get
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Định danh tên thủ tục lỗi: %s", exc)
            kq.notes.append(f"định danh tên lỗi: {str(exc)[:120]}")
    elif kq.codes:
        kq.procedure = resolver.ProcedureResolution(
            code=kq.codes[0], method="code", confidence=1.0, note="mã nêu trực tiếp"
        )
    else:
        kq.procedure = resolver.ProcedureResolution(
            note="đã đủ neo (văn bản/thực thể) — không cần định danh theo tên"
        )

    # Tiền ngữ có hay không, xét **sau** khi biết đã định danh được thủ tục nào chưa.
    #
    # Hai điều kiện, cả hai đều là **sự thật về câu**, không phải đoán nghĩa:
    #   * đại từ nằm ở đầu câu → phía trước **không có gì** để trỏ vào;
    #   * hoặc không định danh được thủ tục nào → không có gì để hiểu đại từ.
    kq.needs_antecedent = thieu_han or (
        co_dai_tu and not kq.codes and not kq.procedure.code
    )
    if kq.needs_antecedent:
        # Đại từ chỉ định mà **không** định danh được thủ tục nào: hệ thống không có bộ nhớ hội
        # thoại nên "thủ tục này" không trỏ vào đâu được. Đo được: câu *"Thủ tục này cần những
        # giấy tờ nào?"* từng bị gán cho thủ tục hôn nhân và trả 51 đoạn văn về hôn nhân.
        kq.procedure = resolver.ProcedureResolution(
            note="câu có đại từ chỉ định nhưng không nêu thủ tục nào trước đó"
        )

    if lazy.used:
        try:
            vec_moi = await lazy.get()
            kq.dau_vet_vector = remember_vector(vec_moi)
            kq.embedding_used = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Không cất được vector: %s", exc)
            kq.notes.append(f"không cất được vector: {str(exc)[:120]}")
    elif vector:
        # Câu này không tự nhúng nhưng được truyền vector vào → vẫn phải cất để nhánh sau
        # (tìm kiếm lai) dùng lại, và vẫn phải ghi cờ "đã nhúng" cho số đo.
        kq.dau_vet_vector = remember_vector(vector)
        kq.embedding_used = True

    # Mã dùng để neo: mã nêu trực tiếp thắng mã tìm theo tên (chắc chắn hơn).
    kq.ma = kq.codes[0] if kq.codes else (kq.procedure.code or "")

    #: Tên hiển thị chỉ có khi thủ tục được tìm theo tên; mã nêu trực tiếp thì tên do các
    #: nhánh tự lấy từ dữ liệu của chúng (bộ định danh không truy vấn thêm để lấy tên).
    kq.ten = kq.procedure.name or ""

    kq.ms = int((time.perf_counter() - bat_dau) * 1000)
    return kq


def _vector_san(vector: list[float]):
    """Hàm lấy vector **đã có sẵn** — dùng thay cho việc nhúng lại.

    Trả một hàm không tham số để khớp đúng khuôn mà bước định danh tên cần.
    """

    async def lay() -> list[float]:
        return vector

    return lay


#: Số từ đầu câu mà nếu đại từ chỉ định rơi vào đó thì **chắc chắn** không có tiền ngữ: câu
#: *"Thủ tục này cần gì?"* — đại từ ở vị trí 0. Còn *"Tôi muốn làm thủ tục cấp giấy khai sinh.
#: Thủ tục này cần gì?"* — đại từ ở vị trí ~8, và phía trước có tên thủ tục.
TIEN_NGU_TOI_THIEU = 4


def needs_no_anchor(question: str) -> bool:
    """Câu hỏi thuộc loại **không cần neo nào** để trả lời (thống kê, đếm).

    Dùng ở tầng điều phối để biết có đáng nhúng câu hỏi không: câu *"lĩnh vực nào nhiều thủ
    tục nhất"* trả lời được bằng đồ thị mà không cần biết nó nói về thủ tục nào, nên nhúng
    chỉ tốn ~140 ms. Cũng vì thế mà không cần tra kho đệm cho loại câu này.
    """
    return _intent_khong_can_neo(question)


def _can_dinh_danh_ten(question: str, kq: Resolution) -> bool:
    """Có cần định danh thủ tục **theo tên** (tức là có cần nhúng) hay không.

    Đây là chỗ quyết định chi phí của cả lượt, nên luật phải rõ:

    * đã có **mã thủ tục** → không cần (chắc chắn nhất rồi);
    * đã có **văn bản** hoặc **thực thể đóng** → nhánh tương ứng tự trả lời được, không cần
      biết đó là thủ tục nào;
    * **trừ khi** câu có cụm chỉ định ("thủ tục này", "quy định này"…) — lúc đó người dùng
      đang nói về **một** thủ tục cụ thể nên phải biết nó là thủ tục nào;
    * **trừ khi** thực thể bị mơ hồ — lúc đó phải hỏi lại, nhúng thêm cũng không giải quyết;
    * còn lại (không neo gì) → phải định danh, kể cả khi kết quả là "không xác định được",
      vì đó cũng là thông tin cần cho bước hỏi lại.
    """
    if kq.codes:
        return False
    if kq.entity_ambiguous:
        return False
    if any(graph_query.has_phrase(question, x) for x in graph_query.DEMONSTRATIVES):
        return True
    if _intent_khong_can_neo(question):
        return False
    if kq.documents:
        return False
    if kq.entity:
        # Có thực thể **chưa chắc** là đã đủ: thực thể chỉ trả lời được khi đồ thị có hình dạng
        # dùng chính nó (liệt kê theo cơ quan / cấp / lĩnh vực). Với câu hỏi nội dung ("phí bao
        # nhiêu", "mấy ngày"), tên lĩnh vực chỉ là manh mối — vẫn phải biết đó là thủ tục nào.
        #
        # Đo được: *"quán cơm … xin giấy chứng nhận an toàn thực phẩm hết bao nhiêu tiền phí"*
        # khớp lĩnh vực "An toàn thực phẩm" nên **bỏ qua** định danh tên, rồi router kết luận
        # "không có thủ tục" — trong khi 1.013855 có trong dữ liệu.
        return not do_thi_tra_loi_duoc_bang_thuc_the(question, kq.entity)
    return True


def do_thi_tra_loi_duoc_bang_thuc_the(question: str, entity: dict[str, str] | None) -> bool:
    """Đồ thị có hình dạng trả lời được **chỉ bằng thực thể** đã khớp hay không.

    Dùng ở hai chỗ, phải cùng một câu trả lời: quyết định *có cần định danh tên không* và quyết
    định *cạnh ``neo`` có được đi thẳng tới router không*. Hai chỗ lệch nhau thì câu hỏi nội
    dung có thực thể sẽ bỏ qua bước định danh — đúng lỗi đã gặp.
    """
    if not entity:
        return False
    try:
        spec = graph_query.classify(
            question,
            has_code=False,
            has_document=False,
            entity=graph_query.EntityMatch(
                kind=str(entity.get("kind") or ""),
                value=str(entity.get("value") or ""),
                label=str(entity.get("label") or ""),
            ),
        )
    except Exception:  # noqa: BLE001 — luật phụ, hỏng thì coi như không trả lời được
        return False
    return spec is not None


def _intent_khong_can_neo(question: str) -> bool:
    """Câu hỏi thuộc loại **không cần neo** nào để trả lời hay không.

    Đo được ba câu bị nhúng thừa vì không có mã, không có văn bản, không có thực thể:

        "Lĩnh vực nào nhiều thủ tục nhất?"          ← câu thống kê
        "Cơ quan nào ban hành nhiều thủ tục nhất?"   ← câu thống kê
        "Văn bản nào làm căn cứ cho nhiều thủ tục nhất?"

    Chúng thuộc nhóm hình dạng mà bảng quyết định của đồ thị khai báo **không cần tham số
    nào**. Vì vậy hỏi thẳng bảng đó thay vì đoán: khớp được một hình dạng không cần tham số
    thì không phải định danh thủ tục làm gì.

    Trả ``False`` khi không khớp gì — lúc đó phải định danh, vì "không xác định được" cũng
    là thông tin cần cho bước hỏi lại và cho việc nhận ra câu ngoài phạm vi.
    """
    try:
        spec = graph_query.classify(question, has_code=False, has_document=False, entity=None)
    except Exception:  # noqa: BLE001 — luật phụ, hỏng thì bỏ qua
        return False
    return spec is not None and not spec.needs


def _documents(question: str, tu_dien: graph_query.Vocabulary) -> list[str]:
    """Mã văn bản pháp lý khớp được.

    Mơ hồ thì trả **danh sách ứng viên** thay vì chọn bừa: bước sau cần biết "có nhiều văn
    bản cùng khớp" để hỏi lại, và danh sách chính là nội dung câu hỏi lại đó.
    """
    khop = graph_query.match_documents(question, tu_dien)
    if khop.unique is not None:
        return [khop.unique.key]
    if khop.candidates:
        return [m.key for m in khop.candidates[:5]]
    return []


def _entity(question: str, tu_dien: graph_query.Vocabulary) -> tuple[dict[str, str] | None, bool]:
    """Thực thể đóng khớp được và cờ mơ hồ.

    Trả cả cờ mơ hồ thay vì gọi lại bước khớp lần nữa: khớp hai lần là hai cơ hội để hai
    kết quả khác nhau, và tốn thêm một lượt duyệt từ điển mỗi câu.
    """
    thuc_the, mo_ho = graph_query.match_entities(question, tu_dien)
    if thuc_the is None:
        return None, bool(mo_ho)
    return {"kind": thuc_the.kind, "value": thuc_the.value, "label": thuc_the.label}, False
