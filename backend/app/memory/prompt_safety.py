"""Đưa nội dung lịch sử vào prompt như **dữ liệu**, không phải chỉ dẫn.

Không thể tin nội dung do người dùng hoặc câu trả lời cũ sinh ra. Trước khi đưa
vào prompt, thay dấu ngoặc nhọn để nội dung không thể đóng/mở các thẻ đánh dấu
vùng dữ liệu như ``</HISTORY>`` hoặc ``</MEMORY>``.
"""

from __future__ import annotations


def neutralize_untrusted_text(value: object) -> str:
    return str(value or "").replace("<", "‹").replace(">", "›")
