from app.utils.database_url import normalize_database_url


def test_normalize_postgres_scheme() -> None:
    assert (
        normalize_database_url("postgres://user:pass@db:5432/tgmocks")
        == "postgresql+asyncpg://user:pass@db:5432/tgmocks"
    )


def test_normalize_postgresql_scheme() -> None:
    assert (
        normalize_database_url("postgresql://user:pass@db:5432/tgmocks")
        == "postgresql+asyncpg://user:pass@db:5432/tgmocks"
    )


def test_keep_asyncpg_scheme() -> None:
    assert (
        normalize_database_url("postgresql+asyncpg://user:pass@db:5432/tgmocks")
        == "postgresql+asyncpg://user:pass@db:5432/tgmocks"
    )

