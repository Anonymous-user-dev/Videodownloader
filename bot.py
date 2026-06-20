from telegram import Update
from telegram.ext import (
    MessageHandler,
    CommandHandler,
    Application,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)
import traceback
from config import settings
from handlers.download import handle_video_request, handle_quality_callback
import logging

logger = logging.getLogger(__name__)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):

    logger.error(
        f"Error: {context.error}\n"
        f"Update: {update}\n"
        f"Traceback: {''.join(traceback.format_exception(type(context.error), context.error, context.error.__traceback__))}"
    )

    if update and update.effective_chat:
        try:
            await update.effective_chat.send_message(
                "Something went wrong. Please try again."
            )
        except Exception:
            pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hi, send me a video link from Youtube, Instagram, Tiktok."
    )


def create_application() -> Application:
    application = (
        Application.builder()
        .token(settings.BOT_TOKEN)
        .read_timeout(60)
        .write_timeout(60)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_quality_callback))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_request)
    )
    application.add_error_handler(error_handler)

    return application