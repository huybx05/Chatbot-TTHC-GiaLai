from __future__ import annotations

import pytest
from backend.app.api.guest_sessions import _set_cookie
from backend.app.auth.router import _enforce_rate_limit
from backend.app.config import settings
from backend.app.main import _validate_production_settings
from backend.app.rate_limit import RateLimiter, limiter
from backend.app.security_utils import client_ip
from fastapi import HTTPException, Response
from starlette.requests import Request


def _request(peer: str, headers: list[tuple[bytes, bytes]]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": headers,
            "client": (peer, 12345),
        }
    )


def test_in_memory_rate_limit_blocks_after_limit() -> None:
    guard = RateLimiter("")
    assert guard.check("ip:one", limit=2).allowed
    assert guard.check("ip:one", limit=2).allowed
    blocked = guard.check("ip:one", limit=2)
    assert not blocked.allowed
    assert blocked.retry_after >= 1


def test_trusted_proxy_header_is_used() -> None:
    request = _request(
        "127.0.0.1",
        [(b"x-forwarded-for", b"203.0.113.9, 10.0.0.1")],
    )
    assert client_ip(request) == "203.0.113.9"


def test_untrusted_peer_cannot_spoof_forwarded_for() -> None:
    request = _request(
        "198.51.100.7",
        [(b"x-forwarded-for", b"203.0.113.9")],
    )
    assert client_ip(request) == "198.51.100.7"


def test_enforce_rate_limit_uses_trusted_proxy_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter.reset()
    monkeypatch.setattr(settings, "login_rate_limit_per_min", 1)
    request = _request("127.0.0.1", [(b"x-forwarded-for", b"203.0.113.9")])

    _enforce_rate_limit(request, "test-login", 1)
    with pytest.raises(HTTPException) as exc:
        _enforce_rate_limit(request, "test-login", 1)
    assert exc.value.status_code == 429
    limiter.reset()


def test_guest_cookie_is_secure_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "guest_cookie_secure", False)
    response = Response()
    _set_cookie(response, "test-token")
    cookie = response.headers["set-cookie"]
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie


def test_production_guard_rejects_missing_allowed_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "allowed_hosts", "")
    monkeypatch.setattr(settings, "cors_origins", "https://example.gov.vn")
    with pytest.raises(RuntimeError, match="ALLOWED_HOSTS"):
        _validate_production_settings()


def test_production_guard_rejects_localhost_cors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "allowed_hosts", "example.gov.vn")
    monkeypatch.setattr(settings, "cors_origins", "http://localhost:5173")
    with pytest.raises(RuntimeError, match="localhost"):
        _validate_production_settings()

