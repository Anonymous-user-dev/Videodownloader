from celery import Celery
import os
import requests
from dependencies.redis_sync import redis_client
import logging

from config import settings
from services.downloader import download_video
# from services.downloads_slots import release_slot
logger = logging.getLogger(__name__)
app = Celery('tasks', broker=settings.RABBITMQ_HOST)


def send_video_sync(chat_id, file_path, width, height):
    with open(file_path, 'rb') as f:
        requests.post(
            f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendVideo",
            data={'chat_id': chat_id, 'width': width, 'height': height},
            files={'video': f},
            timeout=160
        )


def send_message_sync(chat_id):
    requests.post(
        f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
        data={
            "chat_id": chat_id,
            "text": "Video too large. Try 720p or 480p."
        },
        timeout=60
    )


@app.task(rate_limit='3/m')
def video_procedure(url, chat_id, user_id, quality=1080):
    logger.info(f"Worker start: {user_id}")
    file_path = None

    if isinstance(url, bytes):
        url = url.decode()

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
        if file_path:
            try:
                file_path = os.path.abspath(file_path)

                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Deleted file: {file_path}")
                else:
                    logger.warning(f"File not found for deletion: {file_path}")

            except Exception as e:
                logger.error(f"Failed to delete file: {e}")

        # release_slot(user_id)