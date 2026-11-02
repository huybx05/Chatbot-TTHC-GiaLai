"""Engine PostgreSQL dùng chung cho toàn bộ ứng dụng.

Trước đây tầng auth có engine riêng (`auth/session_factory.py`), tạo hai
connection pool không cần thiết. Từ nay mọi module dùng chung engine này;
`auth/session_factory.py` chỉ còn là lớp tương thích re-export.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.app.config import settings


def _database_url() -> str:
    """Chuẩn hoá URL, kể cả khi ai đó dán URL thuần psycopg (không có driver)."""
    url = settings.database_url.strip()
    if not url:
        url = (
            f"postgresql+psycopg://{settings.database_user}:{settings.database_password}"
            f"@{settings.database_host}:{settings.database_port}/{settings.database_db}"
        )
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1).replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    return url


#: `pool_pre_ping` kiểm tra kết nối trước khi dùng, tránh lỗi "server closed
#: the connection unexpectedly" sau thời gian idle. Pool nhỏ là đủ cho quy mô
#: đồ án; tất cả module dùng chung một pool thay vì mỗi nơi tạo một engine.
engine: Engine = create_engine(
    _database_url(),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)
