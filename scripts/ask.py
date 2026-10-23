"""Hỏi thử hệ thống từ dòng lệnh — chạy **trọn luồng** như người dùng thật.

## Cách dùng

```bash
# một câu
uv run python scripts/ask.py "Thủ tục 1.115374 do cơ quan nào ban hành?"

# nhiều câu liên tiếp (mỗi câu một lượt độc lập)
uv run python scripts/ask.py "câu 1" "câu 2"

# chế độ hỏi liên tục: gõ câu, Enter; gõ 'q' để thoát
uv run python scripts/ask.py
```

## Đọc kết quả

Mốc 1 **chưa sinh câu trả lời**. Kết quả là **bằng chứng** hệ thống tìm được, cùng lý do nó
chọn nhánh đó. Cụ thể cần xem:

* ``Nhánh`` — luồng tự chọn nhánh nào (không phải người dùng chọn);
* ``lý do`` — vì sao chọn nhánh đó (đọc được, ghi trong bảng quyết định);
* ``Kết cục`` — tìm được bằng chứng / cần hỏi lại / không trả lời được / lỗi;
* ``Bằng chứng`` — mục đầu tiên thường đã đủ để biết định tuyến có đúng không.

Dòng ``workflow q=...`` in ra ở cuối là **dòng vết** — cùng định dạng mà máy chủ ghi, nên có
thể chép thẳng vào báo cáo.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

#: Chạy trực tiếp ``python scripts/ask.py`` thì thư mục gốc dự án chưa có trong ``sys.path``
#: (Python chỉ thêm thư mục chứa tệp, tức ``scripts/``). Thêm để ``import backend`` chạy được.
GOC_DU_AN = Path(__file__).resolve().parent.parent
if str(GOC_DU_AN) not in sys.path:
    sys.path.insert(0, str(GOC_DU_AN))

from backend.app.rag import embeddings  # noqa: E402
from backend.app.workflow import question_parser  # noqa: E402
from backend.app.workflow.run import ask, tom_tat  # noqa: E402

#: Console Windows mặc định không in được tiếng Việt (``UnicodeEncodeError`` với chữ có dấu).
#: Ép UTF-8 để chạy được trên PowerShell/cmd mà không phải đổi cài đặt hệ thống.
for _luong in (sys.stdout, sys.stderr):
    try:
        _luong.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, OSError):
        pass

#: Một số câu mẫu phủ bốn nhánh, để chạy thử nhanh mà không phải nghĩ câu hỏi.
CAU_MAU = [
    "Thủ tục 1.115374 do cơ quan nào ban hành?",
    "Thủ tục 1.004873 cần hồ sơ gì?",
    "Thủ tục 1.001699 là gì?",
    "Lĩnh vực nào nhiều thủ tục nhất?",
    "lệ phí cấp giấy xác nhận khuyết tật là bao nhiêu?",
    "đổi sổ đỏ bị rách cũ thì cơ quan nào ban hành",
    "thời tiết Gia Lai hôm nay thế nào",
]


async def hoi(cau: str) -> None:
    ket_qua = await ask(cau)
    print()
    print("=" * 78)
    print(tom_tat(ket_qua))
    print("=" * 78)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    for ten in ("httpx", "httpcore", "neo4j", "elastic_transport"):
        logging.getLogger(ten).setLevel(logging.WARNING)

    tham_so = sys.argv[1:]

    if tham_so == ["--mau"]:
        for cau in CAU_MAU:
            await hoi(cau)
        await question_parser.close_client()
        await embeddings.close()
        return

    if tham_so:
        for cau in tham_so:
            await hoi(cau)
        await question_parser.close_client()
        await embeddings.close()
        return

    print("Gõ câu hỏi rồi Enter. Gõ 'q' để thoát.")
    while True:
        try:
            cau = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not cau or cau.lower() in {"q", "quit", "exit"}:
            break
        await hoi(cau)

    await question_parser.close_client()
    await embeddings.close()


if __name__ == "__main__":
    asyncio.run(main())
