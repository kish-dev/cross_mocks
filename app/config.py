from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    PRIVATE_GROUP_ID: int
    ADMIN_TG_IDS: str = ""
    DATABASE_URL: str
    REDIS_URL: str
    APP_TZ: str = "Europe/Moscow"
    MEETING_PROVIDER: str = "manual"
    DEFAULT_DURATION_MIN: int = 60
    TELEMOST_URL: str = "https://telemost.yandex.ru/"
    GOOGLE_SHEET_ID: str = ""
    GOOGLE_SHEETS_CREDENTIALS_JSON: str = ""
    SHEETS_OUTBOX_PATH: str = "backups/sheets_outbox.jsonl"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
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

    @property
    def admin_ids(self) -> set[int]:
        return {int(x.strip()) for x in self.ADMIN_TG_IDS.split(",") if x.strip()}


settings = Settings()
