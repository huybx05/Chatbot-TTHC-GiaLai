"""Cấu hình short-term memory.

Các giá trị này là hợp đồng của plan:
- 3 cặp Q/A gần nhất được đưa vào prompt → 6 message.
- Đủ 10 cặp chưa tóm tắt thì bắt đầu tóm tắt.
- Tóm tắt 8 cặp cũ, giữ nguyên 2 cặp gần nhất.
"""

from backend.app.config import Settings


def test_memory_defaults_match_phase_zero_contract() -> None:
    settings = Settings(_env_file=None)

    assert settings.memory_enabled is True

    # 3 cặp Q/A = 6 message.
    assert settings.memory_recent_messages == 6

    assert settings.memory_summary_trigger_pairs == 10
    assert settings.memory_summary_keep_pairs == 2

    # 10 cặp - 2 cặp giữ lại = 8 cặp được tóm tắt.
    assert (
        settings.memory_summary_trigger_pairs
        - settings.memory_summary_keep_pairs
        == 8
    )

    assert settings.memory_max_chars == 7_000
    assert settings.memory_message_max_chars == 1_200
    assert settings.memory_summary_max_chars == 1_200


def test_rewrite_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.memory_rewrite_enabled is True
    assert settings.memory_rewrite_confidence_min == 0.70
    assert settings.memory_rewrite_max_chars == 600
    assert settings.memory_rewrite_max_attempts == 2
