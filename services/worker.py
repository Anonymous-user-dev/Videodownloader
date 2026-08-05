from celery import Celery
from celery.signals import setup_logging
import os
import logging
import time

from config import settings
from services.downloader import download_video
from services.errors import (
    DownloadFailedError,
    DurationLimitError,
    FileTooLargeError,
    MissingDownloadedFileError,
    OperationalDownloadError,
)
from services.media_policy import (
    MAX_TELEGRAM_FILE_SIZE,
    MEMORY_SAFE_QUALITY,
    choose_quality,
    format_file_size,
    get_known_file_size,
    is_too_long_for_worker,
    should_lower_quality_for_size,
)
from services.logging_config import configure_logging, log_context, platform_from_url
from services.job_status import DOWNLOADING, FAILED, SENT, STARTED, UPLOADING, update_job_status
from services.telegram_sender import send_audio_sync, send_message_sync, send_video_sync
from services.video_info import get_video_info

logger = logging.getLogger(__name__)


@setup_logging.connect
def configure_celery_logging(**kwargs) -> None:
    configure_logging(settings.APP_ENV)


configure_logging(settings.APP_ENV)

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


def short_request_id(request_id: str | None) -> str:
    if not request_id:
        return "unknown"

    return request_id.split("-")[0]


def download_failure_message(request_id: str) -> str:
    return DownloadFailedError().user_message(request_id)


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
        raise MissingDownloadedFileError("Downloader returned a missing output path")

    size = os.path.getsize(file_path)

    return file_path, width, height, media_type, size


@app.task(rate_limit="6/m", bind=True, max_retries=2)
def video_procedure(self, url, chat_id, user_id, quality=1080):
    request_id = short_request_id(getattr(self.request, "id", None))
    started_at = time.monotonic()

    with log_context(
        request_id=request_id,
        platform=platform_from_url(url),
        user_id=user_id,
        chat_id=chat_id,
        quality=quality,
    ):
        logger.info("Worker started")
        update_job_status(getattr(self.request, "id", ""), STARTED)
        file_path = None

        try:
            video_info = get_worker_video_info(url)
            info_size = None

            if video_info:
                if is_too_long_for_worker(video_info):
                    failure = DurationLimitError()
                    logger.info(
                        "Video rejected because it is too long. duration=%s",
                        video_info.get("duration"),
                    )
                    safe_send_message(chat_id, failure.user_message(request_id))
                    update_job_status(
                        getattr(self.request, "id", ""),
                        FAILED,
                        failure.code,
                    )
                    return

                info_size = get_known_file_size(video_info)

                if should_lower_quality_for_size(video_info, quality):
                    logger.info(
                        "Preflight size is too large. Lowering quality to %sp",
                        MEMORY_SAFE_QUALITY,
                    )
                    quality = MEMORY_SAFE_QUALITY

            quality = choose_quality(quality, video_info)
            send_download_started_message(chat_id, info_size)

            update_job_status(getattr(self.request, "id", ""), DOWNLOADING)
            file_path, width, height, media_type, size = download_and_validate(url, quality)
            size_mb = size / (1024 * 1024)

            logger.info(
                "Download finished. size=%.2fMB media_type=%s",
                size_mb,
                media_type,
                extra={"quality": quality},
            )

            if size > MAX_TELEGRAM_FILE_SIZE:
                logger.warning(
                    "File too large. size=%.2fMB limit=%.2fMB",
                    size_mb,
                    MAX_TELEGRAM_FILE_SIZE / (1024 * 1024),
                    extra={"quality": quality},
                )

                remove_file(file_path)
                file_path = None

                retry_qualities = [720, 480] if quality > 720 else [480]
                retry_qualities = [item for item in retry_qualities if item < quality]

                for lower_quality in retry_qualities:
                    safe_send_message(
                        chat_id,
                        f"File is too large. Retrying at {lower_quality}p...",
                    )
                    logger.info(
                        "Retrying oversized download",
                        extra={"quality": lower_quality},
                    )

                    file_path, width, height, media_type, size = download_and_validate(
                        url, lower_quality
                    )
                    size_mb = size / (1024 * 1024)

                    if size <= MAX_TELEGRAM_FILE_SIZE:
                        quality = lower_quality
                        break

                    logger.warning(
                        "File still too large after retry. size=%.2fMB",
                        size_mb,
                        extra={"quality": lower_quality},
                    )
                    remove_file(file_path)
                    file_path = None
                else:
                    failure = FileTooLargeError(f"Final output size was {size_mb:.1f}MB")
                    safe_send_message(chat_id, failure.user_message(request_id))
                    update_job_status(
                        getattr(self.request, "id", ""),
                        FAILED,
                        failure.code,
                    )
                    return

            update_job_status(getattr(self.request, "id", ""), UPLOADING)
            if media_type == "audio":
                logger.info("Sending audio. size=%.2fMB", size_mb)
                send_audio_sync(chat_id, file_path)
                logger.info("Audio sent successfully")
            else:
                logger.info(
                    "Sending video. size=%.2fMB width=%s height=%s",
                    size_mb,
                    width,
                    height,
                )
                send_video_sync(chat_id, file_path, width, height)
                logger.info("Video sent successfully")

            update_job_status(getattr(self.request, "id", ""), SENT)

        except OperationalDownloadError as exc:
            logger.exception("Worker failed with operational error. error_code=%s", exc.code)
            update_job_status(
                getattr(self.request, "id", ""),
                FAILED,
                exc.code,
            )

            safe_send_message(chat_id, exc.user_message(request_id))

        except Exception:
            logger.exception("Worker failed with unexpected error")
            update_job_status(
                getattr(self.request, "id", ""),
                FAILED,
                DownloadFailedError.code,
            )

            safe_send_message(chat_id, download_failure_message(request_id))

        finally:
            remove_file(file_path)
            logger.info(
                "Worker finished",
                extra={"duration_ms": round((time.monotonic() - started_at) * 1000)},
            )
