# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend ./backend
COPY data_pipeline ./data_pipeline
COPY config ./config

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH"

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --home-dir /app app \
    && mkdir -p /app/logs /app/data \
    && chown -R app:app /app

WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv ./.venv
COPY --from=builder --chown=app:app /app/backend ./backend
COPY --from=builder --chown=app:app /app/data_pipeline ./data_pipeline
COPY --from=builder --chown=app:app /app/config ./config
COPY --from=builder --chown=app:app /app/pyproject.toml /app/uv.lock /app/README.md ./
COPY --chown=app:app scripts ./scripts

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

# Một container chỉ nên chạy 1 process Uvicorn quản lý worker.
# Đặt WEB_CONCURRENCY=2 cho VPS 4 vCPU / 8 GB; không tăng quá 2 nếu RAM thấp.
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
