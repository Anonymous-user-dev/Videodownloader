# Telegram Video Downloader Bot

A Telegram bot that downloads videos from YouTube, TikTok, and Instagram and sends them back to the user.

## Features
- Download YouTube (longform, Shorts), TikTok, and Instagram Reels
- Up to 1080p quality with h264 codec
- Concurrent downloads via Celery + RabbitMQ
- User tracking and download history in PostgreSQL
- Redis for caching and state management

## Requirements
- Python 3.14
- PostgreSQL
- Redis
- RabbitMQ
- FFmpeg

## Setup

1. Clone the repo
2. Create a virtual environment and install dependencies:
pip install -r requirements.txt
3. Copy `.env.example` to `.env` and fill in your values:
BOT_TOKEN=your_telegram_bot_token
DATABASE_URL=postgresql+asyncpg://user:password@localhost/dbname
REDIS_HOST=localhost
REDIS_PORT=6379
4. Run migrations:
alembic upgrade head
5. Start the Celery worker:
celery -A services.worker worker --loglevel=info --pool=gevent --concurrency=4
6. Start the bot:
python bot.py