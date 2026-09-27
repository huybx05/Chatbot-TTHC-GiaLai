"""FastAPI entrypoint: app factory, health check and lifecycle."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import settings

app = FastAPI(
    title="TTHC AI Chatbot API",
    version="0.1.0",
    debug=settings.debug,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe used by local runs and the Docker health check."""
    return {"status": "ok"}
