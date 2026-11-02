from __future__ import annotations

from backend.app.memory.topics import derive_topics, merge_topics


def _assistant(
    message_id: str,
    code: str | None,
    name: str = "",
    *,
    status: str = "answered",
    memory_eligible: bool | None = True,
) -> dict:
    metadata: dict = {"status": status}
    if memory_eligible is not None:
        metadata["memory_eligible"] = memory_eligible
    if code:
        metadata["procedure"] = {
            "procedure_code": code,
            "procedure_name": name or code,
        }
    return {
        "id": message_id,
        "role": "assistant",
        "metadata": metadata,
        "created_at": "2026-10-28T00:00:00Z",
    }


def test_derive_topics_theo_thu_tu_xuat_hien() -> None:
    messages = [
        _assistant("m1", "A", "Thủ tục A"),
        _assistant("m2", "B", "Thủ tục B"),
        _assistant("m3", "A", "Thủ tục A"),
    ]

    topics = derive_topics(messages)

    assert [topic.order for topic in topics] == [1, 2]
    assert [topic.procedure_code for topic in topics] == ["A", "B"]
    assert topics[0].first_message_id == "m1"
    assert topics[0].last_message_id == "m3"
    assert topics[1].first_message_id == "m2"


def test_derive_topics_bo_qua_message_khong_co_thu_tuc() -> None:
    topics = derive_topics(
        [
            _assistant("m1", None),
            _assistant("m2", "A", "Thủ tục A"),
        ]
    )

    assert len(topics) == 1
    assert topics[0].procedure_code == "A"


def test_derive_topics_khong_tang_order_khi_lap_lai_thu_tuc() -> None:
    topics = derive_topics(
        [
            _assistant("m1", "A", "Thủ tục A"),
            _assistant("m2", "A", "Thủ tục A"),
            _assistant("m3", "B", "Thủ tục B"),
        ]
    )

    assert [(topic.order, topic.procedure_code) for topic in topics] == [
        (1, "A"),
        (2, "B"),
    ]


def test_derive_topics_bo_qua_abstained_du_co_procedure() -> None:
    topics = derive_topics(
        [
            _assistant("m1", "A", "Thủ tục A", status="abstained"),
            _assistant("m2", "B", "Thủ tục B", status="answered"),
        ]
    )

    assert [topic.procedure_code for topic in topics] == ["B"]


def test_derive_topics_bo_qua_clarify_du_co_procedure() -> None:
    topics = derive_topics(
        [_assistant("m1", "A", "Thủ tục A", status="clarify")]
    )

    assert topics == []


def test_derive_topics_bo_qua_memory_eligible_false() -> None:
    topics = derive_topics(
        [
            _assistant(
                "m1",
                "A",
                "Thủ tục A",
                status="answered",
                memory_eligible=False,
            )
        ]
    )

    assert topics == []


def test_merge_topics_giu_thu_tu_va_cap_nhat_last_message() -> None:
    existing = derive_topics([_assistant("m1", "A", "Thủ tục A")])
    discovered = derive_topics(
        [
            _assistant("m2", "B", "Thủ tục B"),
            _assistant("m3", "A", "Thủ tục A"),
        ]
    )

    merged = merge_topics(existing, discovered)

    assert [topic.order for topic in merged] == [1, 2]
    assert [topic.procedure_code for topic in merged] == ["A", "B"]
    assert merged[0].first_message_id == "m1"
    assert merged[0].last_message_id == "m3"
    assert merged[1].first_message_id == "m2"
