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
from backend.app.cost.service import record_usage
from backend.app.rag import contracts
from backend.app.workflow.fee_policy import fee_prompt_note

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

## Giọng văn và độ rõ

Trả lời tự nhiên, gần gũi, nhưng phải rõ đang nói về thủ tục nào. Khi câu hỏi hoặc ngữ cảnh có
nhiều thủ tục, nêu tên ngắn hoặc mã của thủ tục đó; không dùng “thủ tục này” một cách mơ hồ
khiến người dân nhầm sang thủ tục khác.

Không viết “cổng ghi”, “dữ liệu ghi”, “nguồn ghi”. Hãy nói thẳng sự thật, hoặc dùng cách nói
“thông tin đưa ra…”. Một ý chỉ có một thông tin thì viết một câu, không dùng bullet. Giữ đúng
định dạng số của nguồn, ví dụ “07 ngày”, không tự đổi thành “7 ngày”.

## Trả lời theo trường hợp

Khi ngữ cảnh có nhiều trường hợp (case) của cùng một thủ tục, phải giữ đúng ranh giới từng
trường hợp. Nếu người dùng hỏi chung, trả đủ tất cả trường hợp có trong ngữ cảnh, mỗi trường
hợp một nhóm và nêu rõ tên trường hợp. Nếu người dùng hỏi một trường hợp cụ thể, chỉ trả lời
trường hợp đó. Không lấy hồ sơ của trường hợp này bù sang trường hợp khác.
Với câu hỏi hồ sơ chung, phải giữ đủ mọi giấy tờ và mọi mục "Lưu ý" có trong ngữ cảnh;
không được tóm tắt, không được bỏ mục, không được gộp Lưu ý vào giấy tờ.

Nếu hai ý trong câu hỏi dùng chung một nguồn dữ liệu, không được nói ý sau “chưa có dữ liệu”
chỉ vì ý đó không có nguồn riêng. Chỉ nói thiếu khi trạng thái của chính ý đó là thiếu.

Nếu ngữ cảnh có dòng `{{file:<file_id>}}`, phải giữ nguyên marker đó ngay sau dòng hồ sơ tương
ứng; không đổi id, không bịa id, không chuyển marker sang dòng khác.

## Điều kiện và so sánh

Nếu câu hỏi nêu điều kiện như vùng khó khăn, nhà ở riêng lẻ, đối tượng cụ thể thì phải chọn
đúng mốc tương ứng trong ngữ cảnh. Khi ngữ cảnh có mốc cơ bản và mốc tăng thêm, trình bày
riêng từng mốc và nêu rõ trường hợp nào áp dụng mốc nào; không liệt kê hai mốc ngang hàng
như hai phương án không có điều kiện.

