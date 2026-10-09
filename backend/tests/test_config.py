"""Test cấu hình: giá trị mặc định và đọc từ biến môi trường.

TÊN BIẾN ở đây là chuẩn của dự án — xem ``.env.example``. Đổi tên biến trong
``config.py`` thì phải đổi cả ``.env``, ``.env.example`` và test này.
"""

from backend.app.config import Settings, get_settings


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.data_root == "./data"
    assert settings.database_host == "localhost"
    assert settings.database_port == 5432
    assert settings.embedding_dim == 1024
    assert settings.reranker_final_k == 5


def test_settings_read_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DATA_ROOT", "/content/drive/MyDrive/TTHC_DATA")
    monkeypatch.setenv("DATABASE_DB", "chatbot_tthc")
    monkeypatch.setenv("QWEN_BASE_URL", "https://example.invalid/compatible-mode/v1")
    monkeypatch.setenv("QWEN_API_KEY", "test-key")
    monkeypatch.setenv("EMBEDDING_DIM", "1536")

    settings = Settings(_env_file=None)

    assert settings.data_root == "/content/drive/MyDrive/TTHC_DATA"
    assert settings.database_db == "chatbot_tthc"
    assert settings.qwen_base_url == "https://example.invalid/compatible-mode/v1"
    assert settings.qwen_api_key == "test-key"
    # số chiều phải ép được từ chuỗi sang int
    assert settings.embedding_dim == 1536


def test_settings_has_every_env_example_key() -> None:
    """Mọi biến trong ``.env.example`` phải có trường tương ứng trong ``Settings``.

    Thiếu trường nghĩa là biến bị bỏ qua âm thầm và code dùng giá trị mặc định.
    """
    from pathlib import Path

    mau = Path(__file__).resolve().parents[2] / ".env.example"
    truong = {t.upper() for t in Settings.model_fields}

    for dong in mau.read_text(encoding="utf-8").splitlines():
        s = dong.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        ten = s.split("=", 1)[0].strip()
        assert ten.upper() in truong, f"{ten} không có trường tương ứng trong Settings"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
