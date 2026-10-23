"""Bước sinh câu trả lời có trích dẫn (việc 13.13).

Đầu vào là **bằng chứng** mà các nhánh đã tìm được; đầu ra là câu trả lời cho người dân, mỗi
khẳng định gắn với một nguồn `[n]`.

## Vì sao phải có bước này riêng

Bốn nhánh trả bốn kiểu dữ liệu khác nhau — thuộc tính từ PostgreSQL, quan hệ từ Neo4j, đoạn
văn từ Elasticsearch + Qdrant. Người dân không đọc ba kiểu đó.
Bước này là chỗ duy nhất biến chúng thành **một** câu trả lời, và là chỗ duy nhất có thể **bịa**
— nên mọi ràng buộc về trung thực đều đặt ở đây.

## Ba luật không thoả hiệp

① **Chỉ dùng ngữ cảnh được cấp.** Không có kiến thức ngoài, không suy đoán.
② **Thiếu dữ liệu thì nói thiếu**, không im lặng và không lấp bằng câu chung chung. Phân biệt
   rõ *"chưa ghi nhận"* (dữ liệu của tôi không có) với *"không có"* (kết luận về pháp luật) —
   hai câu này khác nhau về trách nhiệm.
③ **Mỗi khẳng định phải trỏ được về một mục** `[n]` trong ngữ cảnh. Câu không trích được thì
   không được viết.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from backend.app.config import settings
from backend.app.rag import contracts

logger = logging.getLogger(__name__)

#: Chờ tối đa cho một lần sinh. Câu trả lời dài 400–700 từ vẫn xong trong 10–20 giây; quá 45
#: giây là lỗi thật, không phải chậm.
TIMEOUT_S = 45.0

#: Số mục ngữ cảnh tối đa đưa vào lời dẫn. Sáu đoạn đã đủ cho một câu trả lời; nhiều hơn thì
#: mô hình bắt đầu trộn các thủ tục khác nhau.
TOI_DA_MUC = 12


# ══════════════════════════════════════════════════════════════════════════
# LỜI DẪN
# ══════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """Bạn là trợ lý tra cứu thủ tục hành chính của tỉnh Gia Lai, trả lời cho người
dân bằng tiếng Việt.

## Nguồn duy nhất của bạn

Bạn chỉ được dùng **NGỮ CẢNH** trong tin nhắn người dùng. Mỗi mục ngữ cảnh ghi rõ nguồn:
`PostgreSQL` (thuộc tính định danh của thủ tục), `Neo4j` (quan hệ giữa thủ tục và cơ quan/văn
bản) và `Hybrid` (đoạn văn nội dung).

Bạn **không** có kiến thức pháp luật nào khác. Không dùng hiểu biết bên ngoài, không suy đoán,
không "bổ sung cho đầy đủ". Chi tiết nào không có trong ngữ cảnh thì không tồn tại với bạn.

## Trả lời theo từng ý

Khi tin nhắn có khối `CÁC Ý CẦN TRẢ LỜI`, hãy trả lời **đúng thứ tự** đó, mỗi ý một đoạn ngắn.

* Ý ghi **có dữ liệu**: bắt buộc trả lời bằng ngữ cảnh. **Cấm** viết "chưa ghi nhận", "chưa có
  dữ liệu", "không tìm thấy" cho ý này khi ngữ cảnh có thông tin.
* Ý ghi **không có dữ liệu**: chỉ nói chưa có thông tin cho đúng ý đó; không suy đoán, không
  lấy thông tin của ý khác bù vào.
* Ý ghi **nguồn dữ liệu tạm lỗi**: nói hệ thống chưa tra được vì nguồn lỗi, **không** nói dữ
  liệu không có.
* Ý ghi **chưa hỗ trợ**: nói hệ thống chưa hỗ trợ loại thông tin này.
* Ý ghi **cần làm rõ**: đề nghị người dùng chọn hoặc nêu rõ thêm.
* Nếu chỉ trả lời được một phần, phải nói rõ phần nào chưa có; **không** viết như thể đã trả lời
  đầy đủ.

## Không đánh số nguồn trong câu trả lời

Tuyệt đối **không** viết `[1]`, `[2]`, `(1)`, `nguồn 1` hay bất kỳ ký hiệu đánh số nào vào câu
trả lời. Giao diện tự hiện danh sách nguồn kèm đường dẫn bên dưới, nên số hiệu chỉ làm câu chữ
rối. Cũng **không** chép đường dẫn (http…) vào câu trả lời — giao diện lo phần đó.

