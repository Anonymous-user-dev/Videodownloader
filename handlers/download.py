# handlers/download.py

from telegram import Update
from database import SessionLocal
from services.user_service import get_or_create_user, save_download
from telegram.ext import ContextTypes
from dependencies.redis import redis_client
from services.worker import video_procedure
import json
from services.video_info import is_valid_url
import logging
import traceback

logger = logging.getLogger(__name__)


async def handle_video_request(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.message is None or update.message.text is None:
        return

    url = update.message.text.strip()

    if not is_valid_url(url):
        await update.message.reply_text("Please send a valid URL starting with http:// or https://")
        return

    chat_id = update.effective_chat.id if update.effective_chat else None
    user_id = update.effective_user.id if update.effective_user else None

    logger.info("Received video request from user_id=%s", user_id)

    # Check rate limit
    from services.rate_limit import check_rate_limit
    allowed, retry_after = await check_rate_limit(user_id=user_id)

    if not allowed:
        await update.message.reply_text(f"Rate limited. Retry in {retry_after}s")
        return

    try:
        await update.message.reply_text("Request received. Preparing download...")

        async with SessionLocal() as db:
            user = await get_or_create_user(
                telegram_user_id=update.effective_user.id,
                username=update.effective_user.username,
                db=db
            )
            await save_download(user_id=user.id, link=url, db=db)

        video_procedure.delay(url, chat_id, user_id)

    except Exception as e:
        logger.exception("Error quering video")
        await update.message.reply_text("Could not process this link. Please make sure the URL is valid and try again.")


async def handle_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle quality selection from inline keyboard"""
    try:

        if update.callback_query is None:
            return

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

        logger.info("Pending data exists=%s for key=%s", bool(pending_data), pending_key)

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
        logger.exception("Error in quality callback")
        if update.callback_query:
            await update.callback_query.edit_message_text("Something went wrong. Please try again.")