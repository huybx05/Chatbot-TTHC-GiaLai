"""Chuyển response API thành JSON chuẩn hóa.

**Bộ trường gồm 29 trường**, chia 3 nhóm cộng phần bổ sung:

* Nhóm định danh và nội dung bám sát file mẫu ``1.115368.json`` (text có tab).
* Nhóm **bổ sung Mức 1** phục vụ toàn vẹn dữ liệu: ``co_quan_ban_hanh``,
  ``ngay_cap_nhat``, ``content_hash``, ``ngay_crawl``.
* Nhóm **bổ sung Mức 2** phục vụ truy vấn CSDL: ``phi``, ``thoi_han`` ở dạng có cấu
  trúc. Không có hai trường này thì PostgreSQL chỉ là kho text — không lọc được
  "phí dưới 500.000 đồng" hay "thời hạn ≤ 3 ngày làm việc" bằng index.

Quy ước giá trị:

* Trường API không trả hoặc trả rỗng → ``""`` (chuỗi rỗng), giống file mẫu.
* Trường API có trả nhưng `description` là chữ "Không" → ``"Không có thông tin"``,
  đồng bộ với cách file mẫu xử lý `yeu_cau_dieu_kien`.
* Trường nhiều giá trị → nối bằng ``, `` thành một chuỗi, giống file mẫu.

Quy tắc xử lý phí và thời hạn, rút ra từ khảo sát dữ liệu thật:

* **Phí có 5 loại.** ``fees[].value = 0`` **không** đồng nghĩa miễn phí — phải đọc
  ``description`` mới phân loại được. Khảo sát cho thấy phần lớn thủ tục trên cổng
  không công bố mức phí, nên ``CHUA_XAC_DINH`` là kết quả bình thường, không phải lỗi.
* **Phí phải giữ CẶP (số tiền, điều kiện).** API trả mỗi mục phí kèm ``description`` nói
  điều kiện áp dụng. Thủ tục ``1.004376`` có **8 mức phí** cho 8 trường hợp khác nhau.
  Nếu chỉ lưu một số tiền thì không trả lời được *"trường hợp của tôi đóng bao nhiêu?"*.
  Vì vậy ``phi`` có thêm ``muc_chi_tiet`` — mảng ``{so_tien, dieu_kien}`` đã khử trùng
  theo **cặp**, không theo số tiền (cùng số tiền vẫn có thể là hai trường hợp khác nhau).
  Xem ``_fee_detail_items``.
* **Thời hạn không phải lúc nào cũng là số.** Có thủ tục trả ``processingTime = 0``
  với ``unit = "OTHER"`` nhưng mô tả ghi "90 ngày". Khi đó phải trích mốc từ mô tả.
* **Không cộng dồn thời hạn.** Cùng một thời hạn của cả thủ tục bị ghi lặp ở nhiều
  bước, nên tóm tắt phải lấy **giá trị lớn nhất theo từng đơn vị**, và đánh dấu
  ``nhieu_don_vi`` khi có nhiều đơn vị khác nhau.

**Về ``content_hash``:** băm **nội dung nghiệp vụ**, KHÔNG băm các trường phiên bản
(``ngay_crawl``, ``ngay_cap_nhat``, ``content_hash``). Nếu băm cả ``ngay_crawl`` thì
mỗi lần crawl hash lại đổi, và incremental load trở nên vô nghĩa vì lúc nào cũng thấy
"đã thay đổi".
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from .catalog import CatalogEntry

logger = logging.getLogger(__name__)

DETAIL_URL_TEMPLATE = "https://dichvucong.gov.vn/thu-tuc-hanh-chinh/{formality_id}"

NO_INFORMATION = "Không có thông tin"

# Tên trường phiên bản — không đưa vào content_hash.
VERSION_FIELDS = frozenset({"content_hash", "ngay_cap_nhat", "ngay_crawl"})

SUBMISSION_LABELS = {
    "DIRECT": "Trực tiếp",
    "ONLINE": "Trực tuyến",
    "POSTAL": "Bưu chính",
    "OTHER": "Khác",
}

TIME_UNIT_LABELS = {
    "WORKING_DAY": "Ngày làm việc",
    "DAY": "Ngày",
    "HOUR": "Giờ",
    "MONTH": "Tháng",
    "YEAR": "Năm",
    "OTHER": "Khác",
}

# Đơn vị dùng được trực tiếp từ trường số.
USABLE_UNITS = {"WORKING_DAY", "DAY", "HOUR", "MONTH", "YEAR"}


def _submission_label(method: dict[str, Any]) -> str:
    """Nhãn tiếng Việt của hình thức nộp. Không có thì trả về nguyên giá trị gốc."""
    raw = _text(method.get("submissionMethod"))
    return SUBMISSION_LABELS.get(raw, raw)


def _time_unit_label(unit: str) -> str:
    """Nhãn tiếng Việt của đơn vị thời gian."""
    return TIME_UNIT_LABELS.get(unit, unit)

    # Số hiệu văn bản pháp lý, ví dụ: 10/2024/TT-BTC, 101/2024/NĐ-CP.


DOCUMENT_CODE_PATTERN = re.compile(
    r"\b\d+/\d{4}/(?:TT|NĐ|QĐ|NQ|CT|Luật)[-A-Za-zĐ0-9]*",
    re.IGNORECASE,
)

# Mốc thời gian trong mô tả, ví dụ: "90 ngày", "21 ngày làm việc".
TIME_SPAN_PATTERN = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(ngày làm việc|ngày|giờ|tháng|năm)",
    re.IGNORECASE,
)

FREE_OF_CHARGE_PATTERN = re.compile(r"miễn\s*phí|không\s*thu|không\s*phải\s*nộp", re.IGNORECASE)

TIME_UNIT_CODES = {
    "ngày làm việc": "WORKING_DAY",
    "ngày": "DAY",
    "giờ": "HOUR",
    "tháng": "MONTH",
    "năm": "YEAR",
}

# Loại phí hợp lệ — 5 loại theo mục 1.2b của PROJECT_GUIDE_V4_1.md.
FEE_TYPES = ("SO_TIEN", "MIEN_PHI", "THEO_VAN_BAN", "THEO_QUY_DINH_CHUNG", "CHUA_XAC_DINH")

#: Nhãn tiếng Việt của từng loại phí, dùng khi render chunk `FEE` ở Giai đoạn 5.
#: Đặt ở đây (không đặt ở chunker) để chỉ có MỘT nguồn cho 5 loại phí.
FEE_TYPE_LABELS: dict[str, str] = {
    "SO_TIEN": "Mức cụ thể",
    "MIEN_PHI": "Miễn phí",
    "THEO_VAN_BAN": "Theo văn bản",
    "THEO_QUY_DINH_CHUNG": "Theo quy định chung",
    "CHUA_XAC_DINH": "Chưa xác định",
}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _join_names(items: list[dict[str, Any]] | None) -> str:
    """Nối tên các phần tử thành một chuỗi, giống file mẫu (ngăn bằng ``, ``)."""
    if not items:
        return ""
    names = [_text(item.get("name")) for item in items]
    return ", ".join(n for n in names if n)


def _or_no_information(value: Any) -> str:
    """Chuẩn hóa giá trị API, đổi chữ "Không" thành "Không có thông tin".

    API trả `description: "Không"` hoặc `requirementsAndConditions: "Không"` cho thủ tục
    không có nội dung; file mẫu ghi rõ "Không có thông tin" nên đồng bộ theo.
    """
    text = _text(value)
    if not text or text.lower() == "không":
        return "" if not text else NO_INFORMATION
    return text


def _related_procedures(value: Any) -> str:
    """Chuẩn hóa thủ tục liên quan.

    API trả mảng object hoặc mảng rỗng. Nếu chỉ dùng ``str()`` lên mảng rỗng sẽ ra
    chuỗi ``"[]"`` vô nghĩa. Không có dữ liệu thì ghi "Không có thông tin", giống
    file mẫu.
    """
    if isinstance(value, list):
        names = [
            _text(item.get("name"))
            for item in value
            if isinstance(item, dict) and _text(item.get("name"))
        ]
        return ", ".join(names) if names else NO_INFORMATION

    return _text(value) or NO_INFORMATION


def _administrative_level(detail: dict[str, Any]) -> str:
    """Cấp thực hiện, nối bằng ``, `` giống file mẫu ("Cấp tỉnh, Cấp xã")."""
    flag_pairs = [
        ("Cấp bộ", detail.get("isMinistry")),
        ("Cấp tỉnh", detail.get("isProvince")),
        ("Cấp xã", detail.get("isWard")),
        ("Cơ quan khác", detail.get("isOtherAgency")),
    ]
    return ", ".join(label for label, flag in flag_pairs if flag)


def _epoch_ms_to_iso(value: Any) -> str:
    """Đổi mốc thời gian epoch mili-giây của API sang ISO 8601 UTC.

    API trả số nguyên (ví dụ ``1777300588381``); lưu ISO để đọc được và so sánh được
    bằng SQL/Elasticsearch mà không phải tự đổi đơn vị ở mọi truy vấn.
    """
    if not isinstance(value, (int, float)) or value <= 0:
        return ""
    try:
        return datetime.fromtimestamp(value / 1000, tz=UTC).isoformat()
    except (OverflowError, OSError, ValueError):
        logger.warning("Mốc thời gian không hợp lệ: %r", value)
        return ""

        # ───────────────────────── PHÍ ─────────────────────────


def _classify_fee_item(item: dict[str, Any]) -> tuple[str, int | None, str]:
    """Phân loại một mục phí. Trả về ``(loại, số tiền, số hiệu văn bản)``."""
    raw_value = item.get("gia_tri")
    description = _text(item.get("description"))

    if isinstance(raw_value, (int, float)) and raw_value > 0:
        return "SO_TIEN", int(raw_value), ""

        # Mục phí TỒN TẠI nhưng không kèm mô tả ⇒ cổng có đăng ký phí và giá trị bằng 0,
        # nghĩa là không thu gì. Đây là cách duy nhất phân biệt "miễn phí" với "không có
        # thông tin" — xem docstring ``build_fee``.
    if not description:
        return "MIEN_PHI", None, ""

    if FREE_OF_CHARGE_PATTERN.search(description):
        return "MIEN_PHI", None, ""

    document_codes = DOCUMENT_CODE_PATTERN.findall(description)
    if document_codes:
        return "THEO_VAN_BAN", None, document_codes[0].strip()

    return "THEO_QUY_DINH_CHUNG", None, ""


def _description_key(description: str) -> str:
    """Khóa so khớp mô tả — bỏ khác biệt vô nghĩa về khoảng trắng, dấu câu, hoa/thường.

    Cổng ghi **cùng một điều kiện** với cách chấm câu và viết hoa khác nhau ở các hình thức
    nộp. Thủ tục ``2.000115`` có cả ba kiểu:

    ```text
    ONLINE      "…Đơn đề nghị hợp lệ."          ← có dấu chấm cuối
    DIRECT      "…Đơn đề nghị hợp lệ"           ← không có
    FEE         "Theo quy định của Bộ tài chính"      ← "tài" thường
    SERVICE_FEE "Theo quy định của Bộ Tài chính"      ← "Tài" hoa
    ```

    Dùng nguyên văn làm khóa thì **không khớp** → sinh mục trùng: số mục thời hạn của
    ``2.000115`` phình từ 6 lên 9. Khóa đã chuẩn hóa thì gộp đúng, còn **giá trị lưu vẫn là
    nguyên văn** của lần gặp đầu tiên.

    Dấu câu được **thay bằng khoảng trắng** rồi gộp khoảng trắng, chứ không xoá thẳng — nhờ
    vậy ``"17/2020/NĐ-CP"`` vẫn tách khỏi ``"17/2020NĐCP"`` thay vì lặng lẽ bằng nhau.

    Chỉ lấy **dòng đầu** vì cổng có lúc cắt cụt mô tả (chỉ còn dòng nêu trường hợp, mất dòng
    nêu thời hạn). Thủ tục ``2.000115`` có đúng ca đó: bản ``ONLINE`` giữ 2 dòng, bản
    ``DIRECT``/``POSTAL`` chỉ còn dòng đầu. Dòng đầu vẫn phân biệt được các trường hợp khác
    nhau (``"…thay đổi tên cơ sở"`` vs ``"…thay đổi chủ cơ sở"``).
    """
    first_line = (description.split("\n") or [""])[0]
    unaccented = re.sub(r"[.,;:]+", " ", first_line)
    return " ".join(unaccented.split()).lower()


def _fee_detail_items(fee_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gom các mục phí thành **cặp (số tiền, điều kiện)** đã khử trùng.

    ## Vì sao cần hàm này

    API trả về mỗi mục phí là một cặp: ``value`` (số tiền) và ``description`` (điều kiện áp
    dụng). Ví dụ thật ở thủ tục ``1.004376`` (cấp giấy phép bưu chính) — **8 cặp**:

    ```text
    34.500.000  "Quốc tế chiều đi trường hợp cấp phép lần đầu"
    21.500.000  "Phạm vi liên tỉnh trường hợp cấp lần đầu"
    ...
     8.500.000  "Phạm vi liên tỉnh Trường hợp chuyển nhượng toàn bộ doanh nghiệp..."
    ```

    Nếu chỉ lưu ``so_tien`` (một số) và ``mo_ta_goc`` (một đoạn văn) thì **mất liên kết**:
    không biết số tiền nào ứng với điều kiện nào. Đo trên 1.955 bản ghi: **442 bản ghi có
    mô tả phí nhưng mô tả KHÔNG chứa số tiền nào** — với những bản ghi đó, câu hỏi *"trường
    hợp của tôi đóng bao nhiêu?"* không trả lời được.

    ## Khử trùng theo CẶP, không theo số tiền

    Mỗi cách thức thực hiện (trực tiếp / trực tuyến / bưu chính) lặp lại **cùng bộ phí**, nên
    phải khử trùng. Nhưng khử theo ``value`` là sai: ở ``1.004376`` có hai mục **cùng
    21.500.000** ứng với **hai điều kiện khác nhau** (cấp lần đầu vs chuyển nhượng doanh
    nghiệp). Khóa khử trùng là **``(value, description)``**.

    ## Giữ mục ``value = 0`` khi CÓ mô tả

    Bản đầu tôi bỏ mọi mục ``value = 0``, nhưng như vậy **mất luôn mô tả điều kiện**. Thủ tục
    ``2.000115`` có 18 mục phí đều ``value = 0`` kèm mô tả *"Theo quy định của Bộ tài chính"* —
    bỏ hết thì ``muc_chi_tiet`` rỗng và chunk `FEE` không còn gì để nói.

    Quy tắc đúng:

    * ``value = 0`` **có** mô tả → giữ, ``so_tien = null``. Đây là trường hợp *"theo quy định
      của Bộ Tài chính"* — cổng không nêu số tiền nhưng **có** nói nguồn.
    * ``value = 0`` **không** mô tả → bỏ. Đây là nhãn ``MIEN_PHI`` thuần (``1.013314``), mô tả
      trống nên không có gì để hiển thị; ``phi.loai`` đã nói đủ.
    * ``value > 0`` → giữ, ``so_tien`` là số.
    """
    result: list[dict[str, Any]] = []
    seen: set[tuple[Any, str]] = set()
    for item in fee_items:
        value = item.get("gia_tri")
        if not isinstance(value, (int, float)) or value < 0:
            continue
        description = _text(item.get("description"))
        # value = 0 mà không có mô tả ⇒ chỉ là nhãn MIEN_PHI, không có nội dung.
        if value == 0 and not description:
            continue
        key = (value, _description_key(description))
        if key in seen:
            continue
        seen.add(key)
        amount = int(value)
        result.append(
            {
                "so_tien": (amount if amount == value else float(value)) if value > 0 else None,
                "dieu_kien": description,
            }
        )
    return result


