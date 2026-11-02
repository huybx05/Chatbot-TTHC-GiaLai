from __future__ import annotations

from dataclasses import dataclass

from backend.app.workflow.identity import (
    answered_procedure,
    candidates_from_groundings,
    candidates_from_resolution,
    grounded_procedure,
    merge_candidates,
)


def _resolution(**changes):
    data = {
        "code": "A",
        "name": "Thủ tục A",
        "method": "vector",
        "confidence": 0.9,
        "ambiguous": False,
        "alternatives": [],
    }
    data.update(changes)
    return data


@dataclass
class _Grounding:
    type: str = "procedure"
    status: str = "resolved"
    mention: str = "Thủ tục A"
    code: str = "A"
    name: str = "Thủ tục A"
    method: str = "exact_name"
    score: float = 1.0
    alternatives: list | None = None


def test_candidate_tu_resolution_la_gia_thuyet() -> None:
    candidates = candidates_from_resolution(_resolution())

    assert candidates == [
        {
            "code": "A",
            "name": "Thủ tục A",
            "score": 0.9,
            "source": "vector",
            "ambiguous": False,
        }
    ]


def test_candidate_tu_grounding_va_hop_nhat_theo_ma() -> None:
    grounding = _Grounding(
        method="exact_name",
        alternatives=[{"code": "B", "name": "Thủ tục B", "score": 0.7}],
    )
    candidates = merge_candidates(
        candidates_from_resolution(_resolution()),
        candidates_from_groundings([grounding]),
    )

    assert [item["code"] for item in candidates] == ["A", "B"]
    assert candidates[0]["source"] == "exact_name"
    assert candidates[0]["score"] == 1.0


def test_vector_khong_duoc_coi_la_grounded() -> None:
    assert grounded_procedure(_resolution(method="vector"), []) == {}


def test_ma_truc_tiep_duoc_coi_la_grounded() -> None:
    grounded = grounded_procedure(_resolution(method="code"), [])

    assert grounded["code"] == "A"
    assert grounded["source"] == "code"


def test_grounding_resolved_duoc_coi_la_grounded() -> None:
    grounded = grounded_procedure(_resolution(method="vector"), [_Grounding()])

    assert grounded["code"] == "A"
    assert grounded["source"] == "grounding"


def test_answered_chi_co_khi_outcome_answered_va_co_evidence() -> None:
    assert answered_procedure(_resolution(), {}, [], "answered") == {}
    assert answered_procedure(_resolution(), {}, [{"kind": "section"}], "abstained") == {}
    assert answered_procedure(
        _resolution(), {}, [{"kind": "section"}], "answered"
    )["code"] == "A"


def test_answered_uu_tien_grounded_hon_resolution() -> None:
    grounded = {"code": "B", "name": "Thủ tục B", "source": "grounding"}
    answered = answered_procedure(
        _resolution(),
        grounded,
        [{"kind": "section"}],
        "answered",
    )

    assert answered["code"] == "B"
    assert answered["source"] == "grounded"
