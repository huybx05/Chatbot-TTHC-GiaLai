"""Engine SQLAlchemy dùng chung cho tầng xác thực.

Tách riêng khỏi `router.py` để router không phải biết cách tạo engine, và để chỗ này
là **điểm duy nhất** phải sửa khi Giai đoạn 6 chuyển sang `backend/app/db/postgres.py`.

`DATABASE_URL` trong `.env` đã đúng định dạng SQLAlchemy (`postgresql+psycopg://…`).
Nếu ai đó dán URL thuần của psycopg (`postgresql://…`) thì hàm dưới tự thêm hậu tố
driver — SQLAlchemy báo lỗi khó hiểu nếu thiếu nó.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.app.config import settings


def _database_url() -> str:
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


#: `pool_pre_ping` gửi một câu truy vấn nhẹ trước khi dùng kết nối trong pool. Cần thiết
#: vì PostgreSQL có thể đã đóng kết nối idle (hoặc máy ngủ) — không có nó thì request
#: đầu tiên sau một lúc rảnh sẽ lỗi `server closed the connection unexpectedly`.
#:
#: `pool_size` + `max_overflow`: trang /admin chỉ có vài người dùng nên 5 + 10 là thừa.
engine: Engine = create_engine(
    _database_url(),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    # In câu SQL khi DEBUG — tiện kiểm tra, nhưng sẽ lộ tham số ra log nên chỉ bật ở dev.
    echo=False,
)
