from __future__ import annotations

import uuid
from uuid import uuid4

import pytest
from backend.app.api import chat as chat_api
from backend.app.db.postgres import engine
from backend.app.main import app
from backend.app.rag import retrieval
from fastapi.testclient import TestClient
from sqlalchemy import text


def _register(client: TestClient) -> tuple[str, dict[str, str]]:
    username = f"test_opt_{uuid.uuid4().hex[:12]}"
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "matkhau123"},
    )
    assert response.status_code == 201, response.text
    return username, {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_session(client: TestClient, headers: dict[str, str]) -> str:
    response = client.post("/api/v1/chat-sessions", headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _cleanup(*usernames: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM users WHERE username = ANY(:names)"),
            {"names": list(usernames)},
        )


@pytest.fixture
def client() -> TestClient:
    chat_api._luot_goi.clear()
    chat_api.xoa_cache()
    with TestClient(app) as test_client:
        yield test_client
    chat_api._luot_goi.clear()
    chat_api.xoa_cache()


def _fake_retrieve(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(_question: str, **_kwargs) -> dict:
        return {
            "outcome": "answered",
            "answer": "Câu trả lời kiểm thử.",
            "citations": [],
        }

    monkeypatch.setattr(retrieval, "retrieve", fake)


def test_chat_co_session_id_nhung_chua_dang_nhap_tra_401(
    client: TestClient,
) -> None:
    response = client.post(
        "/chat",
        json={
            "question": "Còn lệ phí thì sao?",
            "session_id": str(uuid4()),
        },
    )

    assert response.status_code == 401


def test_chat_stream_co_session_id_nhung_chua_dang_nhap_tra_401(
    client: TestClient,
) -> None:
    response = client.post(
        "/chat/stream",
        json={
            "question": "Còn lệ phí thì sao?",
            "session_id": str(uuid4()),
        },
    )

    assert response.status_code == 401


def test_chat_voi_session_cua_user_khac_tra_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    username_a, headers_a = _register(client)
    username_b, headers_b = _register(client)
    try:
        session_a = _create_session(client, headers_a)
        _fake_retrieve(monkeypatch)

        response = client.post(
            "/chat",
            headers=headers_b,
            json={
                "question": "Còn lệ phí thì sao?",
                "session_id": session_a,
            },
        )

        assert response.status_code == 404
    finally:
        _cleanup(username_a, username_b)


def test_chat_voi_session_cua_chinh_user_duoc_chap_nhan(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    username, headers = _register(client)
    try:
        session_id = _create_session(client, headers)
        _fake_retrieve(monkeypatch)

        response = client.post(
            "/chat",
            headers=headers,
            json={
                "question": "Còn lệ phí thì sao?",
                "session_id": session_id,
            },
        )

        assert response.status_code == 200, response.text
        assert response.json()["answer"] == "Câu trả lời kiểm thử."
    finally:
        _cleanup(username)


def test_chat_guest_van_chay_khi_khong_co_session(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_retrieve(monkeypatch)

    response = client.post(
        "/chat",
        json={
            "question": "Hồ sơ gồm gì?",
            "history": [
                {"role": "user", "content": "Xin chào"},
                {"role": "assistant", "content": "Chào bạn."},
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "Câu trả lời kiểm thử."