def build_fee(methods: list[dict[str, Any]]) -> dict[str, Any]:
    """Tổng hợp phí từ tất cả cách thức thực hiện thành object có cấu trúc.

    Luôn trả về đủ 5 khóa để tầng sau không phải kiểm tra trường thiếu.

    **Phân biệt "miễn phí" với "không có thông tin" — đã kiểm chứng trên cổng:**

    * ``fees: []`` ở mọi cách thức → **CHUA_XAC_DINH**. Cổng không đăng ký mục phí nào nên
      không có cơ sở kết luận gì. Kiểm chứng: thủ tục ``3.000242`` — cổng ghi
      "không có thông tin".
    * ``fees: [{"value": 0}]`` → **MIEN_PHI**. Cổng **có** đăng ký phí và giá trị bằng 0,
      nghĩa là không thu gì. Kiểm chứng: thủ tục ``1.013314`` — cổng ghi "miễn phí".

    Hai thủ tục trên khác nhau về **số phần tử của ``fees``**, dù cả hai đều không có số
    tiền. Đó chính là trường phân biệt, không phải giá trị ``value``.

    ``muc_chi_tiet`` giữ **cặp (số tiền, điều kiện)** — xem ``_fee_detail_items``.
    """
    fee_items: list[dict[str, Any]] = []
    for method in methods:
        fee_items.extend(method.get("fees") or [])

        # Không có mục phí nào ⇒ cổng không đăng ký phí ⇒ chưa xác định được.
    if not fee_items:
        return {
            "loai": "CHUA_XAC_DINH",
            "so_tien": None,
            "van_ban": [],
            "mo_ta_goc": "",
            "muc_chi_tiet": [],
        }

    kinds: list[str] = []
    amount: int | None = None
    document_code = ""
    descriptions: list[str] = []

    for item in fee_items:
        kind, value, code = _classify_fee_item(item)
        if kind not in kinds:
            kinds.append(kind)
        if amount is None and value is not None:
            amount = value
        if not document_code and code:
            document_code = code
        description = _text(item.get("description"))
        if description and description not in descriptions:
            descriptions.append(description)

    raw_description = " ".join(descriptions)
    detail_items = _fee_detail_items(fee_items)

    # Ưu tiên theo độ cụ thể: có số tiền > miễn phí > viện dẫn có số hiệu > chung chung.
    for preferred in ("SO_TIEN", "MIEN_PHI", "THEO_VAN_BAN", "THEO_QUY_DINH_CHUNG"):
        if preferred not in kinds:
            continue

        documents: list[dict[str, str]] = []
        if preferred == "THEO_VAN_BAN" and document_code:
            documents = [{"so_hieu": document_code}]

        return {
            "loai": preferred,
            "so_tien": amount if preferred == "SO_TIEN" else None,
            "van_ban": documents,
            "mo_ta_goc": raw_description,
            "muc_chi_tiet": detail_items,
        }

    return {
        "loai": "CHUA_XAC_DINH",
        "so_tien": None,
        "van_ban": [],
        "mo_ta_goc": raw_description,
        "muc_chi_tiet": detail_items,
    }

    # ───────────────────────── THỜI HẠN ─────────────────────────


