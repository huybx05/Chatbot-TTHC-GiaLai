from __future__ import annotations

from backend.app.db.postgres import engine
from backend.app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import text

client = TestClient(app)


def _visits() -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT COUNT(*) FROM audit_logs WHERE action = 'page_view'")
            ).scalar_one()
        )


def test_page_visit_increments_counter() -> None:
    before = _visits()
    response = client.post("/api/v1/visits")
    assert response.status_code == 200
    assert response.json() == {"recorded": True}
    assert _visits() == before + 1