Yêu cầu duy nhất về nguồn: mọi khẳng định phải **lấy từ** ngữ cảnh, không được thêm.

## Trạng thái do hệ thống chốt trước khi sinh

Mỗi ý trong khối `CÁC Ý CẦN TRẢ LỜI` và phần ngữ cảnh tương ứng đã có trạng thái do hệ thống
quyết định. Bạn chỉ diễn đạt đúng trạng thái đó:

- **có dữ liệu**: trả lời bằng evidence của chính ý đó.
- **dữ liệu chưa ghi nhận**: nói ngắn gọn dữ liệu chưa ghi nhận cho đúng ý đó; không suy đoán.
- **nguồn dữ liệu tạm lỗi**: nói hiện chưa thể tra cứu ý đó do nguồn dữ liệu tạm lỗi; đây không
  phải là kết luận dữ liệu không có.
- **hệ thống chưa hỗ trợ**: nói hệ thống chưa hỗ trợ tra cứu ý đó; không thay bằng "chưa ghi
  nhận".

Không tự nói một ý là thiếu nếu trạng thái hệ thống không nói như vậy. Chỉ dùng "không có" khi
evidence cho thấy rõ đó là kết luận về nội dung pháp luật.

## Cấm liệt kê những gì bạn không có

**Không** thêm đoạn văn kể ra những nội dung bạn không được cấp. Những câu sau đây là sai và
không được viết:

- *"Dữ liệu chưa ghi nhận các nội dung người dân thường cần: thành phần hồ sơ, cách thức nộp,
  thời hạn giải quyết và lệ phí."*
- *"Căn cứ pháp lý chi tiết cũng chưa ghi nhận ngoài số quyết định nêu trên."*
- *"Ngoài ra tôi không có thêm thông tin về …"*
- *"Dữ liệu chưa ghi nhận trình tự thực hiện (các bước thực hiện) của thủ tục này."* — câu này
  đã đo được trong thực tế, khi ngữ cảnh chỉ có mục hồ sơ. Ngữ cảnh thiếu mục nào thì **không
  nói gì** về mục đó, trừ khi mục đó nằm trong khối `CÁC MỤC KHÔNG CÓ DỮ LIỆU`.

Người dân hỏi gì thì trả lời nấy. Nội dung họ **không hỏi** thì không nhắc tới, dù ngữ cảnh
thiếu hay đủ. Chỉ khi họ hỏi đúng nội dung đó mà không có dữ liệu, mới dùng một câu "chưa ghi
nhận" gọn cho chính nội dung ấy.

## Cách trả lời

1. **Trả lời thẳng câu hỏi ở câu đầu tiên.** Không mở bài, không nhắc lại câu hỏi.
2. Không mở đầu bằng *"Chỉ trả lời"*, *"Dựa vào ngữ cảnh được cung cấp"*, *"Theo dữ liệu"*,
   *"Căn cứ vào thông tin trên"* — vào thẳng nội dung.
3. **Chi tiết sau đó**, theo thứ tự người dân cần: hồ sơ → cách nộp → thời hạn → lệ phí →
   cơ quan → căn cứ pháp lý. Chỉ nêu mục nào có trong ngữ cảnh và liên quan tới câu hỏi.
4. **Danh sách thì dùng gạch đầu dòng**, mỗi dòng một giấy tờ/bước/mức phí.
5. **Nêu mã và tên thủ tục** ở đầu câu trả lời khi biết, vì người dân cần đối chiếu.
6. **Độ dài**: đủ để trả lời, không dài hơn. Câu hỏi một ý thì 3–6 câu; hỏi hồ sơ thì liệt kê
   đủ giấy tờ. Không thêm lời khuyên, không thêm thủ tục khác không được hỏi.
7. **Văn bản thuần**, được dùng gạch đầu dòng và in đậm; không dùng bảng, không dùng tiêu đề
   cấp cao, không dùng ký hiệu LaTeX.

## Câu hỏi nhiều ý

Trả lời **từng ý**, theo đúng thứ tự người dùng hỏi. Ý nào ngữ cảnh không có thì nói rõ ý đó
chưa có dữ liệu — **không** bỏ qua, và **không** vì một ý thiếu mà không trả lời các ý còn lại.

## Câu hỏi ngoài phạm vi

