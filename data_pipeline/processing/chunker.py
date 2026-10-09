"""Chia bản ghi 29 trường thành các chunk theo section nghiệp vụ.

## Vì sao KHÔNG cần regex dò tiêu đề

Hướng PDF phải đoán tiêu đề mục bằng regex. Ở đây cổng DVC **đã phân loại sẵn** nội dung vào
từng trường riêng (``trinh_tu_thuc_hien``, ``thanh_phan_ho_so``…), nên ranh giới chunk **trùng
ranh giới nghiệp vụ** và việc gán ``section_type`` là **ánh xạ tất định** từ tên trường. Bỏ
được hẳn một tầng sai số.

## Hai tầng

**Tầng 1 — theo trường.** 29 trường → 9 ``section_type``. Một section ngắn **vẫn là một chunk
riêng**, không gộp sang section khác — vì mỗi section trả lời một câu hỏi khác nhau
(*"nộp gì?"* ≠ *"mất bao lâu?"* ≠ *"bao nhiêu tiền?"*).

**Tầng 2 — trong section dài.** Cắt theo **thứ tự ưu tiên ranh giới**, không theo số ký tự:

1. **Bước** có đánh số (``Bước 1``, ``a)``, ``1.``) — chỉ 495/1909 ``STEPS`` có dạng này
2. **Hàng** (bảng) hoặc **đoạn** (``\\n``)
3. **Câu** (``. `` ``; `` ``! `` ``? ``)
4. **Mệnh đề** (``, ``) — chỉ khi một câu đơn vẫn quá dài
5. Cắt thẳng theo ký tự — lưới an toàn, **không bao giờ chạy** nếu các cấp trên đúng

## Trần cứng 4.500 ký tự

Lấy từ giới hạn thật của reranker ``qwen3-rerank``: **4.000 token mỗi document**, vượt là
**HTTP 400 chứ không cắt bớt**. Tiếng Việt ≈ 3 ký tự/token → 4.500 ký tự ≈ 1.500 token, còn
biên an toàn.

**Đo trên 1.909 bản ghi thật** (số section vượt trần / số chunk sinh ra):

| Section | Vượt trần | Chunk | Ghi chú |
|---|---:|---:|---|
| ``STEPS`` | 156 | 2.097 | dài nhất 18.896 ký tự |
| ``REQUIRED_DOCUMENTS`` | 140 | 2.172 | dài nhất 55.601 |
| ``SUBMISSION_METHOD`` | 78 | 2.027 | dài nhất 26.418 |
| ``REQUIREMENTS`` | 69 | 1.123 | dài nhất 13.404 |
| ``LEGAL_BASIS`` | **0** | 1.884 | dài nhất 3.023 — **không bao giờ cần cắt** |
| ``RESULT`` | **0** | 1.903 | dài nhất 1.685 — **không bao giờ cần cắt** |

**Biên mềm:** vượt trần mà chỉ do **một đơn vị cuối** thì **giữ nguyên, không tách**. Nhờ vậy
một bảng 4.600 ký tự với hàng cuối 300 ký tự vẫn là **một chunk**, thay vì sinh chunk thứ hai
chỉ chứa 300 ký tự vụn.

## Hàng là ĐƠN VỊ CẮT, không phải đơn vị chunk

Đo trên dữ liệu thật: nếu 1 hàng = 1 chunk thì 3 trường bảng sinh **hàng chục nghìn chunk**, và
**74,3% số hàng ngắn hơn 200 ký tự** (có hàng chỉ là ``'-'`` hay ``'Lưu ý'``). Tệ hơn, câu hỏi
*"cần nộp những gì?"* cần **cả danh sách** — chia nhỏ sẽ trả lời **thiếu**.

## Bảng phải ghép CẶP dòng

``can_cu_phap_ly``, ``thanh_phan_ho_so`` và ``cach_thuc_thuc_hien`` là bảng dùng **tab phân
cách cột**. Nếu cắt theo từng dòng thì mỗi ô thành một chunk riêng:

```text
Luật Bảo hiểm xã hội     ← chunk 1
58/2014/QH13             ← chunk 2  (vô nghĩa khi đứng một mình)
```

Vì vậy mỗi **hàng** được làm phẳng thành một dòng bằng cách nối các ô với `` · `` — giữ nguyên
nội dung, bỏ tab phân cách (tab chỉ có nghĩa khi còn cấu trúc bảng, mà chunk là văn bản phẳng).

## Luật sentinel

Với trường mang giá trị sentinel (``is_sentinel``), chunk **GIỮ trường** nhưng **đổi cách diễn
đạt** thành *"cổng chưa ghi nhận thông tin"*:

* **KHÔNG bỏ trường.** Người dùng hỏi *"thủ tục A liên quan tới thủ tục nào?"* — bỏ trường thì
  LLM không có nguồn nào và sẽ trả lời *"không có thủ tục liên quan"*, một **khẳng định sai**
  vì dữ liệu CÓ ghi (chỉ là ghi "chưa có").
* **KHÔNG để nguyên** ``"Không có thông tin"`` — LLM dễ đọc thành *"không có"*, khác nghĩa.
* **Riêng ``FEE`` và ``PROCESSING_TIME`` thì KHÔNG sinh chunk** khi
  ``phi.loai == 'CHUA_XAC_DINH'`` / ``thoi_han.loai == 'CHUA_XAC_DINH'`` — hai trường này đã có
  cờ cấu trúc riêng, không cần câu văn bản.

## `RESULT` cần tiền tố ngữ cảnh

1.666/1.903 ``RESULT`` ngắn hơn 200 ký tự, nhiều cái chỉ 14 ký tự (``'Giấy khai sinh'``). Vector
của một cụm 14 ký tự trơ trọi rất yếu, nên chunk `RESULT` được chèn câu dẫn **cố định của ta**
(nêu rõ đây là kết quả của thủ tục) — không bịa nội dung, chỉ đổi cách diễn đạt.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from data_pipeline.crawler.transform import FEE_TYPE_LABELS
from data_pipeline.processing.normalizer import is_sentinel

# ---------------------------------------------------------------------------
# Hằng số
# ---------------------------------------------------------------------------

#: Trần cứng mỗi chunk, tính bằng ký tự. Xem docstring module để biết nguồn gốc con số.
CHAR_LIMIT = 4500

#: Phiên bản bộ chunker. Đổi khi luật cắt thay đổi để phân biệt chunk cũ / mới.
CHUNKER_VERSION = "5.0"

#: Câu thay thế cho mọi giá trị sentinel. KHÔNG nói "không có" — xem docstring module.
SENTINEL_TEXT = "cổng chưa ghi nhận thông tin"

#: 9 loại section. Thứ tự trong tuple là thứ tự xuất chunk của một thủ tục.
SECTION_TYPES = (
    "GENERAL_INFO",
    "STEPS",
    "SUBMISSION_METHOD",
    "REQUIRED_DOCUMENTS",
    "LEGAL_BASIS",
    "RESULT",
    "REQUIREMENTS",
    "FEE",
    "PROCESSING_TIME",
)

#: Ánh xạ tất định tên trường → section_type. Đây là "Tầng 1" — không dò tiêu đề bằng regex.
#: Khóa là **tên trường dữ liệu** nên giữ tiếng Việt: đây là hợp đồng dữ liệu với cổng DVC.
FIELD_TO_SECTION: dict[str, str] = {
    "trinh_tu_thuc_hien": "STEPS",
    "cach_thuc_thuc_hien": "SUBMISSION_METHOD",
    "thanh_phan_ho_so": "REQUIRED_DOCUMENTS",
    "can_cu_phap_ly": "LEGAL_BASIS",
    "ket_qua_xu_ly": "RESULT",
    "yeu_cau_dieu_kien": "REQUIREMENTS",
}

#: Tiêu đề hiển thị của từng section, dùng trong header chunk.
SECTION_TITLES: dict[str, str] = {
    "GENERAL_INFO": "Thông tin chung",
    "STEPS": "Trình tự thực hiện",
    "SUBMISSION_METHOD": "Cách thức thực hiện",
    "REQUIRED_DOCUMENTS": "Thành phần, số lượng hồ sơ",
    "LEGAL_BASIS": "Căn cứ pháp lý",
    "RESULT": "Kết quả xử lý",
    "REQUIREMENTS": "Yêu cầu, điều kiện thực hiện",
    "FEE": "Phí, lệ phí",
    "PROCESSING_TIME": "Thời hạn giải quyết",
}

#: Đơn vị thời hạn (mã trong JSON) → chữ tiếng Việt để render.
TIME_UNIT_LABELS: dict[str, str] = {
    "WORKING_DAY": "Ngày làm việc",
    "DAY": "Ngày",
    "HOUR": "Giờ",
    "MONTH": "Tháng",
    "YEAR": "Năm",
    "OTHER": "Đơn vị khác",
}


def _time_unit_label(unit: str) -> str:
    """Nhãn tiếng Việt của đơn vị thời hạn. Mã lạ thì trả về nguyên mã."""
    return TIME_UNIT_LABELS.get(unit, unit)


#: Trường định danh gom vào chunk GENERAL_INFO, theo đúng thứ tự hiển thị.
#: Khóa là **tên trường dữ liệu** nên giữ tiếng Việt; giá trị là nhãn hiển thị.
IDENTITY_FIELDS: tuple[tuple[str, str], ...] = (
    ("ma_thu_tuc", "Mã thủ tục"),
    ("ten_thu_tuc", "Tên thủ tục"),
    ("so_quyet_dinh", "Số quyết định"),
    ("cap_thuc_hien", "Cấp thực hiện"),
    ("loai_thu_tuc", "Loại thủ tục"),
    ("linh_vuc", "Lĩnh vực"),
    ("doi_tuong_thuc_hien", "Đối tượng thực hiện"),
    ("co_quan_co_tham_quyen", "Cơ quan có thẩm quyền"),
    ("dia_chi_tiep_nhan", "Địa chỉ tiếp nhận hồ sơ"),
    ("co_quan_duoc_uy_quyen", "Cơ quan được ủy quyền"),
    ("co_quan_phoi_hop", "Cơ quan phối hợp"),
    ("co_quan_thuc_hien", "Cơ quan thực hiện"),
    ("co_quan_ban_hanh", "Cơ quan ban hành"),
    ("thu_tuc_lien_quan", "Thủ tục hành chính liên quan"),
    ("trang_thai", "Trạng thái"),
    ("ngay_cap_nhat", "Ngày cập nhật"),
)

# ---------------------------------------------------------------------------
# Ranh giới cắt — 4 cấp theo thứ tự ưu tiên
# ---------------------------------------------------------------------------

# Cấp 1: đánh số bước. Nhận "Bước N", chữ cái "a)", hoặc "1." ở đầu dòng.
_STEPS_PATTERN = re.compile(r"^\s*bước\s*\.?\s*(\d+)", re.IGNORECASE)
_NUMBERED_PATTERN = re.compile(r"^\s*(\d{1,2})\s*[.)]\s+\S")
_LETTERED_PATTERN = re.compile(r"^\s*([a-zđ])\s*[.)]\s+\S", re.IGNORECASE)

# Cấp 3: ranh giới câu. Giữ dấu câu ở lại với câu trước (lookbehind).
_SENTENCE_PATTERN = re.compile(r"(?<=[.;!?])\s+")
# Cấp 4: ranh giới mệnh đề.
_CLAUSE_PATTERN = re.compile(r"(?<=,)\s+")


def _is_step_label(line: str) -> bool:
    """True nếu dòng này MỞ ĐẦU một bước/đoạn được đánh số."""
    return bool(
        _STEPS_PATTERN.match(line) or _NUMBERED_PATTERN.match(line) or _LETTERED_PATTERN.match(line)
    )


def _flatten_row(line: str) -> str:
    """Làm phẳng MỘT hàng bảng: mỗi ô cách nhau `` · ``, bỏ tab phân cách.

    ``'Tên văn bản\\tMã văn bản'`` → ``'Tên văn bản · Mã văn bản'``

    Ô rỗng bị bỏ (không sinh ``" · · "``). Tab chỉ có nghĩa khi còn cấu trúc bảng; chunk là
    văn bản phẳng nên giữ tab chỉ làm nhiễu embedding.
    """
    if "\t" not in line:
        return line.strip()
    cells = [cell.strip() for cell in line.split("\t")]
    return " · ".join(cell for cell in cells if cell)


#: Tiêu đề cột của các bảng gặp trong dữ liệu — không mang nội dung nghiệp vụ nên bỏ.
_TABLE_HEADERS = frozenset(
    {
        "tên giấy tờ · mẫu đơn, tờ khai · số lượng",
        "tên văn bản pháp lý · mã văn bản",
        "hình thức nộp · thời gian · phí, lệ phí · mô tả",
        "hình thức nộp · thời gian · phí, lệ phí",
        "tên giấy tờ · số lượng",
    }
)


def _is_table_header_row(line: str) -> bool:
    """True nếu dòng chỉ là tiêu đề cột của bảng.

    Xoá vì chúng lặp lại nhiều lần trong cùng một trường (mỗi khối bảng có một tiêu đề) và
    không trả lời câu hỏi nào của người dân.
    """
    return _flatten_row(line).lower() in _TABLE_HEADERS


def _split_into_units(text: str) -> list[str]:
    """Tách text thành các đơn vị cắt **cấp 1–2**: bước đánh số, hàng bảng, hoặc đoạn.

    Quy tắc:

    * Dòng tiêu đề cột của bảng bị **bỏ**.
    * Nếu văn bản có đánh số bước thì mỗi **bước** là một đơn vị (gồm dòng nhãn ``Bước N`` và
      mọi dòng theo sau tới bước kế tiếp). Nhãn được **giữ** vì nó mang thông tin thứ tự.
    * Nếu không đánh số thì mỗi **dòng** là một đơn vị, đã làm phẳng bảng.
    """
    lines = [line for line in text.split("\n") if line.strip()]
    lines = [line for line in lines if not _is_table_header_row(line)]
    if not lines:
        return []

    if not any(_is_step_label(line) for line in lines):
        return [_flatten_row(line) for line in lines]

    # Gom theo bước: mỗi nhãn bước mở một đơn vị mới.
    groups: list[list[str]] = []
    for line in lines:
        if _is_step_label(line) or not groups:
            groups.append([])
        groups[-1].append(_flatten_row(line))
    return ["\n".join(child for child in group if child) for group in groups]


def _split_clauses(paragraph: str, limit: int) -> list[str]:
    """Cắt một đoạn quá dài thành các mảnh ≤ ``limit``, ưu tiên câu rồi tới mệnh đề.

    Lưới an toàn cuối cùng là cắt thẳng theo ký tự — **không bao giờ chạy** nếu dữ liệu bình
    thường, nhưng phải có để bảo đảm trần cứng tuyệt đối (reranker trả HTTP 400 nếu vượt).
    """
    for pattern in (_SENTENCE_PATTERN, _CLAUSE_PATTERN):
        pieces = [piece for piece in pattern.split(paragraph) if piece.strip()]
        if len(pieces) > 1 and all(len(piece) <= limit for piece in pieces):
            return pieces

    # Cấp 5 — lưới an toàn: cắt thẳng, cố dừng ở khoảng trắng gần nhất.
    out: list[str] = []
    remaining = paragraph
    while len(remaining) > limit:
        cut_at = remaining.rfind(" ", 0, limit)
        if cut_at < limit // 2:
            cut_at = limit
        out.append(remaining[:cut_at].strip())
        remaining = remaining[cut_at:].strip()
    if remaining:
        out.append(remaining)
    return out


def _merge_units(units: list[str], limit: int = CHAR_LIMIT) -> list[str]:
    """Gộp các đơn vị cắt thành thân chunk sao cho **thân + header ≤ ``limit``**.

    ``limit`` ở đây là **ngân sách cho phần thân**, không phải trần cuối cùng — hàm gọi phải
    trừ sẵn độ dài header. Xem ``chunk_record``.

    **Biên mềm:** nếu phần đã gộp vượt ngân sách mà **nguyên nhân chỉ là đơn vị cuối cùng vừa
    thêm**, thì giữ nguyên và đóng chunk — không tách đơn vị đó ra làm chunk riêng. Nhờ vậy một
    bảng 4.600 ký tự với hàng cuối 300 ký tự vẫn là **một chunk**.

    **Đơn vị đơn lẻ dài hơn ngân sách thì BẮT BUỘC cắt** — biên mềm không áp cho nó, vì nếu
    không chunk sẽ vượt trần và reranker trả HTTP 400.
    """
    if not units:
        return []
    limit = max(1, limit)

    # Đơn vị đơn lẻ dài hơn ngân sách thì phải cắt nhỏ trước khi gộp.
    flattened: list[str] = []
    for unit in units:
        if len(unit) <= limit:
            flattened.append(unit)
        else:
            flattened.extend(_split_clauses(unit, limit))

    out: list[str] = []
    current: list[str] = []
    size = 0
    for unit in flattened:
        step = len(unit) + (1 if current else 0)
        if current and size + step > limit:
            out.append("\n".join(current))
            current, size = [unit], len(unit)
        else:
            current.append(unit)
            size += step
    if current:
        out.append("\n".join(current))
    return out


# ---------------------------------------------------------------------------
# Render section
# ---------------------------------------------------------------------------


def _render_identity(value: Any) -> str:
    """Render một giá trị định danh: sentinel → câu chuẩn, rỗng → bỏ, còn lại giữ nguyên."""
    if value is None:
        return ""
    if isinstance(value, list):
        value = ", ".join(str(item).strip() for item in value if str(item).strip())
    text = str(value).strip()
    if not text:
        return ""
    if is_sentinel(text):
        return SENTINEL_TEXT
    return text


def _format_amount(amount: int | float) -> str:
    """``250000`` → ``'250.000'`` (dấu chấm phân cách nghìn kiểu Việt Nam)."""
    if isinstance(amount, float) and amount.is_integer():
        amount = int(amount)
    if isinstance(amount, int):
        return f"{amount:,}".replace(",", ".")
    return str(amount)


def render_general_info(record: dict[str, Any], budget: int = CHAR_LIMIT) -> list[str]:
    """Chunk thông tin định danh. Thường đúng **một** chunk mỗi thủ tục.

    ``budget`` là số ký tự còn lại cho phần thân sau khi trừ header. Có **2/1909** thủ tục
    (`1.115362` tên 4.700 ký tự, `1.115369` tên 5.900 ký tự) dài tới mức riêng phần định danh đã
    vượt trần, nên hàm này cũng phải tôn trọng ngân sách — nếu không reranker trả HTTP 400.
    """
    lines: list[str] = []
    for field, label in IDENTITY_FIELDS:
        rendered = _render_identity(record.get(field))
        if rendered:
            lines.append(f"{label}: {rendered}")
    if not lines:
        return []
    return _merge_units(lines, budget)


def render_fee(record: dict[str, Any], budget: int = CHAR_LIMIT) -> list[str]:
    """Chunk `FEE` render từ ``phi.muc_chi_tiet`` — **không** đọc ``so_tien`` đơn lẻ.

    Đọc ``muc_chi_tiet`` mới trả lời được *"trường hợp của tôi đóng bao nhiêu?"*. Nếu chỉ đọc
    ``so_tien`` thì mất hết điều kiện và thủ tục 10 mức phí (`1.014257`) chỉ còn một con số.

    ``budget`` là số ký tự còn lại cho phần thân sau khi trừ header — xem
    ``render_text_section``. Hàm này chỉ cắt khi thật cần, vì cắt là **mất mức phí**.
    """
    fee = record.get("phi") or {}
    fee_type = fee.get("loai")
    if fee_type == "CHUA_XAC_DINH":
        return []

    lines: list[str] = [f"Loại: {FEE_TYPE_LABELS.get(fee_type, fee_type)}"]

    if fee_type == "MIEN_PHI":
        lines.append("Cổng ghi thủ tục này miễn phí.")
    elif fee_type == "THEO_VAN_BAN":
        documents = [str(item).strip() for item in (fee.get("van_ban") or []) if str(item).strip()]
        if documents:
            lines.append(f"Áp dụng theo: {', '.join(documents)}")
    elif fee_type == "THEO_QUY_DINH_CHUNG":
        lines.append("Cổng không nêu số tiền cụ thể mà ghi áp dụng theo quy định hiện hành.")

    items = fee.get("muc_chi_tiet") or []
    if items:
        lines.append("")
        lines.append("Các mức cụ thể:")
        for item in items:
            amount = item.get("so_tien")
            condition = str(item.get("dieu_kien") or "").strip()
            if amount is None:
                # Không có số tiền thì điều kiện LÀ thông tin duy nhất.
                lines.append(f"- {condition}" if condition else f"- {SENTINEL_TEXT}")
            elif condition:
                lines.append(f"- {_format_amount(amount)} đồng — {condition}")
            else:
                # `dieu_kien` rỗng khi cổng chỉ đăng ký MỘT mức phí chung, không kèm điều
                # kiện. Ghi rõ để không sinh dấu gạch treo, và để LLM không suy diễn ra điều
                # kiện. 35/1909 bản ghi ở đúng ca này (ví dụ `1.006468`, `2.000635`).
                lines.append(
                    f"- {_format_amount(amount)} đồng (mức phí phổ biến, "
                    "cổng không kèm điều kiện riêng)"
                )
    else:
        description = _render_identity(fee.get("mo_ta_goc"))
        if description:
            lines.append("")
            lines.append(f"Nội dung cổng ghi: {description}")

    body = "\n".join(lines)
    # Chỉ cắt khi thật vượt — mỗi lần cắt là một lần có nguy cơ tách rời "số tiền" khỏi
    # "điều kiện" của nó nếu cắt vào giữa một dòng.
    if len(body) <= budget:
        return [body]
    return _merge_units([line for line in body.split("\n") if line.strip()], budget)


def render_processing_time(record: dict[str, Any], budget: int = CHAR_LIMIT) -> list[str]:
    """Chunk `PROCESSING_TIME` render từ ``thoi_han.muc_chi_tiet`` — **không** đọc ``moc`` phẳng.

    ``moc`` mất điều kiện. Thủ tục `2.000115` có nhiều mốc **cùng 3 Ngày làm việc** nhưng
    **điều kiện khác nhau**; đọc ``moc`` thì chúng nhìn giống hệt nhau.
    """
    processing_time = record.get("thoi_han") or {}
    if processing_time.get("loai") == "CHUA_XAC_DINH":
        return []

    items = processing_time.get("muc_chi_tiet") or []
    lines: list[str] = []
    if items:
        lines.append("Các mốc thời hạn theo từng trường hợp:")
        for item in items:
            value = item.get("gia_tri")
            unit = _time_unit_label(str(item.get("don_vi")))
            methods = [str(child) for child in (item.get("hinh_thuc") or []) if str(child).strip()]
            body = f"- {value} {unit}"
            if methods:
                body += f" (nộp {', '.join(methods)})"
            condition = str(item.get("dieu_kien") or "").strip()
            lines.append(f"{body} — {condition}" if condition else body)
    else:
        lines.append("Cổng không nêu mốc thời hạn cụ thể.")

    if processing_time.get("nhieu_don_vi"):
        lines.append("")
        lines.append("Lưu ý: thủ tục này có nhiều mốc dùng ĐƠN VỊ khác nhau, không cộng dồn.")

    # Ngăn cách mỗi mốc bằng dòng trống cho dễ đọc khi chunk bị cắt thành nhiều phần.
    body = "\n\n".join([lines[0]] + lines[1:]) if len(lines) > 1 else lines[0]
    if len(body) <= budget:
        return [body]
    return _merge_units([line for line in lines if line.strip()], budget)


def render_text_section(
    record: dict[str, Any],
    field: str,
    section: str,
    budget: int = CHAR_LIMIT,
) -> list[str]:
    """Render một section văn bản thành danh sách thân chunk.

    ``budget`` là số ký tự còn lại cho **phần thân** sau khi trừ header. Hàm gọi phải tính
    sẵn — nếu không thì ``text = header + thân`` sẽ vượt trần dù thân đã đúng ngân sách. Đây là
    bug thật đã gặp: chunk `PROCESSING_TIME` của `1.014257` dài **67.651 ký tự** vì trần chỉ
    được áp cho thân.

    Sentinel → một chunk chứa câu chuẩn. Rỗng → **không** sinh chunk.
    """
    value = record.get(field)
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []

    if is_sentinel(text):
        return [SENTINEL_TEXT]

    # `RESULT` hay chỉ là một cụm rất ngắn ('Giấy khai sinh' 14 ký tự). Vector của chuỗi ngắn
    # như vậy rất yếu, nên chèn câu dẫn CỐ ĐỊNH CỦA TA nêu rõ đây là kết quả của thủ tục.
    # Không bịa nội dung — chỉ đổi cách diễn đạt, giống luật sentinel.
    if section == "RESULT":
        return [f"Kết quả người dân nhận được khi hoàn thành thủ tục: {text}."]

    return _merge_units(_split_into_units(text), budget)


# ---------------------------------------------------------------------------
# Header + lắp ghép chunk
# ---------------------------------------------------------------------------


def full_header(record: dict[str, Any], section: str) -> str:
    """Header 4 dòng cho chunk ĐẦU của một section.

    ``ten_thu_tuc`` lấy **y nguyên** — không viết hoa lại, không cắt ngắn. Đây là thứ giúp
    embedding biết chunk thuộc thủ tục nào mà không cần đọc metadata.
    """
    name = str(record.get("ten_thu_tuc") or "").strip()
    source_field = str(record.get("linh_vuc") or "").strip()
    level = str(record.get("cap_thuc_hien") or "").strip()
    url = str(record.get("detail_url") or "").strip()
    return (
        f"Tên thủ tục: {name}\n"
        f"{SECTION_TITLES.get(section, section)}\n"
        f"Lĩnh vực: {source_field} · Cấp thực hiện: {level}\n"
        f"Nguồn: {url}\n"
        "---"
    )


def compact_header(record: dict[str, Any], section: str) -> str:
    """Header gọn cho chunk TIẾP THEO của cùng section.

    Chunk đầu đã có ``detail_url`` nên chunk sau chỉ cần đủ để truy ngược và để embedding biết
    ngữ cảnh. Tên thủ tục vẫn giữ vì embedding của một mẩu bảng trơ trọi sẽ rất yếu.
    """
    code = str(record.get("ma_thu_tuc") or "").strip()
    name = str(record.get("ten_thu_tuc") or "").strip()
    return f"Thủ tục: {code} · {name}\n{SECTION_TITLES.get(section, section)}\n---"


def _chunk_metadata(record: dict[str, Any]) -> dict[str, Any]:
    """Metadata cấp thủ tục, **kế thừa 100%** xuống mọi chunk.

    Không phân loại lại từng chunk bằng LLM — mọi chunk của một thủ tục mang cùng bộ nhãn.
    """
    return {
        "ten_thu_tuc": record.get("ten_thu_tuc", ""),
        "domain_group": record.get("domain_group", ""),
        "source_field": record.get("linh_vuc", ""),
        "cap_thuc_hien": record.get("cap_thuc_hien", ""),
        "co_quan_thuc_hien": record.get("co_quan_thuc_hien", ""),
        "detail_url": record.get("detail_url", ""),
        "content_hash": record.get("content_hash", ""),
    }


def make_chunk_id(code: str, section: str, order: int) -> str:
    """``{procedure_code}:{section_type}:{chunk_order}`` — ổn định giữa các lần chạy."""
    return f"{code}:{section}:{order}"


def _build_chunks(
    record: dict[str, Any],
    section: str,
    bodies: list[str],
    header: str | None = None,
) -> list[dict[str, Any]]:
    """Ghép header + thân thành các bản ghi chunk hoàn chỉnh.

    ``header`` cho phép hàm gọi truyền vào header đã tính sẵn — tránh gọi ``full_header`` hai
    lần cho cùng một section (một lần để tính ngân sách, một lần để ghép).
    """
    code = str(record.get("ma_thu_tuc") or "").strip()
    metadata = _chunk_metadata(record)
    full = header if header is not None else full_header(record, section)
    out: list[dict[str, Any]] = []
    for index, body in enumerate(bodies, start=1):
        head = full if index == 1 else compact_header(record, section)
        text = f"{head}\n{body}".strip()
        out.append(
            {
                "chunk_id": make_chunk_id(code, section, index),
                "procedure_code": code,
                "section_type": section,
                "section_title": SECTION_TITLES.get(section, section),
                "chunk_order": index,
                "text": text,
                "char_count": len(text),
                "chunker_version": CHUNKER_VERSION,
                **metadata,
            }
        )
    return out


def body_budget(record: dict[str, Any], section: str, header: str) -> int:
    """Số ký tự còn lại cho **phần thân** của chunk đầu, sau khi trừ header.

    Phải trừ header vì ``text = header + "\\n" + thân``. Bỏ qua bước này chính là bug đã gặp:
    chunk `PROCESSING_TIME` của `1.014257` dài **67.651 ký tự** vì trần chỉ áp cho thân.

    Trừ thêm 1 ký tự cho dấu xuống dòng nối header với thân.
    """
    return max(1, CHAR_LIMIT - len(header) - 1)


def chunk_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Sinh toàn bộ chunk của một bản ghi 29 trường.

    Thứ tự chunk theo ``SECTION_TYPES``. Trả list rỗng nếu bản ghi không có ``ma_thu_tuc``.
    """
    code = str(record.get("ma_thu_tuc") or "").strip()
    if not code:
        return []

    out: list[dict[str, Any]] = []

    def _emit(section: str, bodies: list[str]) -> None:
        """Tính header MỘT lần, dùng cho cả ngân sách lẫn lúc ghép."""
        header = full_header(record, section)
        out.extend(_build_chunks(record, section, bodies, header))

    # GENERAL_INFO luôn có — ngay cả khi mọi trường định danh đều rỗng, vì người dân vẫn cần
    # tra được "thủ tục này là gì".
    _emit(
        "GENERAL_INFO",
        render_general_info(
            record, body_budget(record, "GENERAL_INFO", full_header(record, "GENERAL_INFO"))
        )
        or [SENTINEL_TEXT],
    )

    for field, section in FIELD_TO_SECTION.items():
        header = full_header(record, section)
        _emit(
            section,
            render_text_section(record, field, section, body_budget(record, section, header)),
        )

    for section, renderer in (
        ("FEE", render_fee),
        ("PROCESSING_TIME", render_processing_time),
    ):
        header = full_header(record, section)
        _emit(section, renderer(record, body_budget(record, section, header)))

    return out


def hash_chunk(chunk: dict[str, Any]) -> str:
    """Băm nội dung chunk — dùng để phát hiện chunk đổi giữa hai lần chạy."""
    return hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest()
