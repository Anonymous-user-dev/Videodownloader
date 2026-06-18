# handlers/download.py

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from database import SessionLocal
from services.user_service import get_or_create_user, save_download
from telegram.ext import ContextTypes
from dependencies.redis import redis_client
from services.video_info import get_video_info
from services.video_info import is_tiktok_url
from services.worker import video_procedure
import json
import logging
import traceback

logger = logging.getLogger(__name__)

MEMORY_SAFE_QUALITY = 480
MEMORY_SAFE_QUALITY_AFTER_SECONDS = 90
MEMORY_SAFE_MAX_DURATION_SECONDS = 150


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


def format_size(size: int | None) -> str:
    if not size:
        return "unknown size"
    return f"{size / (1024 * 1024):.1f}MB"


def get_memory_safe_quality(video_info: dict) -> int:
    duration = video_info.get("duration")
    if duration and duration >= MEMORY_SAFE_QUALITY_AFTER_SECONDS:
        return MEMORY_SAFE_QUALITY
    return 1080


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

        try:
            video_info = get_video_info(url)
        except Exception as e:
            if not is_tiktok_url(url):
                raise

            logger.warning(
                "TikTok video info failed, queueing download without preflight size check: %s",
                e,
                exc_info=True,
            )
            video_info = None


        logger.info(
            "Video info received: keys=%s extractor=%s id=%s title=%s",
            list(video_info.keys()) if video_info else None,
            video_info.get("extractor") if video_info else None,
            video_info.get("id") if video_info else None,
            video_info.get("title") if video_info else None,
        )

        if not video_info:
            if is_tiktok_url(url):
                await update.message.reply_text("📥 Downloading video...")

                async with SessionLocal() as db:
                    user = await get_or_create_user(
                        telegram_user_id=update.effective_user.id,
                        username=update.effective_user.username,
                        db=db
                    )
                    await save_download(user_id=user.id, link=url, db=db)

                video_procedure.delay(url, chat_id, user_id, MEMORY_SAFE_QUALITY)
                logger.info(
                    "Task queued for TikTok URL without video info: %s with quality %sp",
                    url,
                    MEMORY_SAFE_QUALITY,
                )
                return

            await update.message.reply_text("❌ Could not fetch video information. Please check the URL and try again.")
            return

        duration = video_info.get("duration")
        if duration and duration > MEMORY_SAFE_MAX_DURATION_SECONDS:
            logger.info(
                "Video too long for 512MB worker memory: duration=%ss url=%s",
                duration,
                url,
            )
            await update.message.reply_text(
                "❌ This video is too long for the current 512MB server limit.\n\n"
                "Please send a video around 2 minutes or shorter."
            )
            return

        file_size = get_known_file_size(video_info)


        logger.info("Video file size: %s bytes (%s)", file_size, format_size(file_size))


        MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

        if file_size and file_size > MAX_FILE_SIZE:
            logger.info("Video too large (%s), offering quality options", format_size(file_size))


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
        if file_size:
            logger.info("Video under 50MB, proceeding with download")
            await update.message.reply_text(f"📥 Downloading video ({format_size(file_size)})...")
        else:
            logger.info("Video size is unknown, proceeding with download")
            await update.message.reply_text("📥 Downloading video...")

        async with SessionLocal() as db:
            user = await get_or_create_user(
                telegram_user_id=update.effective_user.id,
                username=update.effective_user.username,
                db=db
            )
            await save_download(user_id=user.id, link=url, db=db)


        quality = get_memory_safe_quality(video_info)
        video_procedure.delay(url, chat_id, user_id, quality)
        logger.info(f"Task queued for URL: {url} with quality {quality}p")

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
