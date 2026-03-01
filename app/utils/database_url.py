def normalize_database_url(value: str) -> str:
    if not isinstance(value, str):
        return value
    scheme, sep, rest = value.partition("://")
    if not sep:
        return value
    if scheme == "postgres":
        scheme = "postgresql"
    if scheme == "postgresql":
        scheme = "postgresql+asyncpg"
    return f"{scheme}://{rest}"

