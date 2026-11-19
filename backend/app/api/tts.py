"""Chuyển câu trả lời thành giọng nói qua VieNeu Cloud API.

Endpoint này là **proxy phía server**: API key không bao giờ đi xuống trình duyệt.
Frontend chỉ gửi phần chữ cần đọc, backend gọi VieNeu rồi trả bytes audio.
"""

from __future__ import annotations

import logging
from typing import Annotated

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, StringConstraints

from backend.app.config import settings
from backend.app.rate_limit import limiter
from backend.app.security_utils import client_ip

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tts"])


class TtsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=50_000),
    ]
    voice: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] = ""


@router.post("/tts")
async def text_to_speech(payload: TtsRequest, request: Request) -> Response:
    """Trả file MP3 cho đoạn text đã được người dùng chủ động bấm nghe."""
    if not settings.vieneu_api_key:
        raise HTTPException(
            status_code=503,
            detail="Tính năng đọc câu trả lời chưa được cấu hình.",
        )

    if len(payload.text) > settings.tts_max_chars:
        raise HTTPException(
            status_code=413,
            detail=f"Câu trả lời quá dài để đọc (tối đa {settings.tts_max_chars} ký tự).",
        )

    ip = client_ip(request) or "unknown"
    limited = limiter.check(
        f"tts:{ip}",
        limit=settings.tts_rate_limit_per_min,
    )
    if not limited.allowed:
        raise HTTPException(
            status_code=429,
            detail="Bạn đã yêu cầu đọc quá nhiều lần. Vui lòng thử lại sau.",
            headers={"Retry-After": str(limited.retry_after)},
        )

    base_url = settings.vieneu_base_url.rstrip("/")
    body = {
        "model": settings.vieneu_model,
        "input": payload.text,
        "voice": payload.voice or settings.vieneu_voice,
        "response_format": "mp3",
        "speed": min(3.0, max(0.5, settings.vieneu_speed)),
    }
    headers = {
        "Authorization": f"Bearer {settings.vieneu_api_key}",
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    try:
        async with httpx.AsyncClient(timeout=settings.vieneu_timeout_s) as client:
            response = await client.post(
                f"{base_url}/audio/speech",
                json=body,
                headers=headers,
            )
    except httpx.TimeoutException as exc:
        logger.warning("VieNeu TTS timeout: %s", type(exc).__name__)
        raise HTTPException(
            status_code=504,
            detail="Máy chủ đọc câu trả lời phản hồi quá lâu. Vui lòng thử lại.",
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("VieNeu TTS lỗi kết nối: %s", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="Không kết nối được dịch vụ đọc câu trả lời.",
        ) from exc

    if response.status_code != 200:
        # Không trả nguyên body lỗi của nhà cung cấp ra người dùng cuối.
        logger.warning(
            "VieNeu TTS trả lỗi HTTP %s: %s",
            response.status_code,
            response.text[:300],
        )
        if response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="Dịch vụ đọc câu trả lời đang quá tải. Vui lòng thử lại sau.",
            )
        if response.status_code in {401, 403}:
            raise HTTPException(
                status_code=503,
                detail="Dịch vụ đọc câu trả lời tạm thời không khả dụng.",
            )
        raise HTTPException(
            status_code=502,
            detail="Không tạo được âm thanh cho câu trả lời này.",
        )

    if not response.content:
        raise HTTPException(
            status_code=502,
            detail="Dịch vụ đọc câu trả lời không trả về âm thanh.",
        )

    return Response(
        content=response.content,
        media_type=response.headers.get("content-type", "audio/mpeg"),
        headers={
            "Cache-Control": "private, max-age=86400",
            "Content-Disposition": 'inline; filename="cau-tra-loi.mp3"',
        },
    )