Nếu ngữ cảnh không liên quan tới câu hỏi (ví dụ hỏi thời tiết, hỏi thủ tục của tỉnh khác), trả
lời đúng một câu: *"Câu hỏi này nằm ngoài dữ liệu thủ tục hành chính của tỉnh Gia Lai mà tôi
có."* Không cố suy diễn, không trích dẫn gượng ép.

## Điều không được làm

- Không bịa số: mức phí, số ngày, số quyết định, số điều luật — chỉ chép từ ngữ cảnh.
- Không gộp hai thủ tục khác nhau vào một câu trả lời.
- Không nói "theo quy định chung" hay "theo pháp luật hiện hành" khi ngữ cảnh không nêu.
- Không hứa hẹn về thời gian xử lý thực tế ngoài con số trong ngữ cảnh.
- Không thêm phần "Lưu ý" hay "Khuyến nghị" nếu người dùng không hỏi.
- Không in đường dẫn, không in số hiệu nguồn.
"""


#: Nhãn nguồn theo loại bằng chứng — trùng với nhãn trên giao diện để người đọc đối chiếu được.
NHAN_NGUON = {
    "fact": "PostgreSQL",
    "graph": "Neo4j",
    "chunk": "Hybrid",
    "section": "PostgreSQL",
}

#: Nhãn tiếng Việt của chín khía cạnh — dùng khi nói với mô hình "mục này không có dữ liệu".
NHAN_KHIA_CANH = {
    "required_documents": "thành phần hồ sơ",
    "steps": "trình tự thực hiện",
    "submission_method": "cách thức nộp / nơi nộp",
    "processing_time": "thời hạn giải quyết",
    "fee": "phí, lệ phí",
    "result": "kết quả nhận được",
    "legal_basis": "căn cứ pháp lý",
    "requirements": "điều kiện, đối tượng",
    "general_info": "thông tin chung",
    "issuing_agency": "cơ quan ban hành",
    "implementing_agency": "cơ quan thực hiện",
    "coordinating_agency": "cơ quan phối hợp",
    "authorized_agency": "cơ quan được ủy quyền",
    "administrative_level": "cấp thực hiện",
    "field": "lĩnh vực",
    "domain_group": "nhóm thủ tục",
    "status": "trạng thái thủ tục",
    "target_audience": "đối tượng thực hiện",
    "related_procedures": "thủ tục liên quan",
}

#: Câu cho từng trạng thái coverage. Không được gộp ``failed``/``unsupported``/``ambiguous``
#: vào "không có dữ liệu": ba trạng thái đó cần hành động khác nhau.
STATUS_TEXT: dict[str, str] = {
    "covered": "có dữ liệu",
    "empty": "không có dữ liệu (đã tìm, dữ liệu không ghi nhận)",
    "failed": "nguồn dữ liệu tạm lỗi — KHÔNG phải dữ liệu thiếu",
    "unsupported": "hệ thống chưa hỗ trợ loại thông tin này",
    "ambiguous": "cần làm rõ — có nhiều lựa chọn",
}


@dataclass(frozen=True, slots=True)
class AnswerResult:
    """Kết quả một lần sinh. ``text == ""`` nghĩa là không sinh được (xem ``error``)."""

    text: str
    #: Nguồn đã cấp cho mô hình, **cùng thứ tự** với số hiệu ``[1]``, ``[2]``… trong câu trả lời.
    citations: tuple[dict[str, str], ...]
    ms: int
    tokens_in: int
    tokens_out: int
    model: str
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.text)


class AnswerError(RuntimeError):
    """Không sinh được câu trả lời. Nơi gọi phải giữ nguyên bằng chứng và báo lỗi."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ══════════════════════════════════════════════════════════════════════════
# DỰNG NGỮ CẢNH
# ══════════════════════════════════════════════════════════════════════════


def _nhan_muc(muc: dict[str, Any]) -> str:
    """Một dòng tiêu đề cho mục ngữ cảnh: nguồn · thủ tục · loại thông tin."""
    nguon = NHAN_NGUON.get(str(muc.get("kind") or ""), "?")
    phan = [f"Nguồn: {nguon}"]

    ma = str(muc.get("procedure_code") or "")
    ten = str(muc.get("procedure_name") or "")
    if ma:
        phan.append(f"Thủ tục {ma}" + (f" — {ten}" if ten else ""))
    elif ten:
        phan.append(f"Thủ tục: {ten}")

    loai = str(muc.get("title") or muc.get("section_type") or "")
    if muc.get("part_title"):
        loai = f"{muc['part_title']} · {loai}" if loai else str(muc["part_title"])
    if loai:
        phan.append(loai)

    return " · ".join(phan)