def extract_time_spans(description: str) -> list[dict[str, Any]]:
    """Trích các mốc thời gian từ chuỗi mô tả."""
    result: list[dict[str, Any]] = []
    seen: set[tuple[float, str]] = set()

    for match in TIME_SPAN_PATTERN.finditer(description):
        number = float(match.group(1).replace(",", "."))
        unit = TIME_UNIT_CODES.get(match.group(2).lower())
        if unit is None or (number, unit) in seen:
            continue
        seen.add((number, unit))
        result.append({"gia_tri": int(number) if number.is_integer() else number, "don_vi": unit})

    return result


def _processing_time_detail_items(methods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gom các mốc thời hạn thành **cặp (thời hạn, điều kiện)** đã khử trùng.

    ## Vì sao cần

    Cùng lý do với ``_fee_detail_items``: API trả mỗi mốc thời hạn kèm ``submissionMethod``
    (hình thức nộp) và ``description`` (điều kiện áp dụng). Đưa hết vào một mảng phẳng thì
    **mất liên kết** — không biết khoảng thời gian nào ứng với tình huống nào.

    Thủ tục ``2.000115`` có **6 mốc `3 Ngày làm việc`** nhưng **6 điều kiện khác nhau**:

    ```text
    ONLINE 3 WORKING_DAY  "a) Trường hợp cấp lại do Giấy chứng nhận bị mất hoặc bị hỏng"
    ONLINE 3 WORKING_DAY  "Trường hợp cơ sở thay đổi tên cơ sở nhưng không đổi chủ cơ sở…"
    ONLINE 3 WORKING_DAY  "Trường hợp cơ sở thay đổi chủ cơ sở nhưng không đổi tên cơ sở…"
    ONLINE 3 WORKING_DAY  "Trường hợp chuỗi cơ sở kinh doanh thực phẩm có giảm…"
    ```

    ## Vì sao KHÔNG có trường ``mo_ta``

    Bản đầu tôi lưu ``mo_ta = "3 Ngày làm việc"`` — **chuỗi tự sinh, không phải điều kiện**.
    Kết quả: 6 mục **nhìn giống hệt nhau**, mất hết thông tin phân biệt. Vì vậy chỉ giữ
    ``dieu_kien`` nguyên văn; ai cần nhãn hiển thị thì ghép ``gia_tri`` + ``don_vi``.

    ## Khử trùng theo ``(gia_tri, don_vi, dieu_kien)``

    Gồm cả điều kiện, nên hai tình huống **khác điều kiện** vẫn giữ riêng, còn cổng ghi lặp
    cùng một tình huống (ở nhiều hình thức nộp, hoặc lặp y hệt) thì **gộp một mục** và liệt
    kê các hình thức nộp.
    """
    result: list[dict[str, Any]] = []
    seen: dict[tuple[Any, str, str], dict[str, Any]] = {}

    for method in methods:
        label = _submission_label(method)
        value = method.get("processingTime")
        unit = _text(method.get("processingTimeUnit")) or "OTHER"
        condition = _text(method.get("description"))

        # Ưu tiên trường số khi đơn vị dùng được; nếu không thì trích từ mô tả.
        pairs: list[tuple[Any, str]] = []
        if unit in USABLE_UNITS and isinstance(value, (int, float)) and value > 0:
            pairs.append((value, unit))
        else:
            for span in extract_time_spans(condition):
                pairs.append((span["gia_tri"], span["don_vi"]))

        for item_value, item_unit in pairs:
            key = (item_value, item_unit, _description_key(condition))
            if key in seen:
                existing = seen[key]
                if label and label not in existing["hinh_thuc"]:
                    existing["hinh_thuc"].append(label)
                continue
            entry = {
                "gia_tri": item_value,
                "don_vi": item_unit,
                "dieu_kien": condition,
                "hinh_thuc": [label] if label else [],
            }
            seen[key] = entry
            result.append(entry)

    return result


def build_processing_time(methods: list[dict[str, Any]]) -> dict[str, Any]:
    """Tổng hợp thời hạn giải quyết thành object có cấu trúc.

    Ưu tiên trường số khi đơn vị dùng được. Nếu không, trích từ mô tả — trường hợp
    thật của thủ tục ``1.116634``: ``processingTime = 0``, ``unit = OTHER``, mô tả ghi
    "90 ngày" và "21 ngày làm việc".

    Trả về 4 khóa:

    * ``loai`` — ``SO`` / ``TRONG_TEXT`` / ``CHUA_XAC_DINH``.
    * ``moc`` — mảng phẳng ``{gia_tri, don_vi}``, giữ để tương thích ngược và để lọc.
    * ``nhieu_don_vi`` — có nhiều hơn một đơn vị khác nhau. Khi ``true`` thì **không được
      trả lời bằng một con số duy nhất**.
    * ``muc_chi_tiet`` — **cặp (thời hạn, điều kiện)**. Xem ``_processing_time_detail_items``.
      Đây mới là trường dùng để render chunk ``PROCESSING_TIME``.

    **Không có ``tom_tat``.** Trường đó lấy giá trị lớn nhất theo từng đơn vị, tạo ra câu
    *"20 ngày, 1 giờ, 5 ngày làm việc"* — đọc lên như thể cộng dồn, trong khi thực tế là
    các tình huống loại trừ nhau. Không code nào đọc nó, nên đã bỏ hẳn.
    """
    milestones: list[dict[str, Any]] = []
    seen: set[tuple[Any, str]] = set()
    used_description = False
    has_numeric_field = False

    for method in methods:
        value = method.get("processingTime")
        unit = _text(method.get("processingTimeUnit")) or "OTHER"

        if unit in USABLE_UNITS and isinstance(value, (int, float)) and value > 0:
            if (value, unit) not in seen:
                seen.add((value, unit))
                milestones.append({"gia_tri": value, "don_vi": unit})
                has_numeric_field = True
            continue

        for span in extract_time_spans(_text(method.get("description"))):
            key = (span["gia_tri"], span["don_vi"])
            if key in seen:
                continue
            seen.add(key)
            milestones.append(span)
            used_description = True

    if not milestones:
        kind = "CHUA_XAC_DINH"
    elif used_description and not has_numeric_field:
        kind = "TRONG_TEXT"
    else:
        kind = "SO"

    detail_items = _processing_time_detail_items(methods)
    distinct_units = {m["don_vi"] for m in milestones}

    return {
        "loai": kind,
        "moc": milestones,
        "nhieu_don_vi": len(distinct_units) > 1,
        "muc_chi_tiet": detail_items,
    }


def build_submission_methods(methods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Khử trùng lặp các cách thức thực hiện.

    Cùng một nội dung có thể bị lặp ở DIRECT / ONLINE / POSTAL. Không khử sẽ khiến
    Elasticsearch và Qdrant index trùng, làm một thông tin chiếm nhiều vị trí top-K.
    """
    merged: list[dict[str, Any]] = []

    for method in methods:
        label = _submission_label(method)
        value = method.get("processingTime")
        unit = _text(method.get("processingTimeUnit"))
        duration_text = (
            f"{value} {_time_unit_label(unit)}"
            if isinstance(value, (int, float)) and value > 0
            else ""
        )
        description = _text(method.get("description"))

        key = (duration_text, description)
        existing = next((m for m in merged if m["_khoa"] == key), None)
        if existing is None:
            merged.append(
                {
                    "_khoa": key,
                    "hinh_thuc": [label],
                    "thoi_gian": duration_text,
                    "mo_ta": description,
                }
            )
        elif label not in existing["hinh_thuc"]:
            existing["hinh_thuc"].append(label)

    for item in merged:
        item.pop("_khoa", None)

    return merged

    # ───────────────────────── BẢNG TEXT ─────────────────────────


def _fee_description(fee_items: list[dict[str, Any]]) -> str:
    """Mô tả phí cho một dòng của bảng, giống file mẫu.

    File mẫu ghi ``Miễn phí\\n(mô tả thêm)`` khi cổng báo miễn phí.

    Quy tắc khớp với ``build_fee`` để cột phí trong bảng không mâu thuẫn với ``phi.loai``:

    * Không có mục phí nào ⇒ ``""`` (cổng không đăng ký phí — thủ tục ``3.000242``).
    * Có mục phí, ``value = 0``, mô tả rỗng ⇒ ``"Miễn phí"`` (thủ tục ``1.013314``).
    * Có mục phí kèm mô tả ⇒ dùng mô tả đó (có thể là số tiền hoặc viện dẫn văn bản).
    """
    if not fee_items:
        return ""

    for item in fee_items:
        description = _text(item.get("description"))
        value = item.get("gia_tri")

        if isinstance(value, (int, float)) and value > 0:
            return f"{int(value):,} đồng".replace(",", ".")

        if not description:
            # Có mục phí nhưng không có số tiền lẫn mô tả ⇒ cổng đăng ký giá trị 0.
            return "Miễn phí"

        if FREE_OF_CHARGE_PATTERN.search(description):
            return f"Miễn phí\n({description})"

        return description

    return ""


def _duration_of(method: dict[str, Any]) -> str:
    """Thời gian giải quyết của một cách thức, cho cột thứ 2 của bảng."""
    value = method.get("processingTime")
    unit = _text(method.get("processingTimeUnit")) or "OTHER"

    if unit in USABLE_UNITS and isinstance(value, (int, float)) and value > 0:
        displayed = int(value) if float(value).is_integer() else value
        return f"{displayed} {TIME_UNIT_LABELS.get(unit, unit)}"

    match = TIME_SPAN_PATTERN.search(_text(method.get("description")))
    if match:
        return f"{match.group(1)} {match.group(2)}"

    return ""


def _submission_method_text(methods: list[dict[str, Any]]) -> str:
    """Dựng bảng cách thức thực hiện dạng text có tab, giống file mẫu."""
    if not methods:
        return ""

    lines = ["Hình thức nộp\tThời gian\tPhí, lệ phí\tMô tả"]
    for method in methods:
        submission = _submission_label(method)
        lines.append(
            "\t".join(
                [
                    submission,
                    _duration_of(method),
                    _fee_description(method.get("fees") or []),
                    _text(method.get("description")),
                ]
            )
        )
    return "\n".join(lines)


def _steps_text(steps: list[dict[str, Any]] | None) -> str:
    """Gộp các bước thành text. File mẫu để mô tả trần, không thêm tiêu đề."""
    if not steps:
        return ""
    return "\n\n".join(
        _text(step.get("description")) for step in steps if _text(step.get("description"))
    )


def _quantity_text(originals: Any, copies: Any) -> str:
    """Chuỗi số lượng, giống file mẫu: ``"1 bản chính"`` hoặc nhiều dòng nếu có cả hai."""
    original_count = int(originals or 0)
    copy_count = int(copies or 0)

    parts = []
    if original_count:
        parts.append(f"{original_count} bản chính")
    if copy_count:
        parts.append(f"{copy_count} bản sao")

    if not parts:
        return "0 bản chính"
    return ",\n".join(parts) if len(parts) > 1 else parts[0]


def _documents_text(detail: dict[str, Any]) -> str:
    """Dựng bảng thành phần hồ sơ dạng text có tab, giống file mẫu."""
    lines: list[str] = []

    for execution_case in detail.get("executionCases") or []:
        components = execution_case.get("profileComponents") or []
        if not components:
            continue

        case_name = _text(execution_case.get("name"))
        if case_name:
            lines.append(case_name)

        lines.append("Tên giấy tờ\tMẫu đơn, tờ khai\tSố lượng")
        for item in components:
            form_files = "; ".join(
                _text(attachment.get("fileName"))
                for attachment in (item.get("attachments") or [])
                if _text(attachment.get("fileName"))
            )
            lines.append(
                "\t".join(
                    [
                        _text(item.get("name")),
                        form_files,
                        _quantity_text(item.get("originalQty"), item.get("copyQty")),
                    ]
                )
            )
        lines.append("")

    return "\n".join(lines).strip()


def _legal_basis_text(documents: list[dict[str, Any]] | None) -> str:
    """Dựng bảng căn cứ pháp lý dạng text có tab, giống file mẫu."""
    if not documents:
        return ""

    lines = ["Tên văn bản pháp lý\tMã văn bản"]
    for document in documents:
        lines.append(f"{_text(document.get('name'))}\t{_text(document.get('code'))}")
    return "\n".join(lines)


def _results_text(results: list[dict[str, Any]] | None) -> str:
    """Nối tên kết quả xử lý thành một chuỗi."""
    return "; ".join(_text(item.get("name")) for item in (results or []) if _text(item.get("name")))

    # ───────────────────────── HÀM CHÍNH ─────────────────────────


def compute_content_hash(record: dict[str, Any]) -> str:
    """Băm nội dung nghiệp vụ để phát hiện thủ tục thay đổi.

    Bỏ các trường phiên bản (``ngay_crawl``, ``ngay_cap_nhat``, ``content_hash``) —
    nếu băm cả chúng thì hash đổi mỗi lần crawl và incremental load vô nghĩa.
    """
    content = {k: v for k, v in record.items() if k not in VERSION_FIELDS}
    payload = json.dumps(content, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def transform(
    entry: CatalogEntry,
    detail: dict[str, Any],
    *,
    crawled_at: str,
) -> dict[str, Any]:
    """Chuyển một response API chi tiết thành JSON chuẩn hóa 29 trường.

    Args:
        entry: dòng danh mục Excel, cấp các trường lấy từ danh mục.
        detail: response API chi tiết.
        crawled_at: thời điểm crawl dạng ISO 8601.
    """
    formality_id = _text(detail.get("id"))
    methods = detail.get("executionMethods") or []

    # Dựng phần nội dung trước để băm, rồi mới ghép các trường phiên bản vào.
    record: dict[str, Any] = {
        # ── Định danh ──
        "ma_thu_tuc": _text(detail.get("codeNotation")) or entry.procedure_code,
        "detail_url": DETAIL_URL_TEMPLATE.format(formality_id=formality_id),
        "formality_id": formality_id,
        "ten_thu_tuc": _text(detail.get("name")) or entry.procedure_name,
        # ── Phân loại ──
        "so_quyet_dinh": _text((detail.get("procedureProposal") or {}).get("proposalNumber")),
        "cap_thuc_hien": _administrative_level(detail),
        "loai_thu_tuc": entry.procedure_type,
        "linh_vuc": entry.source_field,
        "doi_tuong_thuc_hien": _join_names(detail.get("subjectTypesDetails")),
        "co_quan_co_tham_quyen": _join_names(detail.get("departmentsAuthority")),
        "dia_chi_tiep_nhan": _text(detail.get("dossierReceivingAddresses")),
        "co_quan_duoc_uy_quyen": _text(detail.get("authorizedAgencies")),
        "co_quan_phoi_hop": _join_names(detail.get("departmentsCoordinating")),
        "thu_tuc_lien_quan": _related_procedures(detail.get("procedureRelatedGroup")),
        # ── Nội dung ──
        "trinh_tu_thuc_hien": _steps_text(detail.get("executionSteps")),
        "cach_thuc_thuc_hien": _submission_method_text(methods),
        "thanh_phan_ho_so": _documents_text(detail),
        "can_cu_phap_ly": _legal_basis_text(detail.get("legalBasisesDetails")),
        "co_quan_thuc_hien": _join_names(detail.get("departmentsExecuting")),
        "yeu_cau_dieu_kien": _or_no_information(detail.get("requirementsAndConditions")),
        "ket_qua_xu_ly": _results_text(detail.get("resultsDetails")),
        # ── Bổ sung Mức 1 ──
        "co_quan_ban_hanh": _text(detail.get("departmentPromulgateName")),
        "ngay_cap_nhat": _epoch_ms_to_iso(detail.get("updatedAt")),
        # ── Bổ sung Mức 2 ──
        "phi": build_fee(methods),
        "thoi_han": build_processing_time(methods),
        # ── Đã có ──
        "trang_thai": _text(detail.get("state")),
        "domain_group": entry.domain_group,
    }

    record["content_hash"] = compute_content_hash(record)
    record["ngay_crawl"] = crawled_at
    return record
