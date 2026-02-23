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

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def admin_ids(self) -> set[int]:
        return {int(x.strip()) for x in self.ADMIN_TG_IDS.split(",") if x.strip()}


settings = Settings()
