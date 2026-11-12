from __future__ import annotations

import asyncio

from backend.app.rag import faq_global


def test_find_global_faq_exact_khong_can_qdrant(monkeypatch) -> None:
    rows = [
        {
            "id": "faq-1",
            "question": "Địa chỉ của Trung tâm Phục vụ hành chính công tỉnh Gia Lai ở đâu?",
            "answer": "Số 127 Hai Bà Trưng.",
            "intent": "general_info",
            "procedure_code": None,
            "procedure_name": None,
            "detail_url": None,
        }
    ]
    monkeypatch.setattr(faq_global, "_global_rows", lambda: rows)

    result = asyncio.run(
        faq_global.find_global_faq(
            "Địa chỉ của Trung tâm Phục vụ hành chính công tỉnh Gia Lai ở đâu?"
        )
    )

    assert result is not None
    assert result["match"] == "exact"
    assert result["id"] == "faq-1"
