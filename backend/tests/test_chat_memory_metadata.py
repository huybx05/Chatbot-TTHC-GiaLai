from __future__ import annotations

from backend.app.api.chat import _assistant_metadata, _dung_phan_hoi


def _result(*, outcome: str, answerable: bool) -> dict:
    return {
        "outcome": outcome,
        "answer": "Câu trả lời." if answerable else "",
        "refusal": "" if answerable else "Cần hỏi lại.",
        "answerable": answerable,
        "resolution": {
            "code": "1.014100",
            "name": "Cấp lại Chứng chỉ hành nghề dược",
        },
        "answered_procedure": (
            {
                "code": "1.014100",
                "name": "Cấp lại Chứng chỉ hành nghề dược",
                "source": "resolution",
            }
            if answerable
            else {}
        ),
        "citations": [],
        "documents": [],
        "options": [],
    }


def test_abstained_khong_duoc_gan_procedure_vao_response() -> None:
    response = _dung_phan_hoi(_result(outcome="abstained", answerable=False))

    assert response.procedure is None
    assert _assistant_metadata(response)["memory_eligible"] is False


def test_answered_nhung_khong_co_bang_chung_khong_duoc_ghi_memory() -> None:
    response = _dung_phan_hoi(_result(outcome="answered", answerable=False))

    assert response.procedure is None
    assert _assistant_metadata(response)["memory_eligible"] is False


def test_answered_co_bang_chung_duoc_ghi_memory() -> None:
    response = _dung_phan_hoi(_result(outcome="answered", answerable=True))

    assert response.procedure is not None
    assert response.procedure.procedure_code == "1.014100"
    assert _assistant_metadata(response)["memory_eligible"] is True


def test_api_dung_answered_procedure_khong_dung_candidate() -> None:
    result = _result(outcome="answered", answerable=True)
    result["resolution"] = {
        "code": "1.000001",
        "name": "Candidate sai",
    }
    result["answered_procedure"] = {
        "code": "1.014100",
        "name": "Thủ tục đã trả lời",
        "source": "grounded",
    }

    response = _dung_phan_hoi(result)

    assert response.procedure is not None
    assert response.procedure.procedure_code == "1.014100"