Nếu câu hỏi yêu cầu so sánh hai thủ tục, chỉ so sánh đúng hai thủ tục có trong ngữ cảnh,
nêu cùng một khía cạnh cho cả hai, rồi kết luận chênh lệch nếu dữ liệu cho phép.

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
- Không thêm phần "Lưu ý" ngoài ngữ cảnh. Nếu ngữ cảnh có case "Lưu ý" và câu hỏi là
  hồ sơ chung, phải nêu đầy đủ case đó; nếu người dùng hỏi riêng, chỉ nêu case đó.
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
    "notes": "lưu ý của hồ sơ",
    "steps": "trình tự thực hiện",
    "submission_method": "cách thức nộp / nơi nộp",
    "receiving_agency": "cơ quan tiếp nhận / nộp ở đâu",
    "processing_time": "thời hạn giải quyết",
    "fee": "phí, lệ phí",
    "result": "kết quả nhận được",
    "result_delivery": "cách nhận kết quả",
    "decision_number": "số quyết định ban hành",
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
    "components": "thủ tục thành phần",
    "parent_interlinked": "thủ tục cha / liên thông",
    "procedure_relations": "quan hệ thủ tục",
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
    metadata = muc.get("metadata") or {}
    subject_code = str(metadata.get("subject_code") or "")
    if subject_code:
        subject_name = str(metadata.get("subject_name") or "")
        phan.append(
            f"Quan hệ của thủ tục {subject_code}"
            + (f" — {subject_name}" if subject_name else "")
        )

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

    # Dedupe trong cùng một case; giữ nội dung giống nhau ở các case khác nhau.
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for item in items:
        metadata = item.get("metadata") or {}
        key = (
            " ".join(str(item.get("content") or "").split()),
            int(metadata.get("case_order") or 0),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    items = unique

    # Hồ sơ theo case phải giữ đủ case, không bị cắt bởi quota chung.
    if any((m.get("metadata") or {}).get("case_order") for m in items):
        toi_da = max(toi_da, len(items))

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


def _clean_context(content: object, section_type: str = "") -> str:
    """Bỏ metadata lặp của section trước khi đưa vào prompt."""
    text = " ".join(str(content or "").split())
    if " --- " in text:
        text = text.split(" --- ", 1)[1].strip()
    elif section_type.upper() not in {"METADATA", "FACT"}:
        for prefix in (
            "Tên thủ tục:",
            "Lĩnh vực:",
            "Cấp thực hiện:",
            "Nguồn:",
        ):
            if text.startswith(prefix):
                text = text[len(prefix) :].strip()
    return text


def _context_content(item: dict[str, Any]) -> str:
    """Nội dung section + marker file mẫu để model gắn đúng dòng hồ sơ."""
    text = _clean_context(item.get("content"))
    metadata = item.get("metadata") or {}
    attachments = metadata.get("attachments") or []
    markers: list[str] = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        file_id = str(attachment.get("file_id") or "").strip()
        if not file_id:
            continue
        name = str(attachment.get("file_name") or "").strip()
        markers.append(f"File mẫu: {{{{file:{file_id}}}}} — {name}")
    return "\n".join([text, *markers]) if markers else text


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
            dong.append(_context_content(muc))
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
            dong.append(_context_content(muc))
            dong.append("")
            nhan.append(nhan_trich_dan(muc))

    if theo_yeu_cau.get(None):
        dong.append("### Nguồn bổ sung")
        for muc in theo_yeu_cau[None]:
            dong.append(_nhan_muc(muc))
            dong.append(_context_content(muc))
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
    merged = {
        index
        for item in coverage
        for index in (item.get("merged_from") or ())
    }
    dong = ["CÁC Ý CẦN TRẢ LỜI (đúng thứ tự):"]
    shown = 0
    for index, request in enumerate(requests):
        if index in merged:
            continue
        shown += 1
        facet = str(request.get("facet") or "")
        nhan = NHAN_KHIA_CANH.get(facet, facet or "nội dung")
        scenario = " ".join(str(request.get("scenario") or "").split())
        suffix = f" — tình huống: {scenario}" if scenario else ""
        dong.append(
            f"{shown}. {nhan} — "
            f"{STATUS_TEXT.get(status.get(index, ''), 'chưa xác định')}{suffix}"
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
    "required_documents": ("ho so", "giay to", "thanh phan ho so"),
    "notes": ("luu y", "ghi chu"),
    "steps": ("trinh tu", "cac buoc", "buoc thuc hien"),
    "submission_method": ("cach nop", "noi nop", "hinh thuc nop"),
    "receiving_agency": ("co quan tiep nhan", "nop o dau", "noi tiep nhan"),
    "processing_time": ("thoi han", "bao lau", "thoi gian giai quyet"),
    "fee": ("le phi", "phi", "mien phi"),
    "result": ("ket qua", "ket qua nhan duoc"),
    "result_delivery": ("nhan ket qua", "cach nhan ket qua"),
    "decision_number": ("so quyet dinh", "quyet dinh ban hanh"),
    "legal_basis": ("can cu", "van ban", "can cu phap ly"),
    "requirements": ("dieu kien", "doi tuong", "yeu cau"),
    "general_info": ("thong tin chung",),
    "issuing_agency": ("co quan ban hanh",),
    "implementing_agency": ("co quan thuc hien", "don vi thuc hien"),
    "coordinating_agency": ("co quan phoi hop",),
    "authorized_agency": ("co quan duoc uy quyen",),
    "administrative_level": ("cap thuc hien", "cap nao", "cap xu ly"),
    "field": ("linh vuc",),
    "domain_group": ("nhom thu tuc",),
    "status": ("trang thai",),
    "target_audience": ("doi tuong thuc hien", "doi tuong"),
    "related_procedures": ("thu tuc lien quan",),
    "components": ("thu tuc thanh phan", "thu tuc con"),
    "parent_interlinked": ("thu tuc cha", "lien thong"),
}


def _facet_phrases(label: str, facet: str = "") -> set[str]:
    """Cụm 2–3 từ của một nhãn khía cạnh, đã bỏ dấu — để so trong từng câu trả lời."""
    from backend.app.text_norm import strip_accents

    # Nhãn có dấu phẩy (ví dụ "điều kiện, đối tượng") từng làm bộ kiểm tra
    # tạo ra cụm "dieu kien," và bỏ sót cụm "dieu kien". Bỏ dấu câu trước
    # khi tách từ để kiểm tra nhất quán với câu trả lời đã chuẩn hóa.
    normalized = re.sub(r"[^a-z0-9\s]", " ", strip_accents(label).lower())
    words = normalized.split()
    phrases: set[str] = set(FACET_HINTS.get(facet, ()))
    if words:
        phrases.add(" ".join(words))
    for size in (1, 2, 3):
        for start in range(len(words) - size + 1):
            phrase = " ".join(words[start : start + size])
            if len(phrase) >= 4:
                phrases.add(phrase)
    return phrases


def _evidence_facets(evidence: Sequence[dict[str, Any]]) -> set[str]:
    """Facet đã có bằng chứng cấu trúc, không phụ thuộc cách diễn đạt của mô hình.

    ``section_type`` của chunk là ``REQUIRED_DOCUMENTS``; request facet là
    ``required_documents``. Chuẩn hoá cả hai về cùng dạng để bước kiểm chứng
    biết rằng mục hồ sơ đã thực sự được truy xuất.
    """
    from backend.app.text_norm import strip_accents

    facets: set[str] = set()
    for item in evidence:
        for key in ("facet", "section_type"):
            raw = str(item.get(key) or "").strip()
            if raw:
                facets.add(strip_accents(raw).lower())
    return facets


def _facet_content_present(
    text: str,
    evidence: Sequence[dict[str, Any]],
    facet: str,
) -> bool:
    """Câu trả lời có ít nhất hai từ nội dung lấy từ evidence của facet không.

    Không đòi đúng nhãn "hồ sơ"; chỉ đòi câu trả lời thực sự dùng nội dung của
    mục đã truy xuất. Hai từ là ngưỡng thấp để chấp nhận diễn đạt lại, nhưng
    vẫn phân biệt được câu bỏ sót hoàn toàn.
    """
    from backend.app.text_norm import strip_accents

    wanted = strip_accents(facet).lower()
    answer_tokens = set(
        re.sub(r"[^a-z0-9\s]", " ", strip_accents(text).lower()).split()
    )
    for item in evidence:
        values = {
            strip_accents(str(item.get(key) or "")).lower()
            for key in ("facet", "section_type")
        }
        if wanted not in values:
            continue
        content_tokens = {
            token
            for token in re.sub(
                r"[^a-z0-9\s]",
                " ",
                strip_accents(str(item.get("content") or "")).lower(),
            ).split()
            if len(token) >= 3
        }
        if len(content_tokens & answer_tokens) >= 2:
            return True
    return False


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


def _number_tokens(text: str) -> list[int]:
    """Số trong câu trả lời, bỏ URL và mã thủ tục."""
    clean = re.sub(r"https?://\S+", " ", str(text or ""))
    clean = re.sub(r"\[\d+\]", " ", clean)
    clean = re.sub(r"\b\d{1,3}[.,]\d{5,6}\b", " ", clean)
    values: list[int] = []
    for match in re.finditer(r"\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?\b", clean):
        raw = match.group(0).replace(".", "").replace(",", "")
        if raw.isdigit():
            values.append(int(raw))
    return values


def _number_bases(evidence: Sequence[dict[str, Any]]) -> set[int]:
    values: set[int] = set()
    for item in evidence:
        values.update(_number_tokens(str(item.get("content") or "")))
    return values


def validate_number_claims(
    text: str, evidence: Sequence[dict[str, Any]]
) -> list[str]:
    """Bắt số trong câu trả lời không có trong evidence.

    Cho phép tổng/hiệu của hai mốc evidence (ví dụ 9 + 10 = 19 ngày), vì câu trả lời
    hợp lệ thường phải cộng mốc cơ bản với mốc tăng thêm.
    """
    bases = _number_bases(evidence)
    if not bases:
        return []
    allowed = set(bases)
    values = list(bases)
    for index, first in enumerate(values):
        for second in values[index + 1 :]:
            allowed.add(first + second)
            allowed.add(abs(first - second))
    return [
        f"unsupported_number:{number}"
        for number in _number_tokens(text)
        if number not in allowed
    ]


def verify_contract(
    text: str,
    evidence: Sequence[dict[str, Any]],
    *,
    thieu: Sequence[str] = (),
    covered_facets: Sequence[str] = (),
    requests: Sequence[dict[str, Any]] = (),
    coverage: Sequence[dict[str, Any]] = (),
) -> list[str]:
    """Kiểm tra hợp đồng trả lời sau khi sinh. Trả danh sách lỗi (rỗng = đạt).

    Tất định, không gọi mô hình: bắt đúng lỗi đã đo — phủ nhận bằng chứng đang có, hoặc trả lời
    thiếu ý mà không nói là thiếu.
    """
    issues: list[str] = []
    clean = " ".join(str(text or "").split())
    if not clean:
        return ["empty_answer"]
    from backend.app.text_norm import strip_accents

    has_denial = bool(DENIAL_PATTERN.search(clean))
    if has_denial and evidence and covered_facets and _denial_hits_covered(
        clean, covered_facets, thieu
    ):
        issues.append("denies_available_evidence")
    if thieu and not has_denial:
        issues.append("omits_missing_data")

    status = _status_map(coverage)
    structural_facets = _evidence_facets(evidence)
    for index, request in enumerate(requests):
        if status.get(index) != "covered":
            continue
        facet = str(request.get("facet") or "")
        # general_info là nhãn bao quát: câu trả lời đúng nội dung có thể
        # không chứa nguyên cụm "thông tin chung". Kiểm tra nhãn ở đây chỉ
        # tạo false positive rồi kích hoạt fallback không cần thiết.
        if facet == "general_info":
            continue
        # Ưu tiên tín hiệu cấu trúc: evidence đã có đúng facet và câu trả lời
        # thực sự dùng nội dung của mục đó thì không bắt mô hình phải dùng đúng
        # một cụm từ cố định. Đây là nhánh chính.
        if facet in structural_facets and _facet_content_present(
            clean, evidence, facet
        ):
            continue
        # Fallback từ khóa chỉ dùng khi evidence không mang facet rõ ràng.
        label = NHAN_KHIA_CANH.get(facet, facet)
        phrases = _facet_phrases(label, facet)
        if phrases and not any(phrase in strip_accents(clean).lower() for phrase in phrases):
            issues.append(f"missing_covered_facet:{facet}")
    issues.extend(validate_number_claims(clean, evidence))
    return issues


def _clip_fallback_text(text: str, limit: int = 1200) -> str:
    """Cắt fallback theo ranh giới câu/đoạn, không cắt giữa từ.

    Fallback chỉ dùng sau khi LLM đã retry thất bại; nếu buộc phải dùng thì
    vẫn giữ trọn câu quan trọng thay vì cắt cứng ở 400 ký tự.
    """
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    cut = clean[:limit]
    for separator in (". ", "; ", "! ", "? ", "\n"):
        index = cut.rfind(separator)
        if index >= max(120, int(limit * 0.5)):
            return cut[: index + len(separator)].strip()
    return cut.rstrip() + "…"


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
            _clip_fallback_text(muc.get("content")) for _, muc in chon[:3]
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
                dong.append(f"- {_clip_fallback_text(noi_dung)}")
        phan.append("\n".join(dong))
    return "\n\n".join(phan).strip()


def _case_label(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") or {}
    name = " ".join(str(metadata.get("case_name") or "").split())
    name = name.strip("*-: ").strip()
    if name:
        return name
    return "Nội dung chung"


def _strip_case_prefix(content: str, label: str) -> str:
    """Bỏ tiền tố lặp ``Trường hợp: * <case>:`` khỏi nội dung một section.

    Nguồn dữ liệu có nhiều cách ghi cùng một nhãn case:

    - ``Trường hợp: * Giấy tờ phải nộp: - ...``
    - ``**Đối với trường hợp ...** - Đối với trường hợp ... - + ...``

    Hàm lặp nhiều lần vì nhãn có thể xuất hiện hai lần liên tiếp và có thể
    được bọc markdown. Không cắt phần nội dung phía sau các tiền tố này.
    """
    text = _clean_context(content).strip()
    label = label.strip("*-: ").strip()
    if not label:
        return text.lstrip(" -+*").strip()

    def candidates() -> tuple[str, ...]:
        return (
            f"**{label}**:",
            f"**{label}**",
            f"__{label}__",
            f"*{label}*",
            f"_{label}_",
            f"* {label}:",
            f"* {label} -",
            f"- {label}:",
            f"- {label} -",
            f"+ {label}:",
            f"+ {label} -",
            f"{label}:",
            f"{label} -",
            f"{label} –",
            f"{label} —",
        )

    for _ in range(5):
        before = text
        text = text.lstrip(" -–—+")
        if text.casefold().startswith("trường hợp:"):
            text = text[len("trường hợp:") :].lstrip(" :-–—+*")
        for candidate in candidates():
            if candidate and text.casefold().startswith(candidate.casefold()):
                text = text[len(candidate) :].lstrip(" :-–—+*")
                break
        if text == before:
            break

    return text.strip()


def _is_document_request(requests: Sequence[dict[str, Any]]) -> bool:
    return len(requests) == 1 and str(requests[0].get("facet") or "") in {
        "required_documents",
        "notes",
    }


def build_required_documents_answer(
    evidence: Sequence[dict[str, Any]],
    *,
    requests: Sequence[dict[str, Any]] = (),
    coverage: Sequence[dict[str, Any]] = (),
) -> str:
    """Trả **nguyên văn** toàn bộ mục hồ sơ theo case, không tóm tắt.

    Đây là câu trả lời tất định cho câu hỏi hồ sơ: mọi section đã truy xuất
    đều được đưa vào, kể cả case "Lưu ý". Câu hỏi riêng "Lưu ý" chỉ có
    evidence của case đó nên cũng chỉ trả case đó.
    """
    allowed = {"required_documents", "notes"}
    items = [
        item
        for item in evidence
        if str(item.get("facet") or "") in allowed
        and " ".join(str(item.get("content") or "").split())
    ]
    if not items:
        return ""

    first = items[0]
    code = str(first.get("procedure_code") or "")
    name = str(first.get("procedure_name") or "")
    procedure_label = f"thủ tục {code}" + (f" ({name})" if name else "")
    if not code and not name:
        procedure_label = "hồ sơ"

    facet = str((requests[0] if requests else {}).get("facet") or "")
    if facet == "notes":
        heading = f"Lưu ý của {procedure_label}"
    elif code or name:
        heading = f"Thủ tục {code}" + (f" ({name})" if name else "")
    else:
        heading = "Hồ sơ"

    groups: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for item in items:
        metadata = item.get("metadata") or {}
        order = int(metadata.get("case_order") or 0)
        key = (order, _case_label(item))
        groups.setdefault(key, []).append(item)

    parts = [heading + ":"]
    for (_order, label), group in sorted(
        groups.items(), key=lambda pair: (pair[0][0], pair[0][1])
    ):
        parts.append(f"\n**{label}**")
        seen: set[str] = set()
        for item in group:
            content = _strip_case_prefix(_context_content(item), label)
            if not content or content in seen:
                continue
            seen.add(content)
            parts.append(f"- {content}")

    # Không có nội dung sau khi lọc thì không được bịa.
    return "\n".join(parts).strip() if len(parts) > 1 else ""


def build_messages(
    question: str,
    evidence: Sequence[dict[str, Any]],
    *,
    thieu: Sequence[str] = (),
    requests: Sequence[dict[str, Any]] = (),
    coverage: Sequence[dict[str, Any]] = (),
    strict_note: str = "",
    preferred_name: str = "",
) -> list[dict[str, str]]:
    """Tin nhắn gửi mô hình: lời dẫn + ngữ cảnh + **danh sách mục thiếu** + câu hỏi.

    ``thieu`` do **mã nguồn** tính (khía cạnh đã hỏi mà sau khi truy xuất vẫn rỗng), không do
    mô hình suy ra. Đây là điểm mấu chốt: mô hình chỉ thấy ngữ cảnh nên không thể biết dữ liệu
    có gì; để nó tự kết luận "chưa ghi nhận" chính là lỗi đã đo được.
    """
    ngu_canh, _ = build_context(evidence, requests=requests, coverage=coverage)
    fee_note = fee_prompt_note(list(evidence))
    fee_block = f"{fee_note}\n\n" if fee_note else ""
    name_block = (
        f"CÁCH XƯNG HÔ: Người dùng tự giới thiệu tên **{preferred_name}**. "
        "Khi trả lời, có thể xưng hô bằng tên này thay cho “bạn” nếu câu văn tự nhiên. "
        "Không sửa tên văn bản, trích dẫn pháp luật hoặc nội dung nguồn.\n\n"
        if preferred_name.strip()
        else ""
    )
    khoi_thieu = ""
    if thieu and not requests:
        nhan = ", ".join(NHAN_KHIA_CANH.get(x, x) for x in thieu)
        khoi_thieu = f"CÁC MỤC KHÔNG CÓ DỮ LIỆU (hệ thống đã tìm, không có):\n{nhan}\n\n"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"{name_block}"
                f"{build_request_block(requests, coverage)}"
                f"{fee_block}"
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
    preferred_name: str = "",
    timeout: float = TIMEOUT_S,
) -> AnswerResult:
    """Sinh câu trả lời từ **bằng chứng**. Ném :class:`AnswerError` nếu không dùng được.

    Không bao giờ trả câu trả lời rỗng mà không nói lý do: nơi gọi cần biết để hiện bằng chứng
    thay vì một khung trống.
    """
    if _is_document_request(requests):
        text = build_required_documents_answer(
            evidence,
            requests=requests,
            coverage=coverage,
        )
        if text:
            return AnswerResult(
                text=text,
                citations=build_citations(
                    evidence,
                    requests=requests,
                    coverage=coverage,
                ),
                ms=0,
                tokens_in=0,
                tokens_out=0,
                model="deterministic_required_documents",
            )

    if not dang_bat():
        raise AnswerError("chưa cấu hình SYNTHESIZER_MODEL_NAME / DEEPSEEK_BASE_URL")

    if not evidence:
        raise AnswerError("không có bằng chứng nào để trả lời")

    messages = build_messages(
        question, evidence, thieu=thieu, requests=requests, coverage=coverage,
        preferred_name=preferred_name,
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
    await record_usage(
        stage="answer",
        model=settings.synthesizer_model_name,
        input_tokens=int(getattr(su_dung, "prompt_tokens", 0) or 0),
        cached_tokens=int(
            getattr(getattr(su_dung, "prompt_tokens_details", None), "cached_tokens", 0)
            or 0
        ),
        output_tokens=int(getattr(su_dung, "completion_tokens", 0) or 0),
    )
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
    preferred_name: str = "",
    timeout: float = TIMEOUT_S,
) -> AsyncIterator[str]:
    """Sinh câu trả lời và **phát ra từng mẩu** khi mô hình viết.

    Vì sao có bản riêng thay vì ``sinh``: người dùng phải thấy chữ hiện ra, không phải nhìn
    vòng xoay 5 giây. Nhưng chỉ **bước sinh** được stream — phần định tuyến và truy xuất vẫn
    chạy trọn trước đó, vì chưa biết bằng chứng thì chưa có gì để viết.

    Ném :class:`AnswerError` nếu **chưa** phát được mẩu nào (lỗi cấu hình, mạng, mô hình trả
    rỗng) — nơi gọi cần biết để nói lý do thay vì im lặng. Lỗi giữa dòng thì dừng generator.
    """
    if _is_document_request(requests):
        text = build_required_documents_answer(
            evidence,
            requests=requests,
            coverage=coverage,
        )
        if text:
            yield text
            return

    if not dang_bat():
        raise AnswerError("chưa cấu hình SYNTHESIZER_MODEL_NAME / DEEPSEEK_BASE_URL")

    if not evidence:
        raise AnswerError("không có bằng chứng nào để trả lời")

    messages = build_messages(
        question, evidence, thieu=thieu, requests=requests, coverage=coverage,
        preferred_name=preferred_name,
    )
    client = _client()

    try:
        kwargs: dict[str, Any] = {
            "model": settings.synthesizer_model_name,
            "messages": messages,
            "temperature": settings.synthesizer_temperature,
            "max_tokens": settings.synthesizer_max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        try:
            stream = await asyncio.wait_for(
                client.chat.completions.create(**kwargs),
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001 — provider không hỗ trợ stream usage
            if "stream_options" not in f"{type(exc).__name__} {exc}".lower():
                raise
            kwargs.pop("stream_options", None)
            stream = await asyncio.wait_for(
                client.chat.completions.create(**kwargs),
                timeout=timeout,
            )
    except TimeoutError as exc:
        raise AnswerError(f"quá hạn {timeout:.0f}s") from exc
    except Exception as exc:  # noqa: BLE001 — mạng/API
        raise AnswerError(f"{type(exc).__name__}: {str(exc)[:160]}") from exc

    da_phat = False
    stream_usage: Any = None
    try:
        async for phan in stream:
            stream_usage = getattr(phan, "usage", None) or stream_usage
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

    await record_usage(
        stage="answer",
        model=settings.synthesizer_model_name,
        input_tokens=int(getattr(stream_usage, "prompt_tokens", 0) or 0),
        cached_tokens=int(
            getattr(
                getattr(stream_usage, "prompt_tokens_details", None),
                "cached_tokens",
                0,
            )
            or 0
        ),
        output_tokens=int(getattr(stream_usage, "completion_tokens", 0) or 0),
    )

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
