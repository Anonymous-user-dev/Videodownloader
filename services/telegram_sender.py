import logging
import os

import requests

from config import settings

logger = logging.getLogger(__name__)


def send_video_sync(chat_id, file_path, width, height):
    file_size = os.path.getsize(file_path)
    logger.info("Sending video: %s, Size: %.2fMB", file_path, file_size / (1024 * 1024))

    with open(file_path, "rb") as f:
        files = {
            "video": (os.path.basename(file_path), f)
        }
        data = {
            "chat_id": chat_id,
            "width": width,
            "height": height,
            "supports_streaming": True,
        }

        response = requests.post(
            f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendVideo",
            data=data,
            files=files,
            timeout=160,
        )

    if response.status_code != 200:
        logger.error("HTTP video error: %s %s", response.status_code, response.text)
        raise Exception(f"HTTP video error: {response.status_code}")

    result = response.json()
    if not result.get("ok"):
        logger.error("Telegram API video error: %s", result.get("description"))
        raise Exception(f"Telegram API video error: {result.get('description')}")

    logger.info("Video sent successfully to chat %s", chat_id)


def send_audio_sync(chat_id, file_path):
    file_size = os.path.getsize(file_path)
    logger.info("Sending audio: %s, Size: %.2fMB", file_path, file_size / (1024 * 1024))

    with open(file_path, "rb") as f:
        files = {
            "audio": (os.path.basename(file_path), f)
        }

        response = requests.post(
            f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendAudio",
            data={"chat_id": chat_id},
            files=files,
            timeout=160,
        )

    if response.status_code != 200:
        logger.error("HTTP audio error: %s %s", response.status_code, response.text)
        raise Exception(f"HTTP audio error: {response.status_code}")

    result = response.json()
    if not result.get("ok"):
        logger.error("Telegram API audio error: %s", result.get("description"))
        raise Exception(f"Telegram API audio error: {result.get('description')}")

    logger.info("Audio sent successfully to chat %s", chat_id)


def send_message_sync(chat_id, text=None):
    message = text or "⚠️ Video too large (over 45MB). Please try a lower quality (720p or 480p)."

    try:
        response = requests.post(
            f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
            },
            timeout=60,
        )

        if response.status_code == 200:
            logger.info("Message sent to chat %s", chat_id)
        else:
            logger.error("Failed to send message: %s", response.text)

    except Exception as exc:
        logger.error("Error sending message: %s", exc)