def nhan_trich_dan(muc: dict[str, Any]) -> str:
    """Nhãn ngắn để hiện dưới dạng chip nguồn trên giao diện."""
    ma = str(muc.get("procedure_code") or "")
    if ma:
        return ma
    tieu_de = str(muc.get("title") or muc.get("section_type") or "")
    return tieu_de[:40] or NHAN_NGUON.get(str(muc.get("kind") or ""), "nguồn")


def _status_map(coverage: Sequence[dict[str, Any]]) -> dict[int, str]:
    return {
        int(item.get("request_index") or 0): str(item.get("status") or "")
        for item in coverage
    }


def _chon_evidence(
    evidence: Sequence[dict[str, Any]],
    requests: Sequence[dict[str, Any]] = (),
    coverage: Sequence[dict[str, Any]] = (),
    toi_da: int = TOI_DA_MUC,
) -> list[tuple[int | None, dict[str, Any]]]:
    """Chọn mục ngữ cảnh **công bằng theo từng ý**, không cắt máy móc theo thứ tự.

    Luật: mỗi ý ``covered`` được ít nhất một mục trước khi ý khác lấy thêm; phần quota còn lại
    chia theo thứ tự ý. Nhờ vậy câu nhiều ý không bị mất bằng chứng của ý phía sau chỉ vì ý đầu
    có nhiều đoạn.
    """
    items = [
        m
        for m in evidence
        if " ".join(str(m.get("content") or "").split())
        and not contracts.is_discovery_object(m)
    ]
    if not items:
        return []
    if not requests:
        return [(None, muc) for muc in items[:toi_da]]

    status = _status_map(coverage)
    theo_yeu_cau: dict[int, list[dict[str, Any]]] = {i: [] for i in range(len(requests))}
    ngoai: list[dict[str, Any]] = []
    for muc in items:
        key = muc.get("request_index")
        if key is None or int(key) not in theo_yeu_cau:
            ngoai.append(muc)
        else:
            theo_yeu_cau[int(key)].append(muc)

    chon: list[tuple[int | None, dict[str, Any]]] = []
    lay: dict[int, int] = {i: 0 for i in range(len(requests))}

    # Vòng 1: mỗi ý covered một mục (tối đa 2) — bảo đảm không ý nào bị bỏ trắng.
    for index in range(len(requests)):
        if status.get(index) != "covered":
            continue
        for muc in theo_yeu_cau[index][:2]:
            if len(chon) >= toi_da:
                break
            chon.append((index, muc))
            lay[index] += 1

    # Vòng 2: chia đều phần còn lại.
    while len(chon) < toi_da:
        them = False
        for index in range(len(requests)):
            if len(chon) >= toi_da:
                break
            if lay[index] < len(theo_yeu_cau[index]):
                chon.append((index, theo_yeu_cau[index][lay[index]]))
                lay[index] += 1
                them = True
        if not them:
            break

    # Vòng 3: bằng chứng không gắn ý (dữ liệu cũ) — xếp cuối.
    for muc in ngoai:
        if len(chon) >= toi_da:
            break
        chon.append((None, muc))
    return chon


def _muc_dung_duoc(
    evidence: Sequence[dict[str, Any]], toi_da: int
) -> list[tuple[int, dict[str, Any]]]:
    """Tương thích cũ: đánh số danh sách đã chọn (không có thông tin ý)."""
    return [(i, muc) for i, (_, muc) in enumerate(_chon_evidence(evidence, toi_da=toi_da), 1)]


