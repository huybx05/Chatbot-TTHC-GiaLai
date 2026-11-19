"""Test các guard facet hẹp trong question parser."""

from __future__ import annotations

from backend.app.workflow.question_frame import Facet
from backend.app.workflow.question_parser import _apply_facet_guards


def test_cap_thuc_hien_khong_bi_nham_thanh_co_quan_thuc_hien() -> None:
    frame = {
        "scope": "tthc",
        "subject_mentions": [],
        "requests": [
            {
                "text": "thực hiện ở cấp nào",
                "facet": Facet.IMPLEMENTING_AGENCY,
                "operation": "get",
                "subject_ref": None,
                "constraints": [],
                "scenario": "",
            }
        ],
        "ambiguity": {"present": False, "kind": "none", "reason": ""},
    }

    _apply_facet_guards(frame, "Thủ tục này được thực hiện ở cấp nào?")

    assert frame["requests"][0]["facet"] == Facet.ADMINISTRATIVE_LEVEL


def test_thoi_han_va_le_phi_tach_thanh_hai_request() -> None:
    frame = {
        "scope": "tthc",
        "subject_mentions": [],
        "requests": [
            {
                "text": "thời hạn và lệ phí",
                "facet": Facet.GENERAL_INFO,
                "operation": "get",
                "subject_ref": None,
                "constraints": [],
                "scenario": "",
            }
        ],
        "ambiguity": {"present": False, "kind": "none", "reason": ""},
    }

    _apply_facet_guards(frame, "Thời hạn và lệ phí của thủ tục này là gì?")

    assert [item["facet"] for item in frame["requests"]] == [
        Facet.PROCESSING_TIME,
        Facet.FEE,
    ]
