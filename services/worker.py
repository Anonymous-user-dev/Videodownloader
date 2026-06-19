# services/worker.py

from celery import Celery
from celery.signals import setup_logging
import os
import logging
import sys
import traceback

from config import settings
from services.downloader import download_video
from services.media_policy import (
    MAX_TELEGRAM_FILE_SIZE,
    MEMORY_SAFE_QUALITY,
    choose_quality,
    format_file_size,
    get_known_file_size,
    is_too_long_for_worker,
    should_lower_quality_for_size,
)
from services.telegram_sender import send_audio_sync, send_message_sync, send_video_sync
from services.video_info import get_video_info, is_tiktok_url

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


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


def send_download_started_message(chat_id, file_size: int | None):
    try:
        if file_size:
            send_message_sync(chat_id, f"📥 Downloading video ({format_file_size(file_size)})...")
        else:
            send_message_sync(chat_id, "📥 Downloading video (size unknown)...")
    except Exception as exc:
        logger.warning("Could not send download started message: %s", exc, exc_info=True)


def send_worker_started_message(chat_id):
    try:
        send_message_sync(chat_id, "📥 Downloading video...")
    except Exception as exc:
        logger.warning("Could not send worker started message: %s", exc, exc_info=True)


@app.task(rate_limit='3/m', bind=True, max_retries=2)
def video_procedure(self, url, chat_id, user_id, quality=1080):
    logger.info(f"Worker start for user {user_id}, requested quality: {quality}p")
    file_path = None

    try:
        send_worker_started_message(chat_id)
        video_info = get_worker_video_info(url)
        info_size = None

        if video_info:
            if is_too_long_for_worker(video_info):
                logger.info(
                    "Video too long for 512MB worker memory: duration=%ss url=%s",
                    video_info.get("duration"),
                    url,
                )
                send_message_sync(
                    chat_id,
                    "❌ This video is too long for the current 512MB server limit.\n\n"
                    "Please send a video around 2 minutes or shorter."
                )
                return

            info_size = get_known_file_size(video_info)
            if should_lower_quality_for_size(video_info, quality):
                logger.info(
                    "Preflight size %.2fMB exceeds Telegram limit; lowering quality to %sp",
                    info_size / (1024 * 1024),
                    MEMORY_SAFE_QUALITY,
                )
                quality = MEMORY_SAFE_QUALITY

        quality = choose_quality(quality, video_info)
        if info_size:
            send_download_started_message(chat_id, info_size)
        file_path, width, height, media_type = download_video(url, quality)

        if not file_path or not os.path.exists(file_path):
            raise Exception(f"Download failed - file not found")

        size = os.path.getsize(file_path)
        size_mb = size / (1024 * 1024)
        logger.info(f"Final file size: {size_mb:.2f}MB for {quality}p quality")

        if size > MAX_TELEGRAM_FILE_SIZE:
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
