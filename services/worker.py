from celery import Celery
from celery.signals import setup_logging
import os
import logging
import sys

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
from services.video_info import get_video_info

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        stream=sys.stdout,
        force=True,
    )


@setup_logging.connect
def configure_celery_logging(**kwargs) -> None:
    configure_logging()


configure_logging()

app = Celery("tasks", broker=settings.RABBITMQ_HOST)

app.conf.update(
    worker_hijack_root_logger=False,
    worker_redirect_stdouts=True,
    worker_redirect_stdouts_level="INFO",
    worker_prefetch_multiplier=1,
    task_time_limit=300,
    task_soft_time_limit=240,
)


def get_worker_video_info(url: str) -> dict | None:
    try:
        video_info = get_video_info(url)

    except Exception as exc:
        logger.warning(
            "Video info failed in worker; continuing without preflight. url=%s error=%s",
            url,
            exc,
            exc_info=True,
        )
        return None

    logger.info(
        "Worker video info: extractor=%s id=%s title=%s duration=%s",
        video_info.get("extractor"),
        video_info.get("id"),
        video_info.get("title"),
        video_info.get("duration"))

    return video_info


def safe_send_message(chat_id: int, text: str) -> None:
    try:
        send_message_sync(chat_id, text)
    except Exception as exc:
        logger.warning("Could not send Telegram message: %s", exc, exc_info=True)


def send_download_started_message(chat_id: int, file_size: int | None) -> None:
    if file_size:
        safe_send_message(chat_id,f"Downloading video ({format_file_size(file_size)})...")
    else:
        safe_send_message(chat_id, "Downloading video...")


def remove_file(file_path: str | None) -> None:
    if not file_path:
        return

    if not os.path.exists(file_path):
        return

    try:
        os.remove(file_path)
        logger.info("Cleaned up file: %s", file_path)
    except Exception as exc:
        logger.error("Cleanup error for file=%s: %s", file_path, exc, exc_info=True)


def download_and_validate(url: str, quality: int):
    file_path, width, height, media_type = download_video(url, quality)

    if not file_path or not os.path.exists(file_path):
        raise Exception("Download failed - file not found")

    size = os.path.getsize(file_path)

    return file_path, width, height, media_type, size


@app.task(rate_limit="6/m", bind=True, max_retries=2)
def video_procedure(self, url, chat_id, user_id, quality=1080):
    logger.info("Worker started. user_id=%s chat_id=%s requested_quality=%sp",user_id,chat_id,quality)

    file_path = None

    try:
        video_info = get_worker_video_info(url)
        info_size = None

        if video_info:
            if is_too_long_for_worker(video_info):
                logger.info("Video rejected because it is too long. duration=%s user_id=%s",video_info.get("duration"),user_id)

                safe_send_message(chat_id,
                    "This video is too long for the current server limit.\n\n"
                    "Please send a video around 2 minutes or shorter.")
                return

            info_size = get_known_file_size(video_info)

            if should_lower_quality_for_size(video_info, quality):
                logger.info("Preflight size is too large. Lowering quality to %sp",MEMORY_SAFE_QUALITY)
                quality = MEMORY_SAFE_QUALITY

        quality = choose_quality(quality, video_info)

        send_download_started_message(chat_id, info_size)

        file_path, width, height, media_type, size = download_and_validate(url, quality)

        size_mb = size / (1024 * 1024)

        logger.info(
            "Download finished. size=%.2fMB quality=%sp media_type=%s",
            size_mb,
            quality,
            media_type)

        if size > MAX_TELEGRAM_FILE_SIZE:
            logger.warning(
                "File too large. size=%.2fMB limit=%.2fMB quality=%sp",
                size_mb,
                MAX_TELEGRAM_FILE_SIZE / (1024 * 1024),
                quality)

            remove_file(file_path)
            file_path = None

            retry_qualities = [720, 480] if quality > 720 else [480]
            retry_qualities = [item for item in retry_qualities if item < quality]

            for lower_quality in retry_qualities:
                safe_send_message(chat_id,f"File is too large. Retrying at {lower_quality}p...")

                logger.info("Retrying inside same task with quality=%sp", lower_quality)

                file_path, width, height, media_type, size = download_and_validate(url,lower_quality)
                size_mb = size / (1024 * 1024)

                if size <= MAX_TELEGRAM_FILE_SIZE:
                    quality = lower_quality
                    break

                logger.warning("File still too large after retry. size=%.2fMB quality=%sp",size_mb,lower_quality)
                remove_file(file_path)
                file_path = None
            else:
                safe_send_message(chat_id,
                    f"Video is still too large ({size_mb:.1f}MB) even at 480p.\n\n"
                    "Telegram allows a limited file size. Please try a shorter video.")
                return

        if media_type == "audio":
            logger.info("Sending audio. chat_id=%s size=%.2fMB",chat_id,size_mb)

            send_audio_sync(chat_id, file_path)
            logger.info("Audio sent successfully. chat_id=%s", chat_id)

        else:
            logger.info("Sending video. chat_id=%s size=%.2fMB width=%s height=%s",chat_id,size_mb,width,height)

            send_video_sync(chat_id, file_path, width, height)
            logger.info("Video sent successfully. chat_id=%s", chat_id)

    except Exception:
        logger.exception("Worker failed. user_id=%s chat_id=%s quality=%s",user_id,chat_id,quality)

        safe_send_message(chat_id,"Download failed. The link may be unsupported, private, too large, or blocked by the platform.")

    finally:
        remove_file(file_path)
