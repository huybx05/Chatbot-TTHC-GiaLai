from backend.app.config import Settings, get_settings


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.app_env == "development"
    assert settings.data_root == "./data"
    assert settings.postgres_port == 5432
    assert settings.postgres_db == "tthc"


def test_settings_read_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("DATA_ROOT", "/content/drive/MyDrive/TTHC_DATA")
    monkeypatch.setenv("BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("API_KEY", "test-key")

    settings = Settings(_env_file=None)

    assert settings.data_root == "/content/drive/MyDrive/TTHC_DATA"
    assert settings.base_url == "https://example.invalid/v1"
    assert settings.api_key == "test-key"


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
