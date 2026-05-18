from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str
    APP_ENV: str = "development"

    REDIS_HOST: str
    REDIS_PORT: int

    RABBITMQ_HOST: str

    model_config = SettingsConfigDict(
        env_file=".env",
        extra='ignore'
    )

settings = Settings()
