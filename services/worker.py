# services/worker.py

from celery import Celery
from celery.signals import setup_logging
import os
import requests
from dependencies.redis_sync import redis_client
import logging
import sys
import time
import traceback

from config import settings
from services.downloader import download_video
from services.video_info import get_video_info, is_tiktok_url

# from services.downloads_slots import release_slot
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
MEMORY_SAFE_QUALITY = 480
MEMORY_SAFE_QUALITY_AFTER_SECONDS = 90
MEMORY_SAFE_MAX_DURATION_SECONDS = 150
MAX_SIZE = 50 * 1024 * 1024


def configure_logging():
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout, force=True)


@setup_logging.connect
def configure_celery_logging(**kwargs):
    configure_logging()


configure_logging()
logger = logging.getLogger(__name__)
app = Celery('tasks', broker=settings.RABBITMQ_HOST)
app.conf.update(
    worker_hijack_root_logger=False,
    worker_redirect_stdouts=True,
    worker_redirect_stdouts_level="INFO",
)


def get_known_file_size(video_info: dict) -> int | None:
    size = video_info.get("filesize") or video_info.get("filesize_approx")
    if size:
        return int(size)

    format_sizes = []
    for item in video_info.get("requested_formats") or video_info.get("formats") or []:
        item_size = item.get("filesize") or item.get("filesize_approx")
        if item_size:
            format_sizes.append(int(item_size))

    return max(format_sizes) if format_sizes else None


def choose_quality(requested_quality: int, video_info: dict | None) -> int:
    quality = min(int(requested_quality), 720)
    if not video_info:
        return min(quality, MEMORY_SAFE_QUALITY)

    duration = video_info.get("duration")
    if duration and duration >= MEMORY_SAFE_QUALITY_AFTER_SECONDS:
        return min(quality, MEMORY_SAFE_QUALITY)
    return quality


def get_worker_video_info(url: str) -> dict | None:
    try:
        video_info = get_video_info(url)
    except Exception as exc:
        if not is_tiktok_url(url):
            raise

        logger.warning(
            "TikTok video info failed in worker; continuing without preflight: %s",
            exc,
            exc_info=True,
        )
        return None

    logger.info(
        "Worker video info: keys=%s extractor=%s id=%s title=%s duration=%s",
        list(video_info.keys()),
        video_info.get("extractor"),
        video_info.get("id"),
        video_info.get("title"),
        video_info.get("duration"),
    )
    return video_info


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


def send_audio_sync(chat_id, file_path):
    """Send audio to Telegram using direct API call"""
    try:
        file_size = os.path.getsize(file_path)
        logger.info(f"Sending audio: {file_path}, Size: {file_size / (1024 * 1024):.2f}MB")

        with open(file_path, 'rb') as f:
            files = {
                'audio': (os.path.basename(file_path), f)
            }

            response = requests.post(
                f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendAudio",
                data={'chat_id': chat_id},
                files=files,
                timeout=160
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('ok'):
                    logger.info(f"Audio sent successfully to chat {chat_id}")
                else:
                    logger.error(f"Telegram API audio error: {result.get('description')}")
                    raise Exception(f"Telegram API audio error: {result.get('description')}")
            else:
                logger.error(f"HTTP audio error: {response.status_code} {response.text}")
                raise Exception(f"HTTP audio error: {response.status_code}")

    except Exception as e:
        logger.error(f"Failed to send audio: {e}")
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
        video_info = get_worker_video_info(url)

        if video_info:
            duration = video_info.get("duration")
            if duration and duration > MEMORY_SAFE_MAX_DURATION_SECONDS:
                logger.info(
                    "Video too long for 512MB worker memory: duration=%ss url=%s",
                    duration,
                    url,
                )
                send_message_sync(
                    chat_id,
                    "❌ This video is too long for the current 512MB server limit.\n\n"
                    "Please send a video around 2 minutes or shorter."
                )
                return

            info_size = get_known_file_size(video_info)
            if info_size and info_size > MAX_SIZE and quality > MEMORY_SAFE_QUALITY:
                logger.info(
                    "Preflight size %.2fMB exceeds Telegram limit; lowering quality to %sp",
                    info_size / (1024 * 1024),
                    MEMORY_SAFE_QUALITY,
                )
                quality = MEMORY_SAFE_QUALITY

        quality = choose_quality(quality, video_info)
        file_path, width, height, media_type = download_video(url, quality)

        if not file_path or not os.path.exists(file_path):
            raise Exception(f"Download failed - file not found")

        size = os.path.getsize(file_path)
        size_mb = size / (1024 * 1024)
        logger.info(f"Final file size: {size_mb:.2f}MB for {quality}p quality")

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


        if media_type == "audio":
            logger.info(f"Sending audio-only TikTok media to chat {chat_id} (Size: {size_mb:.2f}MB)")
            send_audio_sync(chat_id, file_path)
            logger.info("Audio sent successfully")
        else:
            logger.info(f"Sending video to chat {chat_id} (Size: {size_mb:.2f}MB)")
            send_video_sync(chat_id, file_path, width, height)
            logger.info(f"Video sent successfully")

    except Exception as e:
        trace = traceback.format_exc()
        logger.exception("Worker error while processing %s", url)
        print(f"Worker traceback while processing {url}:\n{trace}", flush=True)
        failure_text = str(e)
        if not failure_text.lower().startswith("download failed"):
            failure_text = f"Download failed: {failure_text}"
        send_message_sync(chat_id, f"❌ {failure_text[:600]}")

    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up: {file_path}")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
