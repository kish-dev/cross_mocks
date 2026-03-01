import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.config import Settings


def _build_settings(database_url: str) -> Settings:
    return Settings(
        BOT_TOKEN="123:ABC",
        PRIVATE_GROUP_ID=-1000000000001,
        ADMIN_TG_IDS="1,2",
        DATABASE_URL=database_url,
        REDIS_URL="redis://localhost:6379/0",
    )


def test_database_url_normalizes_postgres_scheme() -> None:
    settings = _build_settings("postgres://user:pass@db:5432/tgmocks")
    assert settings.DATABASE_URL == "postgresql+asyncpg://user:pass@db:5432/tgmocks"


def test_database_url_normalizes_postgresql_scheme() -> None:
    settings = _build_settings("postgresql://user:pass@db:5432/tgmocks")
    assert settings.DATABASE_URL == "postgresql+asyncpg://user:pass@db:5432/tgmocks"


def test_database_url_keeps_asyncpg_scheme() -> None:
    settings = _build_settings("postgresql+asyncpg://user:pass@db:5432/tgmocks")
    assert settings.DATABASE_URL == "postgresql+asyncpg://user:pass@db:5432/tgmocks"
