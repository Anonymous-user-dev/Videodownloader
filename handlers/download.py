# handlers/download.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from database import SessionLocal
from services.user_service import get_or_create_user, save_download
from telegram.ext import ContextTypes
from dependencies.redis import redis_client
from services.video_info import get_video_info
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

    # get video info to check size
    try:

        logger.info(f"Getting video info for URL: {url}")

        video_info = get_video_info(url)


        logger.info(f"Video info received: {video_info.keys() if video_info else 'None'}")

        if not video_info:
            await update.message.reply_text("❌ Could not fetch video information. Please check the URL and try again.")
            return

        file_size = video_info.get('filesize', 0) or video_info.get('filesize_approx', 0)


        logger.info(f"Video file size: {file_size} bytes ({file_size / (1024 * 1024):.1f}MB)")


        MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

        if file_size > MAX_FILE_SIZE:
            logger.info(f"Video too large ({file_size / (1024 * 1024):.1f}MB), offering quality options")


            quality_data = {
                'url': url,
                'original_size': file_size
            }
            await redis_client.setex(
                f"pending_quality:{chat_id}",
                300,  # 5 minutes expiry
                json.dumps(quality_data)
            )


            sizes = {}
            video_height = video_info.get('height', 1080)
            logger.info(f"Video height: {video_height}")

            for quality in [1080, 720, 480]:
                if quality <= video_height:
                    size_ratio = (quality / video_height) ** 2
                    sizes[quality] = (file_size * size_ratio) / (1024 * 1024)
                    logger.info(f"Estimated size for {quality}p: {sizes[quality]:.1f}MB")

            keyboard = []
            row = []

            if 480 in sizes and sizes[480] < 50:
                row.append(InlineKeyboardButton(f"480p (~{sizes[480]:.0f}MB)", callback_data=f"quality_480_{chat_id}"))
            if 720 in sizes and sizes[720] < 50:
                row.append(InlineKeyboardButton(f"720p (~{sizes[720]:.0f}MB)", callback_data=f"quality_720_{chat_id}"))
            if 1080 in sizes and sizes[1080] < 50:
                row.append(InlineKeyboardButton(f"1080p (~{sizes[1080]:.0f}MB)", callback_data=f"quality_1080_{chat_id}"))

            if row:
                keyboard.append(row)
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    f"⚠️ Video size ({file_size / (1024 * 1024):.1f}MB) exceeds Telegram's 50MB limit.\n\n"
                    f"Please select a quality that will be under 50MB:",
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    f"❌ Video is too large ({file_size / (1024 * 1024):.1f}MB) and no quality options will fit within Telegram's 50MB limit."
                )
            return

        # Video is under 50MB, proceed with download
        logger.info(f"Video under 50MB, proceeding with download")
        await update.message.reply_text(f"📥 Downloading video ({file_size / (1024 * 1024):.1f}MB)...")

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
        error_msg = f"Error checking video: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        await update.message.reply_text(
            f"❌ Error processing video: {str(e)}\n\nPlease make sure the URL is valid and try again.")


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
            await query.edit_message_text("❌ This quality selection is not for this chat.")
            return

        pending_key = f"pending_quality:{chat_id}"
        pending_data = await redis_client.get(pending_key)

        logger.info(f"Pending data from Redis: {pending_data}")

        if not pending_data:
            await query.edit_message_text("❌ Selection expired. Please send the video link again.")
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


        await query.edit_message_text(f"📥 Downloading video in {quality}p quality... Please wait.")

        video_procedure.delay(original_url, chat_id, user_id, quality)
        logger.info(f"Task queued with quality {quality}p for URL: {original_url}")

    except Exception as e:
        error_msg = f"Error in quality callback: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        await update.callback_query.edit_message_text(f"❌ Error: {str(e)}")