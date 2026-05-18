
from celery import Celery
import requests
import os

from config import settings
from services.downloader import download_video
from dependencies.redis import redis_client

app = Celery('tasks', broker=settings.RABBITMQ_HOST)

def send_video_sync(chat_id, file_path, width, height):
    """Sends video to the user"""
    with open(file_path, 'rb') as f:
        requests.post(
            f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendVideo",
            data={'chat_id': chat_id, 'width': width, 'height': height},
            files={'video': f},
            timeout=120
        )
def send_message_sync(chat_id):
    """Sends message to the user asking to reduce video quality"""
    requests.post(
        f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
        data={"chat_id": chat_id, "text": "The video is too large. Reply with 720p or 480p to download in lower quality."},
        timeout=30
    )


@app.task
def video_procedure(url, chat_id, quality=1080):
    file_path, width, height = download_video(url, quality)
    if os.path.getsize(file_path) > 45 * 1024 * 1024:
        os.remove(file_path)
        send_message_sync(chat_id)

        redis_client.set(f"pending_quality:{chat_id}", url, ex=300)
        return

    send_video_sync(chat_id=chat_id, file_path=file_path, width=width, height=height)
    os.remove(file_path)






