from telegram import Update
from database import SessionLocal
from services.user_service import get_or_create_user, save_download
from telegram.ext import ContextTypes
from dependencies.redis import redis_client
from services.video_info import get_video_info
from services.worker import video_procedure

import logging
# from services.downloads_slots import acquire_slot
from services.rate_limit import check_rate_limit

logger = logging.getLogger(__name__)


async def handle_video_request(update: Update, context: ContextTypes.DEFAULT_TYPE):

    url = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    logger.info(f"Received message: {url}")
    allowed, retry_after = await check_rate_limit(user_id=user_id)

    if not allowed:
        await update.message.reply_text(f"Rate limited. Retry in {retry_after}s")
        return

    # slot = acquire_slot(user_id)

    # try:
    #     get_video_info(url)
    # except Exception as e:
    #     await update.message.reply_text(str(e))
    #     return

    # if not slot:
    #     await update.message.reply_text("Too many active downloads. Wait for current ones to finish")
    #     return


    pending_url = redis_client.get(f"pending_quality:{chat_id}")
    logger.info(f"Pending url: {pending_url}")

    if pending_url:
        pending_url = pending_url.decode() if isinstance(pending_url, bytes) else pending_url

    if pending_url and url in ["720p", "480p", "1080p"]:
        quality = int(url.replace("p", ""))
        await redis_client.delete(f"pending_quality:{chat_id}")
        video_procedure.delay(str(pending_url), chat_id, user_id, quality)
        await update.message.reply_text("Downloading in lower quality...")
        return
    try:
        get_video_info(url)
    except Exception as e:
        await update.message.reply_text(str(e))
        return

    await update.message.reply_text("Downloading video. Please wait...")
    url = update.message.text


    async with SessionLocal() as db:
        user = await get_or_create_user(
            telegram_user_id=update.effective_user.id,
            username=update.effective_user.username,
            db=db
        )
        await save_download(user_id=user.id, link=url, db=db)
    logger.info(f"Sending task to Celery: {url}")
    video_procedure.delay(url, chat_id, user_id)
    await update.message.reply_text("Task queued. Downloading...")




