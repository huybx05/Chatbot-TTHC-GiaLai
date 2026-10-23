"""Nhúng câu hỏi — **một chỗ duy nhất** gọi API embedding.

## Vì sao phải tách riêng file này

Có ít nhất hai tầng cần vector của **cùng một** câu hỏi:

* (FAQ đã được gỡ khỏi luồng truy xuất)
* ``hybrid``    — tìm trong collection ``semantic_search``

Nếu mỗi module tự gọi ``embeddings.create()`` thì sẽ có hai đường code gọi API với
cùng tham số, và chúng sẽ lệch nhau khi ai đó đổi model hoặc đổi cách chuẩn bị đầu
vào. Ngoài ra vector nhúng ra sẽ không tái dùng được: một câu hỏi bị nhúng **hai lần**
cho hai tầng (tốn gấp đôi, ~350 ms mỗi lần).

## Kế thừa vector

Tầng gọi nên nhúng **một lần** rồi truyền vector xuống:

```python
vector = await embeddings.embed(question)

if hit is None:
    chunks = await hybrid.hybrid(question, vector=vector)   # tầng 2, dùng lại
```

## Client lười theo event loop

Xem ``_Embedder._get()``. Tóm tắt: ``AsyncOpenAI`` (bọc ``httpx.AsyncClient``) giữ
connection pool gắn với event loop đã dùng nó lần đầu; loop đóng thì tái sử dụng ném
``RuntimeError: Event loop is closed``. Tạo client ở cấp module sẽ gặp lỗi này ở
request thứ hai qua ``TestClient`` (mỗi request một loop). Vì vậy client được tạo lười
và **tạo lại khi loop đổi**.
"""

from __future__ import annotations

import asyncio
import logging

from openai import AsyncOpenAI

from backend.app.config import settings

logger = logging.getLogger(__name__)


class _Embedder:
    """Giữ một client embedding, gắn với event loop đang chạy."""

    def __init__(self) -> None:
        # Thiếu API key thì ``enabled`` là False — tầng gọi tự quyết định bỏ qua
        # đường tắt thay vì để lỗi bung ra ngoài.
        self._enabled = bool(settings.qwen_api_key.strip())
        self._client: AsyncOpenAI | None = None
        self._bound_loop: asyncio.AbstractEventLoop | None = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _get(self) -> AsyncOpenAI:
        """Trả client của event loop hiện tại, tạo mới nếu loop đã đổi.

        ## Tiếng ồn đã biết khi chạy nhiều event loop

        Client của loop cũ **không đóng được nữa** (loop đã chết), nên chỉ bỏ tham
        chiếu. Khi garbage collector gọi finalizer của nó, ``httpx`` cố ``aclose()``
        trên loop đã đóng và in ra::

            Task exception was never retrieved
            ... RuntimeError: Event loop is closed

        Đây là **log rác, không phải lỗi chức năng**: request vẫn trả HTTP 200. Nó chỉ
        xuất hiện khi một process dùng **nhiều** event loop — tức là trong test qua
        ``TestClient`` (mỗi request một loop). Trên uvicorn chỉ có một loop, nên
        ``close()`` chạy lúc loop còn sống và không có tiếng ồn này.

        Không sửa bằng cách chạm vào thuộc tính riêng của ``httpx`` — cách đó giòn hơn
        cái log nó định che.
        """
        loop = asyncio.get_running_loop()
        if self._client is None or self._bound_loop is not loop:
            # Client của loop cũ không đóng được nữa (loop đã chết) nên chỉ bỏ tham
            # chiếu; tài nguyên đã được giải phóng cùng loop.
            self._client = AsyncOpenAI(
                base_url=settings.qwen_base_url,
                api_key=settings.qwen_api_key,
            )
            self._bound_loop = loop
        return self._client

    async def embed(self, text: str) -> list[float]:
        """Nhúng một đoạn văn bản, trả vector độ dài ``EMBEDDING_DIM`` (1024).

        **Phải dùng cùng model với lúc index.** Đổi ``EMBEDDING_MODEL_NAME`` thì phải
        reindex toàn bộ ``semantic_search``; nếu không, vector truy
        vấn và vector lưu trữ nằm ở hai không gian khác nhau và cosine vô nghĩa.
        """
        client = self._get()
        result = await client.embeddings.create(
            model=settings.embedding_model_name,
            input=[text],
        )
        return list(result.data[0].embedding)

    async def close(self) -> None:
        """Đóng client. Không bao giờ ném lỗi."""
        if self._client is not None:
            try:
                await self._client.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Đóng client embedding không sạch: %s", exc)
        self._client = None
        self._bound_loop = None


#: Instance dùng chung cho cả process.
_embedder = _Embedder()


async def embed(text: str) -> list[float]:
    """Nhúng một câu hỏi. Đây là hàm mọi tầng truy xuất nên gọi."""
    return await _embedder.embed(text)


def enabled() -> bool:
    """API embedding có cấu hình không."""
    return _embedder.enabled


async def close() -> None:
    """Đóng client. Gọi trong lifespan shutdown của FastAPI."""
    await _embedder.close()
