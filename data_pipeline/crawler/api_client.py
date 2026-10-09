"""Client gọi API công khai của Cổng Dịch vụ công Quốc gia.

Hai endpoint được dùng:

1. ``list-all-public-formality-by-citizen`` — tra mã thủ tục, trả về UUID.
2. ``get-formality-by-citizen`` — lấy toàn bộ nội dung thủ tục theo UUID.

API công khai, không cần đăng nhập. Nếu về sau cổng siết truy cập, điền cookie
phiên vào ``DVC_COOKIE`` trong ``.env``; code sẽ tự gửi kèm.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from . import (
    API_DETAIL_PATH,
    API_LIST_PATH,
    MAX_RETRIES,
    RETRY_BACKOFF_SECONDS,
    TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


class DvcApiError(RuntimeError):
    """Lỗi gọi API cổng dịch vụ công."""


class DvcApiClient:
    """Client đồng bộ, dùng chung một kết nối cho cả phiên crawl."""

    def __init__(
        self,
        base_url: str,
        *,
        cookie: str = "",
        delay_seconds: float = 1.0,
        user_agent: str = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
        ),
    ) -> None:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": base_url,
            "User-Agent": user_agent,
        }
        if cookie:
            headers["Cookie"] = cookie

        self._client = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        self._delay_seconds = delay_seconds

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DvcApiClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST có retry giới hạn. Không retry lỗi 4xx vì đó là lỗi payload."""
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._client.post(path, json=payload)

                if response.status_code >= 500:
                    raise DvcApiError(f"HTTP {response.status_code} từ {path}")

                if response.status_code >= 400:
                    raise DvcApiError(
                        f"HTTP {response.status_code} từ {path}: {response.text[:200]}"
                    )

                body = response.json()
                if body.get("code") != "OK":
                    raise DvcApiError(f"API trả code={body.get('code')!r} từ {path}")

                return body.get("data") or {}

            except DvcApiError as exc:
                if "HTTP 4" in str(exc):
                    raise
                last_error = exc
            except httpx.HTTPError as exc:  # lỗi mạng, timeout
                last_error = exc
            except ValueError as exc:  # JSON hỏng
                last_error = exc

            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF_SECONDS * attempt
                logger.warning(
                    "Lần thử %d/%d thất bại cho %s (%s), chờ %.1fs",
                    attempt,
                    MAX_RETRIES,
                    path,
                    last_error,
                    wait,
                )
                time.sleep(wait)

        raise DvcApiError(f"Thất bại sau {MAX_RETRIES} lần gọi {path}: {last_error}")

    def search_by_code(self, procedure_code: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Tra danh sách thủ tục khớp mã. Trả về mảng item thô."""
        data = self._post(
            API_LIST_PATH,
            {
                "limit": limit,
                "lastId": "",
                "q": procedure_code,
                "categoryId": "",
                "departmentCode": "",
                "formalityType": "",
            },
        )
        items = data.get("items") or []
        return [item for item in items if item.get("code") == procedure_code]

    def get_detail(self, formality_id: str) -> dict[str, Any]:
        """Lấy toàn bộ nội dung một thủ tục theo UUID."""
        return self._post(API_DETAIL_PATH, {"id": formality_id})

    def sleep_between_requests(self) -> None:
        """Nghỉ giữa các request để không gây tải cho cổng."""
        if self._delay_seconds > 0:
            time.sleep(self._delay_seconds)
