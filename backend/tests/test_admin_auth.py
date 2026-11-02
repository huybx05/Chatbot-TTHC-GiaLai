from __future__ import annotations

from backend.app.auth.dependencies import require_admin
from backend.app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_admin_endpoints_require_authentication() -> None:
    app.dependency_overrides.pop(require_admin, None)
    try:
        for path in (
            "/api/admin/system/status",
            "/api/admin/conversations",
            "/api/admin/faq",
        ):
            response = client.get(path)
            assert response.status_code == 401, path
    finally:
        app.dependency_overrides[require_admin] = lambda: {
            "id": 1,
            "username": "test-admin",
            "role": "admin",
            "jti": "",
        }


def test_security_headers_are_present() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "server" not in response.headers
