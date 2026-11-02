"""FastAPI entrypoint: app factory, health check and lifecycle."""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.app.api.admin import router as admin_router
from backend.app.api.chat import router as chat_router
from backend.app.api.chat_sessions import router as chat_sessions_router
from backend.app.api.costs import router as costs_router
from backend.app.api.documents import router as document_router
from backend.app.api.faq import router as faq_router
from backend.app.api.feedback import router as feedback_router
from backend.app.api.guest_sessions import cleanup_expired_guest_sessions
from backend.app.api.guest_sessions import router as guest_sessions_router
from backend.app.api.visits import router as visits_router
from backend.app.auth.router import router as auth_router
from backend.app.auth.security import cleanup_expired_sessions
from backend.app.auth.session_factory import engine
from backend.app.config import settings
from backend.app.rag import embeddings, hybrid
from backend.app.security_headers import SecurityHeadersMiddleware
from backend.app.workflow import question_parser

logger = logging.getLogger(__name__)


def _cleanup_sessions_once() -> None:
    with engine.begin() as conn:
        cleanup_expired_sessions(conn)
    cleanup_expired_guest_sessions()


async def _cleanup_sessions_periodically() -> None:
    while True:
        try:
            await asyncio.to_thread(_cleanup_sessions_once)
        except Exception:
            logger.exception("Không thể dọn session đã hết hạn.")
        await asyncio.sleep(60)


async def _cleanup_guest_sessions_periodically() -> None:
    while True:
        try:
            await asyncio.to_thread(cleanup_expired_guest_sessions)
        except Exception:
            logger.exception("Không thể dọn phiên khách đã hết hạn.")
        await asyncio.sleep(max(10, settings.guest_cleanup_interval_seconds))


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Vòng đời ứng dụng.

    ## Vì sao cần shutdown

    Các module giữ client async lâu dài cho embedding, semantic parser và search store.
    Không đóng khi tắt server thì mỗi lần restart lại để lại
    connection pool treo và in cảnh báo ``Unclosed client session``.

    Đóng ở đây cũng đảm bảo việc đóng chạy trên **event loop còn sống** — đó là lý do
    các client được tạo lười (xem ``hybrid._qdrant_client``).
    """
    cleanup_task = asyncio.create_task(_cleanup_sessions_periodically())
    guest_cleanup_task = asyncio.create_task(_cleanup_guest_sessions_periodically())
    try:
        yield
    finally:
        cleanup_task.cancel()
        guest_cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
        with contextlib.suppress(asyncio.CancelledError):
            await guest_cleanup_task
        await question_parser.close_client()
        await embeddings.close()
        await hybrid.close()


_is_production = settings.app_env.lower() in {"production", "prod"}


def _production_origins() -> list[str]:
    return [
        origin.strip()
        for origin in (settings.cors_origins or "").split(",")
        if origin.strip()
    ]


def _production_hosts() -> list[str]:
    return [host.strip() for host in (settings.allowed_hosts or "").split(",") if host.strip()]


def _validate_production_settings() -> None:
    """Fail fast instead of deploying with localhost CORS / no TrustedHost."""
    if settings.app_env.lower() not in {"production", "prod"}:
        return
    hosts = _production_hosts()
    origins = _production_origins()
    if not hosts:
        raise RuntimeError(
            "Thiếu ALLOWED_HOSTS ở production. Đặt domain thật, ví dụ "
            "ALLOWED_HOSTS=your-domain.example."
        )
    if not origins:
        raise RuntimeError("Thiếu CORS_ORIGINS ở production.")
    if any(origin == "*" for origin in origins):
        raise RuntimeError("CORS_ORIGINS không được chứa '*' ở production.")
    if any("localhost" in origin or "127.0.0.1" in origin for origin in origins):
        raise RuntimeError("CORS_ORIGINS ở production không được là localhost.")


_validate_production_settings()

app = FastAPI(
    title="Chatbot TTHC Gia Lai API",
    version="0.1.0",
    debug=settings.debug,
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in (settings.cors_origins or "").split(",")
        if origin.strip()
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

if _is_production:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=_production_hosts() + ["localhost", "127.0.0.1"],
    )

if settings.force_https:
    app.add_middleware(HTTPSRedirectMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(chat_sessions_router, prefix=settings.api_v1_prefix)
app.include_router(admin_router, prefix="/api/admin")
app.include_router(costs_router, prefix="/api/admin")
app.include_router(chat_router)
app.include_router(feedback_router)
app.include_router(guest_sessions_router)
app.include_router(document_router, prefix=settings.api_v1_prefix)
app.include_router(faq_router, prefix=settings.api_v1_prefix)
app.include_router(visits_router, prefix=settings.api_v1_prefix)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe used by local runs and the Docker health check."""
    return {"status": "ok"}
