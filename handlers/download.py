from telegram import Update
from database import SessionLocal
from services.user_service import get_or_create_user, save_download
from telegram.ext import ContextTypes
from dependencies.redis import redis_client
from services.worker import video_procedure
import logging

logger = logging.getLogger(__name__)

async def handle_video_request(update: Update, context: ContextTypes.DEFAULT_TYPE):

    url = update.message.text
    chat_id = update.effective_chat.id

    pending_url = redis_client.get(f"pending_quality:{chat_id}")

    if pending_url and url in ["720p", "480p", "1080p"]:
        quality = int(url.replace("p", ""))
        redis_client.delete(f"pending_quality:{chat_id}")
        video_procedure.delay(pending_url, chat_id, quality)
        await update.message.reply_text("Downloading in lower quality...")
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

    video_procedure.delay(url, update.effective_chat.id)