def build_context(
    evidence: Sequence[dict[str, Any]],
    *,
    toi_da: int = TOI_DA_MUC,
    requests: Sequence[dict[str, Any]] = (),
    coverage: Sequence[dict[str, Any]] = (),
) -> tuple[str, tuple[str, ...]]:
    """Dựng ngữ cảnh **nhóm theo từng ý** để câu trả lời không trộn ý.

    Mỗi ý có tiêu đề ``### Ý n — <khía cạnh>``; ý không có bằng chứng ghi rõ trạng thái hệ thống
    (không có dữ liệu / nguồn lỗi / chưa hỗ trợ), không để mô hình tự đoán.
    """
    chon = _chon_evidence(evidence, requests, coverage, toi_da)
    if not requests:
        dong: list[str] = []
        nhan: list[str] = []
        for _, muc in chon:
            dong.append(f"### {_nhan_muc(muc)}")
            dong.append(" ".join(str(muc.get("content") or "").split()))
            dong.append("")
            nhan.append(nhan_trich_dan(muc))
        return "\n".join(dong).strip(), tuple(nhan)

    status = _status_map(coverage)
    theo_yeu_cau: dict[int | None, list[dict[str, Any]]] = {}
    for index, muc in chon:
        theo_yeu_cau.setdefault(index, []).append(muc)

    dong = []
    nhan = []
    for index, request in enumerate(requests):
        facet = str(request.get("facet") or "")
        label = NHAN_KHIA_CANH.get(facet, facet or "nội dung")
        dong.append(f"### Ý {index + 1} — {label}")
        muc_cua_y = theo_yeu_cau.get(index, [])
        if not muc_cua_y:
            trang_thai = STATUS_TEXT.get(status.get(index, ""), "chưa có dữ liệu")
            dong.append(f"(Trạng thái: {trang_thai})")
            dong.append("")
            continue
        for muc in muc_cua_y:
            dong.append(_nhan_muc(muc))
            dong.append(" ".join(str(muc.get("content") or "").split()))
            dong.append("")
            nhan.append(nhan_trich_dan(muc))

    if theo_yeu_cau.get(None):
        dong.append("### Nguồn bổ sung")
        for muc in theo_yeu_cau[None]:
            dong.append(_nhan_muc(muc))
            dong.append(" ".join(str(muc.get("content") or "").split()))
            dong.append("")
            nhan.append(nhan_trich_dan(muc))

    return "\n".join(dong).strip(), tuple(nhan)


def build_citations(
    evidence: Sequence[dict[str, Any]],
    *,
    toi_da: int = TOI_DA_MUC,
    requests: Sequence[dict[str, Any]] = (),
    coverage: Sequence[dict[str, Any]] = (),
) -> tuple[dict[str, str], ...]:
    """Nguồn ứng với từng mục — dùng **cùng** hàm chọn với :func:`build_context`."""
    return tuple(
        {
            "procedure_code": str(muc.get("procedure_code") or ""),
            "procedure_name": str(muc.get("procedure_name") or ""),
            "detail_url": str(muc.get("detail_url") or ""),
            "document_code": str(muc.get("document_code") or ""),
            "section": (
                str(muc.get("title") or "")
                if str(muc.get("kind") or "") in {"chunk", "section"}
                else ""
            ),
        }
        for _, muc in _chon_evidence(evidence, requests, coverage, toi_da)
    )


def build_request_block(
    requests: Sequence[dict[str, Any]], coverage: Sequence[dict[str, Any]] = ()
) -> str:
    """Khối liệt kê các ý theo đúng thứ tự, kèm trạng thái phủ do executor tính."""
    if not requests:
        return ""
    status = _status_map(coverage)
    dong = ["CÁC Ý CẦN TRẢ LỜI (đúng thứ tự):"]
    for index, request in enumerate(requests):
        facet = str(request.get("facet") or "")
        nhan = NHAN_KHIA_CANH.get(facet, facet or "nội dung")
        dong.append(
            f"{index + 1}. {nhan} — {STATUS_TEXT.get(status.get(index, ''), 'chưa xác định')}"
        )
    return "\n".join(dong) + "\n\n"


#: Câu mô hình dùng để nói "không có dữ liệu". Dùng cho kiểm chứng hậu sinh.
DENIAL_PATTERN = re.compile(
    r"(chưa ghi nhận|chưa được ghi nhận|chưa có dữ liệu|chưa có thông tin|"
    r"không có dữ liệu|không có thông tin|không tìm thấy)",
    re.IGNORECASE,
)

#: Từ đồng nghĩa tối thiểu cho **kiểm chứng** (không dùng để định tuyến).
FACET_HINTS: dict[str, tuple[str, ...]] = {
    "required_documents": ("ho so", "giay to"),
    "processing_time": ("thoi han", "bao lau"),
    "submission_method": ("cach nop", "noi nop"),
    "legal_basis": ("van ban", "can cu"),
    "result": ("ket qua",),
    "steps": ("trinh tu",),
    "fee": ("le phi",),
}


