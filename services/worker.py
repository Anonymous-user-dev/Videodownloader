from celery import Celery
import os
import requests
import asyncio
import logging

from config import settings
from services.downloader import download_video
from services.downloads_slots import release_slot
logger = logging.getLogger(__name__)
app = Celery('tasks', broker=settings.RABBITMQ_HOST)


def send_video_sync(chat_id, file_path, width, height):
    with open(file_path, 'rb') as f:
        requests.post(
            f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendVideo",
            data={'chat_id': chat_id, 'width': width, 'height': height},
            files={'video': f},
            timeout=120
        )


def send_message_sync(chat_id):
    requests.post(
        f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": "Video too large. Try 720p or 480p."
        },
        timeout=30
    )


@app.task(rate_limit='3/m')
def video_procedure(url, chat_id, user_id, quality=1080):
    logger.info(f"Worker start: {user_id}")
    file_path = None

    try:
        file_path, width, height = download_video(url, quality)

        size = os.path.getsize(file_path)

        if size > 45 * 1024 * 1024:
            os.remove(file_path)
            send_message_sync(chat_id)
            return

        send_video_sync(chat_id, file_path, width, height)

    except Exception as e:
        logger.error(f"Worker error: {e}")

    finally:

        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except:
                pass

        release_slot(user_id)