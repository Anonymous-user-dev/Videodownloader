# handlers/download.py

from telegram import Update
from database import SessionLocal
from services.user_service import get_or_create_user, save_download
from telegram.ext import ContextTypes
from dependencies.redis import redis_client
from services.worker import video_procedure
import json
import logging
import traceback

logger = logging.getLogger(__name__)


async def handle_video_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    logger.info(f"Received message from user {user_id}: {url}")

    # Check rate limit
    from services.rate_limit import check_rate_limit
    allowed, retry_after = await check_rate_limit(user_id=user_id)

    if not allowed:
        await update.message.reply_text(f"Rate limited. Retry in {retry_after}s")
        return

    try:
        await update.message.reply_text("Request received. I’ll process it now...")

        async with SessionLocal() as db:
            user = await get_or_create_user(
                telegram_user_id=update.effective_user.id,
                username=update.effective_user.username,
                db=db
            )
            await save_download(user_id=user.id, link=url, db=db)

        video_procedure.delay(url, chat_id, user_id)
        logger.info(f"Task queued for URL: {url}")

    except Exception as e:
        error_msg = f"Error queueing video: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        await update.message.reply_text(
            f"Error processing video: {str(e)}\n\nPlease make sure the URL is valid and try again.")


async def handle_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quality selection from inline keyboard"""
    try:
        query = update.callback_query
        await query.answer()

        logger.info(f"Callback received: {query.data}")

        data = query.data
        parts = data.split('_')
        quality = int(parts[1])
        original_chat_id = int(parts[2])

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        logger.info(f"Quality selected: {quality}p for chat {chat_id}")

        if chat_id != original_chat_id:
            await query.edit_message_text("This quality selection is not for this chat.")
            return

        pending_key = f"pending_quality:{chat_id}"
        pending_data = await redis_client.get(pending_key)

        logger.info(f"Pending data from Redis: {pending_data}")

        if not pending_data:
            await query.edit_message_text("Selection expired. Please send the video link again.")
            return

        pending_data = json.loads(pending_data.decode() if isinstance(pending_data, bytes) else pending_data)
        original_url = pending_data['url']

        logger.info(f"Original URL from pending data: {original_url}")

        # Clean up Redis
        await redis_client.delete(pending_key)


        async with SessionLocal() as db:
            user = await get_or_create_user(
                telegram_user_id=user_id,
                username=update.effective_user.username,
                db=db
            )
            await save_download(user_id=user.id, link=original_url, db=db)


        await query.edit_message_text(f"Downloading video in {quality}p quality... Please wait.")

        video_procedure.delay(original_url, chat_id, user_id, quality)
        logger.info(f"Task queued with quality {quality}p for URL: {original_url}")

    except Exception as e:
        error_msg = f"Error in quality callback: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        await update.callback_query.edit_message_text(f"Error: {str(e)}")
