"""Security headers for every HTTP response.

The headers are intentionally conservative:
- ``X-Content-Type-Options`` blocks MIME sniffing.
- ``X-Frame-Options`` and ``frame-ancestors`` block clickjacking.
- ``Referrer-Policy`` avoids leaking admin URLs to third parties.
- HSTS is only sent in production, after HTTPS has been verified.

TLS termination/redirect should be enforced at the reverse proxy (Cloudflare or
Nginx). The optional ``FORCE_HTTPS`` switch is for deployments where the app is
exposed directly and receives the original ``https`` scheme.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.app.config import settings

_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "frame-ancestors 'none'; base-uri 'self'",
    "Cross-Origin-Opener-Policy": "same-origin",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        for name, value in _HEADERS.items():
            response.headers.setdefault(name, value)
        if settings.app_env.lower() in {"production", "prod"}:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        # Uvicorn advertises itself by default; do not expose server details.
        if "server" in response.headers:
            del response.headers["server"]
        return response
