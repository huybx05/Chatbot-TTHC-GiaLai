"""Lớp tương thích: engine xác thực dùng chung engine của ứng dụng.

Trước đây file này tạo một ``create_engine`` riêng, dẫn tới hai connection pool
cho cùng một database. Từ khi ``backend/app/db/postgres.py`` là nguồn duy nhất,
file này chỉ re-export để các import cũ (``auth.router``, ``main``) không phải
sửa hàng loạt.

Code mới nên import trực tiếp:

```python
from backend.app.db.postgres import engine
```
"""

from __future__ import annotations

from backend.app.db.postgres import engine

__all__ = ["engine"]
