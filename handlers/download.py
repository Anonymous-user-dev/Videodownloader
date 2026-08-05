from telegram import Update
from telegram.ext import ContextTypes
from uuid import uuid4

from database import SessionLocal
from services.user_service import get_or_create_user, mark_download_failed, save_download
from dependencies.redis import redis_client
from services.worker import video_procedure
from services.rate_limit import check_rate_limit
import json
import logging
from services.logging_config import log_context, platform_from_url

logger = logging.getLogger(__name__)


async def queue_download_job(
    url: str,
    chat_id: int,
    telegram_user_id: int,
    username: str | None,
    quality: int = 1080,
) -> str:
    task_id = str(uuid4())

    async with SessionLocal() as db:
        user = await get_or_create_user(
            telegram_user_id=telegram_user_id,
            username=username,
            db=db,
        )
        await save_download(
            user_id=user.id,
            link=url,
            request_id=task_id,
            requested_quality=quality,
            db=db,
        )

    try:
        video_procedure.apply_async(
            args=(url, chat_id, telegram_user_id, quality),
            task_id=task_id,
        )
    except Exception:
        async with SessionLocal() as db:
            await mark_download_failed(task_id, "queue_failed", db)
        raise

    return task_id


async def handle_video_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.message.text is None:
        logger.warning("handle_video_request called without text message")
        return

    if update.effective_chat is None or update.effective_user is None:
        logger.warning("handle_video_request called without chat/user")
        return

    url = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    with log_context(
        platform=platform_from_url(url),
        user_id=user_id,
        chat_id=chat_id,
    ):
        await _queue_video_request(update, url, chat_id, user_id)


async def _queue_video_request(update: Update, url: str, chat_id: int, user_id: int) -> None:
    logger.info("Received video request")

    allowed, retry_after = await check_rate_limit(user_id=user_id)

    if not allowed:
        await update.message.reply_text(f"Rate limited. Retry in {retry_after}s")
        return

    try:
        task_id = await queue_download_job(
            url=url,
            chat_id=chat_id,
            telegram_user_id=user_id,
            username=update.effective_user.username,
        )
        request_id = task_id.split("-")[0]
        with log_context(request_id=request_id):
            logger.info("Video task queued")

        await update.message.reply_text(
            f"Request received. Added to the download queue.\n\nReference: {request_id}"
        )

    except Exception:
        logger.exception("Error queueing video request")

        await update.message.reply_text(
            "Could not process this link. Please check the URL and try again."
        )


async def handle_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    if query is None:
        logger.warning("handle_quality_callback called without callback_query")
        return

    await query.answer()

    try:
        if update.effective_chat is None or update.effective_user is None:
            logger.warning("Callback missing chat/user")
            await query.edit_message_text("Invalid request.")
            return

        data = query.data

        if not data:
            await query.edit_message_text("Invalid selection.")
            return

        parts = data.split("_")

        if len(parts) != 3 or parts[0] != "quality":
            logger.warning("Invalid callback data: %s", data)
            await query.edit_message_text("Invalid selection.")
            return

        try:
            quality = int(parts[1])
            original_chat_id = int(parts[2])
        except ValueError:
            logger.warning("Invalid quality callback numbers: %s", data)
            await query.edit_message_text("Invalid selection.")
            return

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        if chat_id != original_chat_id:
            await query.edit_message_text("This quality selection is not for this chat.")
            return

        pending_key = f"pending_quality:{chat_id}"
        pending_raw = await redis_client.get(pending_key)

        if not pending_raw:
            await query.edit_message_text("Selection expired. Please send the video link again.")
            return

        pending_text = pending_raw.decode() if isinstance(pending_raw, bytes) else pending_raw

        try:
            pending_data = json.loads(pending_text)
        except json.JSONDecodeError:
            logger.exception("Invalid pending quality JSON for key=%s", pending_key)
            await query.edit_message_text("Selection expired. Please send the video link again.")
            return

        original_url = pending_data.get("url")

        if not original_url:
            logger.warning("Pending quality data missing url for key=%s", pending_key)
            await query.edit_message_text("Selection expired. Please send the video link again.")
            return

        await redis_client.delete(pending_key)

        task_id = await queue_download_job(
            url=original_url,
            chat_id=chat_id,
            telegram_user_id=user_id,
            username=update.effective_user.username,
            quality=quality,
        )
        request_id = task_id.split("-")[0]
        with log_context(
            request_id=request_id,
            platform=platform_from_url(original_url),
            user_id=user_id,
            chat_id=chat_id,
            quality=quality,
        ):
            logger.info("Video task queued")

        await query.edit_message_text(
            f"Download queued in {quality}p quality.\n\nReference: {request_id}"
        )

    except Exception:
        logger.exception("Error in quality callback")

        try:
            await query.edit_message_text("Something went wrong. Please try again.")
        except Exception:
            logger.exception("Failed to send callback error message")
