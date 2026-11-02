"""Cấu hình chung cho **bài kiểm** — không ảnh hưởng lúc chạy thật.

Tệp này chỉ được pytest nạp. Nó đặt hai công tắc về ``0`` để cả bộ test **không gọi API trả
tiền** (router Qwen và bước sinh DeepSeek): không có nó, mỗi lần chạy test có bằng chứng là một
lần gọi thật — vừa tốn tiền, vừa chậm, vừa làm kết quả phụ thuộc mạng.

Lúc chạy sản phẩm, hai biến này **không được đặt**, nên cả hai bước đều bật. Bài kiểm nào cần
đo đường có gọi mô hình thì tự ``monkeypatch.setenv(..., "1")`` trong thân bài.
"""

from __future__ import annotations

import os

import pytest

# Tests run over plain HTTP. Keep the production-only cookie/HTTPS switches
# out of the test process even when the developer's .env says production.
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DEBUG", "False")
os.environ.setdefault("FORCE_HTTPS", "False")
# Existing tests exercise business logic, not throttling; explicit rate-limit
# tests below turn the limits back on.
os.environ.setdefault("LOGIN_RATE_LIMIT_PER_MIN", "0")
os.environ.setdefault("REGISTER_RATE_LIMIT_PER_MIN", "0")
os.environ.setdefault("REFRESH_RATE_LIMIT_PER_MIN", "0")
os.environ.setdefault("CHAT_RATE_LIMIT_PER_MIN", "0")

from backend.app.auth.dependencies import require_admin  # noqa: E402
from backend.app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def _tat_goi_mo_hinh(monkeypatch: pytest.MonkeyPatch):
    """Mặc định **không** gọi mô hình trong test. Bài kiểm nào cần thì tự bật."""
    monkeypatch.setenv("ROUTER_USE_LLM", "0")
    monkeypatch.setenv("ANSWER_USE_LLM", "0")
    yield


@pytest.fixture(autouse=True)
def _bypass_admin_auth_for_existing_tests():
    """Các test cũ kiểm tra nghiệp vụ admin, không kiểm tra auth.

    Auth của router được kiểm riêng trong ``test_admin_auth.py``; fixture này
    chỉ thay dependency admin bằng một admin giả để các test CRUD không phải
    đăng nhập lại ở mọi bài.
    """
    app.dependency_overrides[require_admin] = lambda: {
        "id": 1,
        "username": "test-admin",
        "role": "admin",
        "jti": "",
    }
    yield
    app.dependency_overrides.pop(require_admin, None)

