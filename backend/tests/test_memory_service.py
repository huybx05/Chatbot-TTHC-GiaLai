from __future__ import annotations

import asyncio
from uuid import uuid4

from backend.app.memory import service
from backend.app.memory.service import empty_memory, memory_from_history


def test_empty_memory() -> None:
    memory = empty_memory()

    assert memory.summary == ""
    assert memory.recent_turns == []
    assert memory.topics == []
    assert memory.active_procedure is None
    assert memory.is_empty() is True


def test_memory_from_history_giu_dung_thu_tu_va_vai() -> None:
    memory = memory_from_history(
        [
            {"role": "user", "content": "Hồ sơ gồm gì?"},
            {"role": "assistant", "content": "Hồ sơ gồm đơn."},
        ]
    )

    assert [turn.role for turn in memory.recent_turns] == ["user", "assistant"]
    assert memory.recent_turns[0].content == "Hồ sơ gồm gì?"
    assert memory.topics == []
    assert memory.active_procedure is None
    assert memory.is_empty() is False


def test_load_session_memory_khong_tom_tat_truoc_khi_tra_cuu(
    monkeypatch,
) -> None:
    calls: list[str] = []

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

    class FakeEngine:
        def connect(self) -> FakeConnection:
            return FakeConnection()

    async def fake_summary(**_kwargs) -> bool:
        calls.append("summary")
        return False

    monkeypatch.setattr(service, "engine", FakeEngine())
    monkeypatch.setattr(service, "maybe_summarize", fake_summary)
    monkeypatch.setattr(service, "load_session_memory", lambda *_args, **_kwargs: empty_memory())

    memory = asyncio.run(
        service.load_chat_memory(
            user_id=1,
            session_id=uuid4(),
            current_message_id=None,
        )
    )

    assert memory is not None
    assert calls == []
