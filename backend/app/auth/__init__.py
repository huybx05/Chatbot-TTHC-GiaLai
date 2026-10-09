"""Package xác thực — băm mật khẩu, JWT, phiên làm mới, dependency FastAPI."""

from backend.app.auth.dependencies import (
    AdminUser,
    AnalystUser,
    CurrentUser,
    get_current_user,
    require_admin,
    require_analyst,
)
from backend.app.auth.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    needs_rehash,
    verify_password,
)

__all__ = [
    "AdminUser",
    "AnalystUser",
    "CurrentUser",
    "create_access_token",
    "decode_access_token",
    "get_current_user",
    "hash_password",
    "needs_rehash",
    "require_admin",
    "require_analyst",
    "verify_password",
]
