"""Tầng điều phối truy xuất — **lối vào duy nhất** cho chatbot.

## Vai trò

``api/chat.py`` chỉ cần gọi :func:`retrieve`. Thứ tự tầng, việc tái dùng vector, và việc ghi
nguồn vào kết quả đều nằm **một chỗ**. **Không** để ``api/chat.py`` gọi thẳng tầng truy xuất
rồi gọi ``hybrid`` — khi đó logic thứ tự sẽ nằm rải rác, và đó là nguồn gốc của loại lỗi
"ba nơi dựng ba kiểu kết quả".

Trang admin ``/admin/rag-playground`` là **ngoại lệ có chủ ý**: nó gọi lẻ từng động cơ để
kiểm thử riêng từng tín hiệu. Nhưng nó cũng có nút "chạy qua luồng" gọi đúng lối vào này,
để so sánh "chạy lẻ" với "chạy đủ luồng".

## Thứ tự tầng

Toàn bộ thứ tự đã được cài trong đồ thị (``backend/app/workflow/graph.py``) và **không** còn
nằm ở tệp này:

```text
neo (mã · văn bản · thực thể)             0 token
  ↓ chưa neo
nhúng MỘT lần (định danh tên thủ tục)        ~150 ms · 0 token sinh
  ↓ trượt
định danh tên (dùng lại vector)           ~30 ms
  ↓
router (luật; mô hình ở việc 13.8)        ~0 ms
  ↓
một trong bốn nhánh                       12–350 ms
```

Tệp này cố ý **mỏng**: nếu nó dài ra thì thứ tự tầng đã bị chép ra khỏi đồ thị, và hai bản
sao sẽ lệch nhau.
"""

from __future__ import annotations

from typing import Any

from backend.app.workflow.run import RunResult, ask, tom_tat

__all__ = ["retrieve", "retrieve_full", "RunResult", "ask", "tom_tat"]


async def retrieve(
    question: str,
    *,
    turn_index: int = 1,
    generate: bool = True,
    log_trace: bool = True,
    source: str = "api",
) -> dict[str, Any]:
    """Trả lời một câu hỏi, dạng **từ điển** để API gửi thẳng ra ngoài."""
    ket_qua = await ask(
        question,
        turn_index=turn_index,
        generate=generate,
        log_trace=log_trace,
        source=source,
    )
    return ket_qua.to_dict()


async def retrieve_full(
    question: str, *, turn_index: int = 1, source: str = "admin"
) -> RunResult:
    """Như :func:`retrieve` nhưng trả **đối tượng đầy đủ** — cho CLI và trang kiểm thử."""
    return await ask(question, turn_index=turn_index, source=source)
