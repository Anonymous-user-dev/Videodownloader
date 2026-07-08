# Telegram Video Downloader Bot

A Telegram bot that downloads videos from YouTube, TikTok, and Instagram and sends them back to the user.

## Features
- Download YouTube (longform, Shorts), TikTok, and Instagram Reels
- Up to 1080p quality with h264 codec
- Concurrent downloads via Celery + RabbitMQ
- User tracking and download history in PostgreSQL
- Redis for caching and state management
- Rate limiter for preventing spamming
- Downloading

## Requirements
- Python 3.14
- PostgreSQL
- Redis
- RabbitMQ
- Celery 
- FFmpeg (Optional)

## Setup

1. Clone the repo
2. Create a virtual environment and install dependencies:
pip install -r requirements.txt
3. Copy `.env.example` to `.env` and fill in your values 
4. Run migrations:
alembic upgrade head
5. Start the Celery worker:
celery -A services.worker worker --loglevel=info --pool=gevent --concurrency=4
6. Start the bot:
python bot.py

## Project Flow
When a user sends a video link:
1.  The bot gets the message and quickly replies “Downloading, give me a sec…” so the user knows it’s doing something.
2.  It throws the job into the queue (Celery + RabbitMQ). This lets the bot stay responsive even if multiple people are using it at the same time.
3.  One of the worker processes picks up the task when it’s free. The worker then actually downloads the video using yt-dlp.
4.  After downloading, it checks the file size:
 •  If it’s 45MB or smaller, the worker sends the video straight to the user through Telegram and cleans up the file.
 •  If it’s bigger than 45MB, the worker deletes the big file and tells the user “Video is too heavy, choose a lower quality” and saves the original link temporarily in Redis.
5.  User picks a quality (like 720p). The bot sees that and sends a new download task with the chosen quality.
6.  Once everything is done, the worker cleans up any leftover files and (optionally) saves the download record in the database.