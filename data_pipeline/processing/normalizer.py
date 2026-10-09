"""Chuẩn hóa bản ghi trước khi chunk.

Phạm vi: **chỉ đụng vào khoảng trắng và dạng Unicode**, không đổi nội dung, không suy diễn,
không điền thêm. Mọi thay đổi ở đây phải tất định và kiểm chứng được.

## Vì sao cần

Khảo sát 1.955 bản ghi thật cho thấy:

* **Unicode:** toàn bộ 43.438 giá trị đã ở dạng **NFC** — **không cần** chuẩn hóa. Hàm
  ``normalize_unicode`` vẫn giữ lại vì nó rẻ và phòng khi nguồn đổi.
* **Khoảng trắng:** đây mới là vấn đề thật — 1.013 giá trị có space thừa ở đầu/cuối,
  1.168 giá trị có hai space liền nhau, 3 giá trị có ba dòng trống liên tiếp.

## Vì sao KHÔNG được gộp khoảng trắng một cách thô bạo

6.047 giá trị chứa **ký tự tab**, và tab là **dấu phân cách cột** của các trường dạng bảng:
``cach_thuc_thuc_hien``, ``thanh_phan_ho_so``, ``can_cu_phap_ly``. Nếu gộp ``\\s+`` thành một
space thì tab bị phá và bảng mất cấu trúc — hỏng dữ liệu nặng hơn lỗi đang sửa.

Vì vậy quy tắc là: chỉ gộp khi có **từ hai ký tự trắng trở lên**, và gộp về **ký tự đầu tiên
của nhóm** — nhờ đó tab đơn lẻ giữ nguyên, còn hai space → một space, ``" \\t "`` → ``"\\t"``.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# Chuẩn hóa khoảng trắng NGANG, làm theo 3 bước tách biệt vì mỗi bước có ràng buộc riêng.
#
# RÀNG BUỘC QUAN TRỌNG: **tab là dấu phân cách cột**, và **hai tab liền nhau là một Ô RỖNG**
# trong bảng. Gộp `\t\t` thành `\t` sẽ DỊCH CỘT và làm sai dữ liệu — đã gặp thật ở thủ tục
# `1.013314` (cột "Mẫu đơn" rỗng). Vì vậy TUYỆT ĐỐI không đụng vào cụm tab.
_MULTI_SPACE = re.compile(r" {2,}")  # nhiều space → một space
_SPACE_BEFORE_TAB = re.compile(r" *\t")  # space thừa ngay trước tab → bỏ
_SPACE_AFTER_TAB = re.compile(r"\t *")  # space thừa ngay sau tab → bỏ
# Ba dòng trống trở lên → còn hai (một dòng trống phân cách).
_MULTI_BLANK_LINES = re.compile(r"\n{3,}")

#: Trường dạng bảng có tab phân cách cột — bắt buộc giữ tab.
#: Giá trị là **tên trường dữ liệu** nên giữ tiếng Việt: đây là khóa trong JSON của cổng.
TABULAR_FIELDS = frozenset({"cach_thuc_thuc_hien", "thanh_phan_ho_so", "can_cu_phap_ly"})

# ---------------------------------------------------------------------------
# GIÁ TRỊ SENTINEL — chỗ cổng ghi "không có gì" thay vì để trống
#
# Cổng DVC dùng các cụm từ này để đánh dấu mục chưa ghi nhận. Chúng KHÔNG phải nội dung
# nghiệp vụ. Khảo sát 1.909 bản ghi thật (bản đã chuẩn hóa):
#
#     thu_tuc_lien_quan   1.906 bản ghi   (chỉ 3 bản ghi có dữ liệu thật)
#     yeu_cau_dieu_kien     186 bản ghi
#     dia_chi_tiep_nhan       3 bản ghi
#     ket_qua_xu_ly           2 bản ghi
#
# Phân biệt hai câu KHÁC NHAU về nghĩa:
#
#     "Không có thông tin"  = cổng CHƯA GHI NHẬN mục này
#     "Không có"            = khẳng định CHẮC CHẮN không có
#
# Vì vậy KHÔNG được để LLM đọc sentinel rồi trả lời "không có X" — đó là khẳng định vượt
# quá dữ liệu. Giai đoạn 5 render thành "cổng chưa ghi nhận thông tin" và Giai đoạn 14
# ràng buộc prompt theo cách diễn đạt đó. Xem §4.1c của guide.
#
# ## Vì sao so khớp trên DẠNG ĐÃ CHUẨN HÓA chứ không phải nguyên văn
#
# Cổng ghi cùng một ý với dấu câu, hoa/thường và khoảng trắng khác nhau. Khảo sát thật cho
# thấy **9 biến thể** của cùng nhóm "chưa ghi nhận":
#
#     'Không có thông tin' · 'Không quy định' · 'Không quy định.' · 'Không có'
#     'không có' · 'không quy định' · 'Không.' · 'không có.' · 'Không có.'
#
# Liệt kê tay từng biến thể là cách làm sai — chỉ cần cổng thêm một dấu chấm nữa là sót.
# Nên ``is_sentinel`` chuẩn hóa giá trị về dạng không dấu, không dấu câu, gộp khoảng trắng,
# rồi tra trong tập ngắn dưới đây. Giá trị GỐC vẫn **không bị đổi** khi lưu.
#
# ## Ba cụm KHÔNG được coi là sentinel dù bắt đầu bằng "không có"
#
#     'Không có yêu cầu, điều kiện'      → khẳng định thủ tục KHÔNG đòi điều kiện
#     'Không có kết quả'                 → khẳng định thủ tục không trả kết quả
#     'Không có văn bản trả lời'         → khẳng định không có văn bản
#
# Ba câu này **có nghĩa nghiệp vụ**, khác hẳn "chưa ghi nhận". Nếu gộp chúng vào sentinel
# thì chunk sẽ nói "cổng chưa ghi nhận" trong khi cổng đã KHẲNG ĐỊNH — sai hướng.
# Vì vậy dùng tập ĐÓNG (khớp chính xác trên dạng chuẩn hóa), không dùng tiền tố.
# ---------------------------------------------------------------------------
EMPTY_SENTINELS = frozenset(
    {
        # "chưa ghi nhận" — nhóm phổ biến nhất
        "khong co thong tin",
        # "không quy định"
        "khong quy dinh",
        # "không có" / "không"
        "khong co",
        "khong",
    }
)

#: Ký tự bị coi là dấu câu vô nghĩa khi so khớp sentinel. Chỉ ảnh hưởng tới VIỆC SO KHỚP,
#: không ảnh hưởng tới giá trị lưu.
_IGNORED_CHARS = re.compile(r"[^a-z0-9]+")


def _sentinel_key(value: str) -> str:
    """Đưa giá trị về khoá so khớp sentinel: không dấu, không dấu câu, không hoa/thường."""
    text = unicodedata.normalize("NFD", value.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d")
    return " ".join(_IGNORED_CHARS.sub(" ", text).split())


def is_sentinel(value: Any) -> bool:
    """True nếu giá trị là chỗ cổng đánh dấu "chưa ghi nhận", không phải nội dung thật.

    So khớp trên **dạng đã chuẩn hóa** nên ``"Không quy định"``, ``"Không quy định."`` và
    ``"không quy định"`` đều nhận ra như nhau. Giá trị gốc **không bị đổi**.
    """
    if value is None:
        return False
    if isinstance(value, str):
        return _sentinel_key(value) in EMPTY_SENTINELS
    if isinstance(value, list):
        # Mảng toàn sentinel cũng là "chưa ghi nhận" (ví dụ co_quan_phoi_hop = ["Không"]).
        return bool(value) and all(is_sentinel(item) for item in value)
    return False


#: Trường văn xuôi — không có tab phân cách, gộp khoảng trắng mạnh hơn được.
#: Giá trị là **tên trường dữ liệu** nên giữ tiếng Việt.
PROSE_FIELDS = frozenset(
    {
        "trinh_tu_thuc_hien",
        "yeu_cau_dieu_kien",
        "ket_qua_xu_ly",
        "thu_tuc_lien_quan",
        "co_quan_thuc_hien",
        "co_quan_co_tham_quyen",
        "co_quan_ban_hanh",
        "co_quan_phoi_hop",
        "co_quan_duoc_uy_quyen",
        "dia_chi_tiep_nhan",
    }
)


def normalize_unicode(value: str) -> str:
    """Đưa về dạng NFC.

    Tiếng Việt có hai cách mã hoá cùng một ký tự (``"ế"`` = 1 ký tự NFC, hoặc 3 ký tự NFD).
    Hai dạng **không bằng nhau** khi so sánh chuỗi, nên tìm kiếm sẽ trượt dù chữ nhìn giống hệt.
    """
    return unicodedata.normalize("NFC", value)


def normalize_whitespace(value: str) -> str:
    """Chuẩn hóa khoảng trắng nhưng **giữ nguyên cụm tab**.

    Ba bước, cố ý tách riêng:

    1. Bỏ space/tab/xuống dòng thừa ở đầu và cuối
    2. Nhiều space liền nhau → một space; space thừa quanh tab → bỏ
    3. Từ ba dòng trống liên tiếp trở lên → còn hai

    **Không đụng vào cụm tab** vì ``\\t\\t`` là một ô rỗng trong bảng — gộp lại sẽ dịch cột.
    """
    value = value.strip()
    value = _MULTI_SPACE.sub(" ", value)
    value = _SPACE_BEFORE_TAB.sub("\t", value)
    value = _SPACE_AFTER_TAB.sub("\t", value)
    value = _MULTI_BLANK_LINES.sub("\n\n", value)
    return value


def normalize_text(value: Any, *, field_name: str = "") -> str:
    """Chuẩn hóa một giá trị văn bản. Trả ``""`` cho giá trị rỗng."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    if not value:
        return ""
    value = normalize_unicode(value)
    value = normalize_whitespace(value)
    # Trường văn xuôi không có tab phân cách: gộp cả tab lẫn space về space.
    if field_name in PROSE_FIELDS:
        value = re.sub(r"[ \t]+", " ", value)
    return value