def _facet_phrases(label: str, facet: str = "") -> set[str]:
    """Cụm 2–3 từ của một nhãn khía cạnh, đã bỏ dấu — để so trong từng câu trả lời."""
    from backend.app.text_norm import strip_accents

    words = strip_accents(label).lower().split()
    phrases: set[str] = set(FACET_HINTS.get(facet, ()))
    for size in (2, 3):
        for start in range(len(words) - size + 1):
            phrase = " ".join(words[start : start + size])
            if len(phrase) >= 4:
                phrases.add(phrase)
    return phrases


def _sentence_matches(sentence: str, facets: Sequence[str]) -> bool:
    for facet in facets:
        phrases = _facet_phrases(NHAN_KHIA_CANH.get(facet, facet), facet)
        if any(phrase in sentence for phrase in phrases):
            return True
    return False


def _denial_hits_covered(
    text: str, covered_facets: Sequence[str], thieu: Sequence[str] = ()
) -> bool:
    """Câu phủ nhận có nói về khía cạnh **đã có bằng chứng** và không phải khía cạnh thiếu."""
    from backend.app.text_norm import strip_accents

    for cau in re.split(r"[.!?\n]+", text):
        if not DENIAL_PATTERN.search(cau):
            continue
        chuan = strip_accents(cau).lower()
        if _sentence_matches(chuan, covered_facets) and not _sentence_matches(
            chuan, list(thieu)
        ):
            return True
    return False


def verify_contract(
    text: str,
    evidence: Sequence[dict[str, Any]],
    *,
    thieu: Sequence[str] = (),
    covered_facets: Sequence[str] = (),
) -> list[str]:
    """Kiểm tra hợp đồng trả lời sau khi sinh. Trả danh sách lỗi (rỗng = đạt).

    Tất định, không gọi mô hình: bắt đúng lỗi đã đo — phủ nhận bằng chứng đang có, hoặc trả lời
    thiếu ý mà không nói là thiếu.
    """
    issues: list[str] = []
    clean = " ".join(str(text or "").split())
    if not clean:
        return ["empty_answer"]
    has_denial = bool(DENIAL_PATTERN.search(clean))
    if has_denial and evidence and covered_facets and _denial_hits_covered(
        clean, covered_facets, thieu
    ):
        issues.append("denies_available_evidence")
    if thieu and not has_denial:
        issues.append("omits_missing_data")
    return issues


def build_fallback_answer(
    evidence: Sequence[dict[str, Any]],
    *,
    requests: Sequence[dict[str, Any]] = (),
    coverage: Sequence[dict[str, Any]] = (),
    toi_da: int = TOI_DA_MUC,
) -> str:
    """Câu trả lời **tất định** từ evidence, dùng khi mô hình vi phạm hợp đồng sau retry."""
    chon = _chon_evidence(evidence, requests, coverage, toi_da)
    if not chon:
        return ""
    status = _status_map(coverage)
    theo_yeu_cau: dict[int | None, list[dict[str, Any]]] = {}
    for index, muc in chon:
        theo_yeu_cau.setdefault(index, []).append(muc)

    if not requests:
        dong = [
            " ".join(str(muc.get("content") or "").split())[:400] for _, muc in chon[:3]
        ]
        return "\n\n".join(d for d in dong if d)

    phan: list[str] = []
    for index, request in enumerate(requests):
        facet = str(request.get("facet") or "")
        label = NHAN_KHIA_CANH.get(facet, facet or "nội dung")
        muc_cua_y = theo_yeu_cau.get(index, [])
        if not muc_cua_y:
            trang_thai = STATUS_TEXT.get(status.get(index, ""), "chưa có dữ liệu")
            phan.append(f"**{label}**: {trang_thai}.")
            continue
        dong = [f"**{label}**"]
        for muc in muc_cua_y[:2]:
            noi_dung = " ".join(str(muc.get("content") or "").split())
            if noi_dung:
                dong.append(f"- {noi_dung[:400]}")
        phan.append("\n".join(dong))
    return "\n\n".join(phan).strip()


