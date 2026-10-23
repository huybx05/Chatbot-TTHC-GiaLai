"""Chuẩn hoá chuỗi — **hợp đồng giữa lúc nạp đồ thị và lúc truy vấn**.

## Vì sao file này tồn tại

``VanBanPhapLy.key`` trong Neo4j **không phải** số hiệu nguyên văn. Bộ index đã chuẩn
hoá trước khi ghi:

```text
Người dùng gõ   : 102/2024/NĐ-CP
Lưu trong DB    : 102/2024/ND CP
```

Quy tắc: bỏ dấu tiếng Việt, ``đ``→``d``, mọi ký tự ngoài ``[a-z0-9/]`` thành khoảng
trắng, giữ ``/``, viết hoa, gộp khoảng trắng.

Nếu backend viết lại hàm này mà lệch **một ký tự** thì truy vấn T4 trả 0 dòng và
không có lỗi nào báo — đúng loại hỏng im lặng khó phát hiện nhất. Vì vậy hàm ở đây
được chép **nguyên văn** từ ``data_pipeline/indexing/neo4j.py`` và có test đối chiếu
(``backend/tests/test_text_norm.py``): hai bản lệch nhau là test đỏ ngay.
"""

from __future__ import annotations

import re
import unicodedata

#: Mã văn bản pháp lý: ``31/2024/QH15`` · ``49/2026/NĐ-CP`` · ``104/2026/QĐ-UBND`` ·
#: ``816/QĐ-UBND``. Chép từ bộ index để "cái gì được coi là số hiệu văn bản" chỉ có
#: **một** định nghĩa.
DOCUMENT_CODE_PATTERN = re.compile(
    r"\b\d{1,4}\s*/\s*\d{4}\s*/\s*"
    r"(?:NĐ[-\s]?CP|TT[-\s]?[A-ZĐ]+|QH\d{1,2}|QĐ[-\s]?[A-ZĐ]+|NQ[-\s]?[A-ZĐ]+|TTLT[-\s]?[A-ZĐ]+)\b"
    r"|\b\d{1,4}\s*/\s*QĐ[-\s]?[A-ZĐ]+\b",
    re.IGNORECASE,
)

#: Loại văn bản — dùng để nhận ra người dùng đang nói tới **tên** văn bản (không có số
#: hiệu), ví dụ *"Luật Đất đai là căn cứ của thủ tục nào?"*.
DOCUMENT_TYPE_WORDS = (
    "Luật",
    "Bộ luật",
    "Nghị định",
    "Thông tư liên tịch",
    "Thông tư",
    "Quyết định",
    "Nghị quyết",
    "Pháp lệnh",
    "Hiến pháp",
    "Công văn",
)

#: Cắt cụm tên văn bản tại những từ bắt đầu mệnh đề sau — nếu không cắt, cụm sẽ nuốt
#: cả câu hỏi ("Luật Đất đai **là căn cứ của thủ tục nào**").
_NAME_STOP_WORDS = (
    " là ",
    " có ",
    " quy định ",
    " quy ",
    " làm ",
    " số ",
    " gồm ",
    " áp dụng ",
    " căn cứ ",
    " hiện ",
    " thuộc ",
    " ?",
    " bao ",
)


def normalize_key(value: str) -> str:
    """Chuẩn hoá về đúng dạng khoá lưu trong Neo4j.

    ``"102/2024/NĐ-CP"`` → ``"102/2024/ND CP"``
    """
    value = unicodedata.normalize("NFD", str(value).lower())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    value = value.replace("đ", "d")
    value = re.sub(r"[^a-z0-9/]+", " ", value)
    return " ".join(value.split()).upper()


def strip_accents(value: str) -> str:
    """Bỏ dấu tiếng Việt, **giữ nguyên** chữ thường — dùng để so khớp từ khoá."""
    value = unicodedata.normalize("NFD", str(value).lower())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return value.replace("đ", "d")


def document_numbers(text: str) -> list[str]:
    """Trích các số hiệu văn bản trong câu, **đã chuẩn hoá**, giữ thứ tự, bỏ trùng."""
    ket_qua: list[str] = []
    for khop in DOCUMENT_CODE_PATTERN.findall(text):
        khoa = normalize_key(khop)
        if khoa and khoa not in ket_qua:
            ket_qua.append(khoa)
    return ket_qua


def document_name_phrases(text: str) -> list[str]:
    """Trích cụm **tên** văn bản (không kèm số hiệu), ví dụ ``"Đất đai"``.

    Chỉ dùng khi câu hỏi **không có** số hiệu. Ví dụ:

    ```text
    "Luật Đất đai là căn cứ của thủ tục nào?"  → ["Đất đai"]
    "Thông tư 08/2023/TT-BLĐTBXH quy định gì?" → []   (đã có số hiệu)
    ```

    Trả về cụm thô (giữ dấu) để so khớp ``CONTAINS`` với ``VanBanPhapLy.name``.
    """
    if document_numbers(text):
        return []

    mau = re.compile(
        r"\b(" + "|".join(re.escape(w) for w in DOCUMENT_TYPE_WORDS) + r")\b\s+(.{2,80})",
        re.IGNORECASE,
    )
    ket_qua: list[str] = []
    for khop in mau.finditer(text):
        duoi = khop.group(2)
        # Cắt tại từ bắt đầu mệnh đề sau.
        for dung in _NAME_STOP_WORDS:
            vi_tri = duoi.lower().find(dung)
            if vi_tri > 0:
                duoi = duoi[:vi_tri]
        duoi = duoi.strip(" ,.;:?!\"'")
        # Bỏ phần còn lại nếu là chữ số (trường hợp số hiệu viết tách).
        if duoi and not re.fullmatch(r"[\d/\s.-]+", duoi):
            if duoi not in ket_qua:
                ket_qua.append(duoi)
    return ket_qua
