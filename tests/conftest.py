import os


TEST_ENVIRONMENT = {
    "BOT_TOKEN": "test-token",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "WEBHOOK_URL": "https://example.com/webhook/telegram",
    "WEBHOOK_SECRET": "test-secret",
    "REDIS_HOST": "redis://localhost:6379/15",
    "RABBITMQ_HOST": "memory://",
}

for name, value in TEST_ENVIRONMENT.items():
    os.environ.setdefault(name, value)