def build_messages(
    question: str,
    evidence: Sequence[dict[str, Any]],
    *,
    thieu: Sequence[str] = (),
    requests: Sequence[dict[str, Any]] = (),
    coverage: Sequence[dict[str, Any]] = (),
    strict_note: str = "",
) -> list[dict[str, str]]:
    """Tin nhắn gửi mô hình: lời dẫn + ngữ cảnh + **danh sách mục thiếu** + câu hỏi.

    ``thieu`` do **mã nguồn** tính (khía cạnh đã hỏi mà sau khi truy xuất vẫn rỗng), không do
    mô hình suy ra. Đây là điểm mấu chốt: mô hình chỉ thấy ngữ cảnh nên không thể biết dữ liệu
    có gì; để nó tự kết luận "chưa ghi nhận" chính là lỗi đã đo được.
    """
    ngu_canh, _ = build_context(evidence, requests=requests, coverage=coverage)
    khoi_thieu = ""
    if thieu and not requests:
        nhan = ", ".join(NHAN_KHIA_CANH.get(x, x) for x in thieu)
        khoi_thieu = f"CÁC MỤC KHÔNG CÓ DỮ LIỆU (hệ thống đã tìm, không có):\n{nhan}\n\n"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{build_request_block(requests, coverage)}"
                "NGỮ CẢNH:\n"
                f"{ngu_canh or '(không có mục ngữ cảnh nào)'}\n\n"
                f"{khoi_thieu}"
                f"{strict_note}"
                "CÂU HỎI CỦA NGƯỜI DÂN:\n"
                f"{question}"
            ),
        },
    ]


# ══════════════════════════════════════════════════════════════════════════
# GỌI MÔ HÌNH
# ══════════════════════════════════════════════════════════════════════════

_client_theo_loop: AsyncOpenAI | None = None
_loop_da_dung: asyncio.AbstractEventLoop | None = None


def _client() -> AsyncOpenAI:
    """Client **theo event loop hiện tại** — cùng lý do như router: giữ kết nối TLS."""
    global _client_theo_loop, _loop_da_dung

    loop = asyncio.get_running_loop()
    if _client_theo_loop is None or _loop_da_dung is not loop:
        if _client_theo_loop is not None:
            try:
                _client_theo_loop.close()
            except Exception:  # noqa: BLE001 — loop cũ đã đóng thì bỏ qua
                pass
        _client_theo_loop = AsyncOpenAI(
            base_url=settings.deepseek_base_url,
            api_key=settings.deepseek_api_key,
        )
        _loop_da_dung = loop
    return _client_theo_loop


async def close_client() -> None:
    """Đóng client của loop hiện tại."""
    global _client_theo_loop, _loop_da_dung

    if _client_theo_loop is not None and _loop_da_dung is asyncio.get_running_loop():
        try:
            await _client_theo_loop.close()
        finally:
            _client_theo_loop = None
            _loop_da_dung = None


def dang_bat() -> bool:
    """Có bật bước sinh câu trả lời không.

    **Mặc định BẬT**: không đặt biến môi trường nào thì bước sinh chạy bình thường, vì đó là
    hành vi thật của sản phẩm. Chỉ tắt khi đặt ``ANSWER_USE_LLM=0``.

    Công tắc này tồn tại **chỉ để bài kiểm không gọi API trả tiền** (xem
    ``backend/tests/conftest.py``). Nó không phải cổng dành cho người dùng: ở sáu chế độ truy
    xuất, việc có sinh hay không do ô *"Sinh câu trả lời từ context"* quyết định, còn Luồng
    chính thì luôn sinh khi có bằng chứng.
    """
    if os.getenv("ANSWER_USE_LLM", "1").strip().lower() in {"0", "false", "no", "off"}:
        return False
    return bool(settings.synthesizer_model_name and settings.deepseek_base_url)


