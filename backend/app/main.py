"""FastAPI entrypoint: app factory, health check and lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.admin import router as admin_router
from backend.app.api.chat import router as chat_router
from backend.app.auth.router import router as auth_router
from backend.app.config import settings
from backend.app.rag import embeddings, hybrid
from backend.app.workflow import question_parser


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
    yield
    await question_parser.close_client()
    await embeddings.close()
    await hybrid.close()


app = FastAPI(
    title="Chatbot TTHC Gia Lai API",
    version="0.1.0",
    debug=settings.debug,
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
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(admin_router, prefix="/api/admin")
app.include_router(chat_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe used by local runs and the Docker health check."""
    return {"status": "ok"}
