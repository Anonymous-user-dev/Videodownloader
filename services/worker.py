# services/worker.py

from celery import Celery
import os
import requests
from dependencies.redis_sync import redis_client
import logging
import time

from config import settings
from services.downloader import download_video

# from services.downloads_slots import release_slot
logger = logging.getLogger(__name__)
app = Celery('tasks', broker=settings.RABBITMQ_HOST)


def send_video_sync(chat_id, file_path, width, height):
    """Send video to Telegram using direct API call"""
    try:
        file_size = os.path.getsize(file_path)
        logger.info(f"Sending video: {file_path}, Size: {file_size / (1024 * 1024):.2f}MB")

        with open(file_path, 'rb') as f:
            files = {
                'video': (os.path.basename(file_path), f)
            }

            data = {
                'chat_id': chat_id,
                'width': width,
                'height': height,
                'supports_streaming': True
            }

            response = requests.post(
                f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendVideo",
                data=data,
                files=files,
                timeout=160
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    logger.info(f"Video sent successfully to chat {chat_id}")
                else:
                    logger.error(f"Telegram API error: {result.get('description')}")
                    raise Exception(f"Telegram API error: {result.get('description')}")
            else:
                logger.error(f"HTTP error: {response.status_code}")
                raise Exception(f"HTTP error: {response.status_code}")

    except Exception as e:
        logger.error(f"Failed to send video: {e}")
        raise


def send_message_sync(chat_id, text=None):
    """Send text message to Telegram"""
    try:
        message = text or "⚠️ Video too large (over 45MB). Please try a lower quality (720p or 480p)."

        response = requests.post(
            f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML"
            },
            timeout=60
        )

        if response.status_code == 200:
            logger.info(f"Message sent to chat {chat_id}")
        else:
            logger.error(f"Failed to send message: {response.text}")

    except Exception as e:
        logger.error(f"Error sending message: {e}")


# def send_quality_options_sync(chat_id, original_url):
#     """Send quality selection options when video is too large"""
#     try:
#         # Store the URL in Redis with short expiry
#         import json
#         redis_client.setex(
#             f"pending_quality:{chat_id}",
#             300,
#             json.dumps({'url': original_url})
#         )
#
#         # Create inline keyboard markup
#         keyboard = {
#             "inline_keyboard": [
#                 [
#                     {"text": "720p", "callback_data": f"quality_720_{chat_id}"},
#                     {"text": "480p", "callback_data": f"quality_480_{chat_id}"}
#                 ]
#             ]
#         }
#
#         response = requests.post(
#             f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage",
#             json={
#                 "chat_id": chat_id,
#                 "text": "⚠️ Video is too large (over 45MB). Please select a lower quality:",
#                 "reply_markup": keyboard
#             },
#             timeout=60
#         )
#
#         if response.status_code == 200:
#             logger.info(f"Quality options sent to chat {chat_id}")
#         else:
#             logger.error(f"Failed to send quality options: {response.text}")
#
#     except Exception as e:
#         logger.error(f"Error sending quality options: {e}")


# services/worker.py - Update the size check

@app.task(rate_limit='3/m', bind=True, max_retries=2)
def video_procedure(self, url, chat_id, user_id, quality=1080):
    logger.info(f"Worker start for user {user_id}, requested quality: {quality}p")
    file_path = None

    try:
        file_path, width, height = download_video(url, quality)

        if not file_path or not os.path.exists(file_path):
            raise Exception(f"Download failed - file not found")

        size = os.path.getsize(file_path)
        size_mb = size / (1024 * 1024)
        logger.info(f"Final file size: {size_mb:.2f}MB for {quality}p quality")

        MAX_SIZE = 50 * 1024 * 1024  # Telegram limit is 50MB, use 50MB

        if size > MAX_SIZE:
            logger.warning(f"Video too large: {size_mb:.2f}MB > 50MB")


            if os.path.exists(file_path):
                os.remove(file_path)


            if quality > 480:
                lower_quality = 480
                logger.info(f"Retrying with lower quality: {lower_quality}p")

                video_procedure.delay(url, chat_id, user_id, lower_quality)
                return
            else:

                send_message_sync(chat_id,
                                  f"❌ Video is still too large ({size_mb:.1f}MB) even at 480p.\n\nTelegram allows maximum 50MB. Please try a different video.")
                return


        logger.info(f"Sending video to chat {chat_id} (Size: {size_mb:.2f}MB)")
        send_video_sync(chat_id, file_path, width, height)
        logger.info(f"Video sent successfully")

    except Exception as e:
        logger.error(f"Worker error: {e}", exc_info=True)
        send_message_sync(chat_id, f"❌ Download failed: {str(e)[:200]}")

    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up: {file_path}")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
