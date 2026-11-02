"""Rate limiter dùng Redis, fallback in-memory khi Redis chưa sẵn sàng.

Redis là service riêng; ở local có thể không cài. Module này vẫn hoạt động với
một cửa sổ trượt trong RAM để test và chạy một process. Khi có ``REDIS_URL``,
bộ đếm được chia sẻ giữa các worker/instance.

Thiết kế cố ý đơn giản: cửa sổ cố định 60 giây, đủ cho login/register/chat.
Không dùng làm giới hạn nghiệp vụ hay tính cước.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass

from backend.app.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    retry_after: int = 0


class RateLimiter:
    def __init__(self, redis_url: str = "") -> None:
        self._redis = None
        self._redis_failed = False
        if redis_url:
            try:
                import redis

                self._redis = redis.Redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=0.5,
                    socket_timeout=0.5,
                )
            except Exception:  # noqa: BLE001 - Redis là optional
                logger.warning("Không khởi tạo được Redis rate limiter; dùng in-memory.")
                self._redis = None
                self._redis_failed = True
        self._memory: dict[str, deque[float]] = {}

    def check(self, key: str, limit: int, window_seconds: int = 60) -> RateLimitResult:
        if limit <= 0:
            return RateLimitResult(True)
        if not key:
            key = "unknown"
        redis_key = f"rate_limit:{key}"

        if self._redis is not None and not self._redis_failed:
            try:
                count = int(self._redis.incr(redis_key))
                if count == 1:
                    self._redis.expire(redis_key, window_seconds)
                if count > limit:
                    ttl = int(self._redis.ttl(redis_key))
                    return RateLimitResult(False, max(ttl, 1))
                return RateLimitResult(True)
            except Exception as exc:  # noqa: BLE001 - Redis down phải fallback
                self._redis_failed = True
                logger.warning("Redis rate limiter lỗi, chuyển in-memory: %s", type(exc).__name__)

        now = time.monotonic()
        bucket = self._memory.setdefault(key, deque())
        while bucket and now - bucket[0] > window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = int(window_seconds - (now - bucket[0])) + 1
            return RateLimitResult(False, max(retry_after, 1))
        bucket.append(now)
        if len(self._memory) > 4096:
            for stale_key in [k for k, v in self._memory.items() if not v]:
                self._memory.pop(stale_key, None)
        return RateLimitResult(True)

    def reset(self) -> None:
        """Xoá bộ đếm in-memory; dùng cho test."""
        self._memory.clear()
        self._redis_failed = False


#: Singleton dùng chung. Đổi ``REDIS_URL`` rồi restart process để nạp lại.
limiter = RateLimiter(settings.redis_url)
