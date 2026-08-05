import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 5

    WEBHOOK_URL: str
    WEBHOOK_SECRET: str

    YOUTUBE_COOKIES_PATH: str | None = None
    TIKTOK_COOKIES_PATH: str | None = None
    INSTAGRAM_COOKIES_PATH: str | None = None
    YTDLP_COOKIES_PATH: str | None = None

    APP_ENV: str = "development"

    REDIS_HOST: str
    RABBITMQ_HOST: str

    LIMIT: int = 5
    WINDOW_SEC: int = 60

    @field_validator("DATABASE_URL")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

    @field_validator("WEBHOOK_SECRET")
    @classmethod
    def validate_webhook_secret(cls, value: str) -> str:
        cleaned = value.strip().strip('"').strip("'")

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", cleaned):
            raise ValueError(
                "WEBHOOK_SECRET must only contain letters, numbers, underscores, or hyphens"
            )

        return cleaned

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
