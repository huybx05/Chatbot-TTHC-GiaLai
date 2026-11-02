from __future__ import annotations

import json
from uuid import uuid4

from backend.app.db.postgres import engine
from backend.app.main import app
from fastapi.testclient import TestClient
from sqlalchemy import text

client = TestClient(app)


def _payload() -> dict[str, str]:
    return {
        "question": f"FAQ kiểm thử {uuid4()}",
        "answer": "Câu trả lời kiểm thử.",
        "intent": "general_info",
    }


def test_danh_sach_intent_lay_tu_du_lieu_goc() -> None:
    response = client.get("/api/admin/faq/intents")

    assert response.status_code == 200
    labels = {item["value"]: item["label"] for item in response.json()}
    assert labels["required_documents"] == "Hồ sơ, giấy tờ"
    assert labels["processing_time"] == "Thời hạn giải quyết"
    assert labels["general_info"] == "Thông tin chung"
    assert labels["none"] == "Không"


def test_crud_faq_khong_gan_thu_tuc() -> None:
    payload = _payload()
    faq_id = ""

    try:
        created = client.post("/api/admin/faq", json=payload)
        assert created.status_code == 200
        body = created.json()
        faq_id = body["id"]
        assert body["status"] == "ready"
        assert body["intent"] == "general_info"

        with engine.connect() as conn:
            procedure_code = conn.execute(
                text("SELECT procedure_code FROM faq WHERE faq_id = :id"),
                {"id": faq_id},
            ).scalar()
        assert procedure_code is None

        listed = client.get("/api/admin/faq")
        assert listed.status_code == 200
        assert any(item["id"] == faq_id for item in listed.json()["items"])

        updated = client.patch(
            f"/api/admin/faq/{faq_id}",
            json={**payload, "answer": "Đã sửa."},
        )
        assert updated.status_code == 200
        assert updated.json()["answer"] == "Đã sửa."

        suggestions = client.get("/api/v1/faq/suggestions")
        assert suggestions.status_code == 200
        assert any(
            item["id"] == faq_id
            for item in suggestions.json()["items"]
        )

        deleted = client.delete(f"/api/admin/faq/{faq_id}")
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] == 1
        faq_id = ""
    finally:
        if faq_id:
            client.delete(f"/api/admin/faq/{faq_id}")


def test_intent_khong_hop_le_bi_tu_choi() -> None:
    response = client.post(
        "/api/admin/faq",
        json={
            "question": "Câu hỏi",
            "answer": "Câu trả lời",
            "intent": "khong_ton_tai",
        },
    )

    assert response.status_code == 422


def test_doi_trang_thai_faq_ready_va_draft() -> None:
    faq_id = ""

    try:
        created = client.post("/api/admin/faq", json=_payload())
        assert created.status_code == 200
        faq_id = created.json()["id"]

        to_draft = client.patch(
            f"/api/admin/faq/{faq_id}/status",
            json={"status": "draft"},
        )
        assert to_draft.status_code == 200
        assert to_draft.json()["status"] == "draft"

        to_ready = client.patch(
            f"/api/admin/faq/{faq_id}/status",
            json={"status": "ready"},
        )
        assert to_ready.status_code == 200
        assert to_ready.json()["status"] == "ready"
    finally:
        if faq_id:
            client.delete(f"/api/admin/faq/{faq_id}")


def test_tao_va_sua_faq_bang_dropdown_trang_thai() -> None:
    payload = {**_payload(), "status": "draft"}
    faq_id = ""

    try:
        created = client.post("/api/admin/faq", json=payload)
        assert created.status_code == 200
        faq_id = created.json()["id"]
        assert created.json()["status"] == "draft"

        updated = client.patch(
            f"/api/admin/faq/{faq_id}",
            json={**payload, "status": "ready"},
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "ready"
    finally:
        if faq_id:
            client.delete(f"/api/admin/faq/{faq_id}")


def test_faq_ready_duoc_tra_loi_truc_tiep_khong_qua_rag() -> None:
    question = f"Địa chỉ làm việc kiểm thử {uuid4()}?"
    answer = "Số 127 đường Hai Bà Trưng, phường Quy Nhơn, tỉnh Gia Lai."
    faq_id = ""

    try:
        created = client.post(
            "/api/admin/faq",
            json={
                "question": question,
                "answer": answer,
                "intent": "general_info",
                "status": "ready",
            },
        )
        assert created.status_code == 200
        faq_id = created.json()["id"]

        response = client.post("/chat", json={"question": question})
        assert response.status_code == 200
        body = response.json()
        assert body["answer"] == answer
        assert body["citations"] == []

        with client.stream(
            "POST",
            "/chat/stream",
            json={"question": question},
        ) as streamed:
            assert streamed.status_code == 200
            events: list[tuple[str, dict]] = []
            event = ""
            for line in streamed.iter_lines():
                if line.startswith("event: "):
                    event = line.removeprefix("event: ")
                elif line.startswith("data: "):
                    events.append((event, json.loads(line.removeprefix("data: "))))

        assert events[1][0] == "meta"
        assert events[-1][0] == "done"
        assert events[-1][1]["answer"] == answer
    finally:
        if faq_id:
            client.delete(f"/api/admin/faq/{faq_id}")
