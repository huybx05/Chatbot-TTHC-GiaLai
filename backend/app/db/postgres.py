from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.app.config import settings


def _database_url() -> str:
    if settings.database_url:
        return settings.database_url

    return (
        f"postgresql+psycopg://{settings.database_user}:{settings.database_password}"
        f"@{settings.database_host}:{settings.database_port}/{settings.database_db}"
    )


engine: Engine = create_engine(_database_url(), pool_pre_ping=True)