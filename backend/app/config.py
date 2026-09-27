"""Application settings loaded from environment variables and ``.env``."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    Secrets are never hard-coded here; they come from the environment.
    ``DATA_ROOT`` points at the raw PDF tree, which lives on Google Drive for
    the full corpus and under ``./data`` for local samples.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    debug: bool = True

    data_root: str = "./data"

    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "tthc"
    postgres_user: str = "tthc"
    postgres_password: str = ""

    elasticsearch_url: str = "http://localhost:9200"

    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""

    base_url: str = ""
    api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()


settings = get_settings()