async def sinh(
    question: str,
    evidence: Sequence[dict[str, Any]],
    *,
    thieu: Sequence[str] = (),
    requests: Sequence[dict[str, Any]] = (),
    coverage: Sequence[dict[str, Any]] = (),
    strict_note: str = "",
    timeout: float = TIMEOUT_S,
) -> AnswerResult:
    """Sinh câu trả lời từ **bằng chứng**. Ném :class:`AnswerError` nếu không dùng được.

    Không bao giờ trả câu trả lời rỗng mà không nói lý do: nơi gọi cần biết để hiện bằng chứng
    thay vì một khung trống.
    """
    if not dang_bat():
        raise AnswerError("chưa cấu hình SYNTHESIZER_MODEL_NAME / DEEPSEEK_BASE_URL")

    if not evidence:
        raise AnswerError("không có bằng chứng nào để trả lời")

    messages = build_messages(
        question, evidence, thieu=thieu, requests=requests, coverage=coverage,
    )
    nhan = build_citations(evidence, requests=requests, coverage=coverage)
    bat_dau = time.perf_counter()
    client = _client()

    try:
        phan_hoi = await asyncio.wait_for(
            client.chat.completions.create(
                model=settings.synthesizer_model_name,
                messages=messages,  # type: ignore[arg-type]
                temperature=settings.synthesizer_temperature,
                max_tokens=settings.synthesizer_max_tokens,
            ),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise AnswerError(f"quá hạn {timeout:.0f}s") from exc
    except Exception as exc:  # noqa: BLE001 — mạng/API: đổi thành lỗi có lý do
        raise AnswerError(f"{type(exc).__name__}: {str(exc)[:160]}") from exc

    ms = int((time.perf_counter() - bat_dau) * 1000)
    try:
        text = (phan_hoi.choices[0].message.content or "").strip()
    except (AttributeError, IndexError) as exc:
        raise AnswerError("phản hồi không có nội dung") from exc

    if not text:
        raise AnswerError("mô hình trả chuỗi rỗng")

    su_dung = getattr(phan_hoi, "usage", None)
    return AnswerResult(
        text=text,
        citations=nhan,
        ms=ms,
        tokens_in=int(getattr(su_dung, "prompt_tokens", 0) or 0),
        tokens_out=int(getattr(su_dung, "completion_tokens", 0) or 0),
        model=settings.synthesizer_model_name,
    )


async def sinh_stream(
    question: str,
    evidence: Sequence[dict[str, Any]],
    *,
    thieu: Sequence[str] = (),
    requests: Sequence[dict[str, Any]] = (),
    coverage: Sequence[dict[str, Any]] = (),
    strict_note: str = "",
    timeout: float = TIMEOUT_S,
) -> AsyncIterator[str]:
    """Sinh câu trả lời và **phát ra từng mẩu** khi mô hình viết.

    Vì sao có bản riêng thay vì ``sinh``: người dùng phải thấy chữ hiện ra, không phải nhìn
    vòng xoay 5 giây. Nhưng chỉ **bước sinh** được stream — phần định tuyến và truy xuất vẫn
    chạy trọn trước đó, vì chưa biết bằng chứng thì chưa có gì để viết.

    Ném :class:`AnswerError` nếu **chưa** phát được mẩu nào (lỗi cấu hình, mạng, mô hình trả
    rỗng) — nơi gọi cần biết để nói lý do thay vì im lặng. Lỗi giữa dòng thì dừng generator.
    """
    if not dang_bat():
        raise AnswerError("chưa cấu hình SYNTHESIZER_MODEL_NAME / DEEPSEEK_BASE_URL")

    if not evidence:
        raise AnswerError("không có bằng chứng nào để trả lời")

    messages = build_messages(
        question, evidence, thieu=thieu, requests=requests, coverage=coverage,
    )
    client = _client()

    try:
        stream = await asyncio.wait_for(
            client.chat.completions.create(
                model=settings.synthesizer_model_name,
                messages=messages,  # type: ignore[arg-type]
                temperature=settings.synthesizer_temperature,
                max_tokens=settings.synthesizer_max_tokens,
                stream=True,
            ),
            timeout=timeout,
        )
    except TimeoutError as exc:
        raise AnswerError(f"quá hạn {timeout:.0f}s") from exc
    except Exception as exc:  # noqa: BLE001 — mạng/API
        raise AnswerError(f"{type(exc).__name__}: {str(exc)[:160]}") from exc

    da_phat = False
    try:
        async for phan in stream:
            try:
                delta = phan.choices[0].delta.content or ""
            except (AttributeError, IndexError):
                continue
            if delta:
                da_phat = True
                yield delta
    except Exception as exc:  # noqa: BLE001 — đứt giữa dòng
        if not da_phat:
            raise AnswerError(f"{type(exc).__name__}: {str(exc)[:160]}") from exc
        # Đã phát được một phần: dừng êm, người dùng thấy phần đã có thay vì mất trắng.
        logger.warning("Stream đứt giữa dòng: %s", str(exc)[:120])

    if not da_phat:
        raise AnswerError("mô hình không phát ra nội dung nào")


__all__ = [
    "AnswerError",
    "AnswerResult",
    "SYSTEM_PROMPT",
    "TOI_DA_MUC",
    "STATUS_TEXT",
    "build_citations",
    "build_context",
    "build_fallback_answer",
    "build_request_block",
    "verify_contract",
    "build_messages",
    "close_client",
    "dang_bat",
    "nhan_trich_dan",
    "sinh",
    "sinh_stream",
]