def _normalize_fee(fee: dict[str, Any]) -> dict[str, Any]:
    """Chuẩn hóa phần văn bản của ``phi``, đi cả vào ``muc_chi_tiet[].dieu_kien``.

    **Không** đụng ``so_tien`` (số) và ``loai`` (mã) — chúng không phải văn bản.
    """
    result: dict[str, Any] = {
        **fee,
        "mo_ta_goc": normalize_text(fee.get("mo_ta_goc"), field_name="phi.mo_ta_goc"),
        "van_ban": [normalize_text(x) for x in (fee.get("van_ban") or []) if str(x).strip()],
    }
    items = fee.get("muc_chi_tiet")
    if isinstance(items, list):
        result["muc_chi_tiet"] = [
            {**x, "dieu_kien": normalize_text(x.get("dieu_kien"))} if isinstance(x, dict) else x
            for x in items
        ]
    return result


def _normalize_processing_time(processing_time: dict[str, Any]) -> dict[str, Any]:
    """Chuẩn hóa ``thoi_han``, đi cả vào ``muc_chi_tiet[].dieu_kien`` và ``hinh_thuc[]``.

    **Không** đụng ``gia_tri`` (số), ``don_vi`` (mã), ``moc`` (số) và ``nhieu_don_vi`` (bool).
    """
    result: dict[str, Any] = {**processing_time, "moc": processing_time.get("moc") or []}
    items = processing_time.get("muc_chi_tiet")
    if isinstance(items, list):
        result["muc_chi_tiet"] = [
            {
                **x,
                "dieu_kien": normalize_text(x.get("dieu_kien")),
                "hinh_thuc": [
                    normalize_text(y) for y in (x.get("hinh_thuc") or []) if str(y).strip()
                ],
            }
            if isinstance(x, dict)
            else x
            for x in items
        ]
    return result


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Chuẩn hóa mọi giá trị văn bản trong một bản ghi 29 trường.

    Đi sâu vào hai object có cấu trúc ``phi`` và ``thoi_han`` — **kể cả** phần tử trong
    ``muc_chi_tiet`` — nhưng **không** đụng vào số và mã: ``so_tien``, ``gia_tri``, ``don_vi``,
    ``moc``, ``nhieu_don_vi``.

    Chuẩn hóa ``muc_chi_tiet`` là bắt buộc vì Giai đoạn 5 render chunk `FEE` và
    `PROCESSING_TIME` **trực tiếp từ đó**. Bỏ qua thì một chuỗi có hai space trong
    ``dieu_kien`` sẽ đi thẳng vào chunk.
    """
    result: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, str):
            result[key] = normalize_text(value, field_name=key)
        elif key == "phi" and isinstance(value, dict):
            result[key] = _normalize_fee(value)
        elif key == "thoi_han" and isinstance(value, dict):
            result[key] = _normalize_processing_time(value)
        else:
            result[key] = value
    return result


def fields_needing_normalization(record: dict[str, Any]) -> list[str]:
    """Liệt kê tên trường sẽ bị thay đổi nếu chạy chuẩn hóa. Rỗng nghĩa là đã sạch."""
    changed: list[str] = []
    for key, value in record.items():
        if isinstance(value, str):
            if normalize_text(value, field_name=key) != value:
                changed.append(key)
        elif key == "phi" and isinstance(value, dict):
            if _normalize_fee(value) != value:
                changed.append("phi")
        elif key == "thoi_han" and isinstance(value, dict):
            if _normalize_processing_time(value) != value:
                changed.append("thoi_han")
    return changed
