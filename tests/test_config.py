from config import Settings


BASE_SETTINGS = {
    "BOT_TOKEN": "test-token",
    "WEBHOOK_URL": "https://example.com/webhook/telegram",
    "WEBHOOK_SECRET": "test-secret",
    "REDIS_HOST": "redis://localhost:6379/15",
    "RABBITMQ_HOST": "memory://",
}


def test_render_postgres_url_is_normalized_for_async_sqlalchemy() -> None:
    settings = Settings(
        **BASE_SETTINGS,
        DATABASE_URL="postgresql://user:pass@host/database",
    )

    assert settings.DATABASE_URL == "postgresql+asyncpg://user:pass@host/database"


def test_explicit_async_database_driver_is_preserved() -> None:
    settings = Settings(
        **BASE_SETTINGS,
        DATABASE_URL="postgresql+asyncpg://user:pass@host/database",
    )

    assert settings.DATABASE_URL == "postgresql+asyncpg://user:pass@host/database"
