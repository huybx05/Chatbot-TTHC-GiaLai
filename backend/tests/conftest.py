"""Cấu hình chung cho **bài kiểm** — không ảnh hưởng lúc chạy thật.

Tệp này chỉ được pytest nạp. Nó đặt hai công tắc về ``0`` để cả bộ test **không gọi API trả
tiền** (router Qwen và bước sinh DeepSeek): không có nó, mỗi lần chạy test có bằng chứng là một
lần gọi thật — vừa tốn tiền, vừa chậm, vừa làm kết quả phụ thuộc mạng.

Lúc chạy sản phẩm, hai biến này **không được đặt**, nên cả hai bước đều bật. Bài kiểm nào cần
đo đường có gọi mô hình thì tự ``monkeypatch.setenv(..., "1")`` trong thân bài.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _tat_goi_mo_hinh(monkeypatch: pytest.MonkeyPatch):
    """Mặc định **không** gọi mô hình trong test. Bài kiểm nào cần thì tự bật."""
    monkeypatch.setenv("ROUTER_USE_LLM", "0")
    monkeypatch.setenv("ANSWER_USE_LLM", "0")
    yield
