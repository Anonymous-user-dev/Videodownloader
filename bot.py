from telegram import Update
from telegram.ext import MessageHandler, CommandHandler, Application, ApplicationBuilder, ContextTypes, filters
from config import settings
import logging
from handlers.download import handle_video_request
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi, send me a video link from Youtube, Instagram, Tiktok.")

def main():
    logging.basicConfig(filename="app.logs", encoding="utf-8", level=logging.DEBUG if settings.APP_ENV == "development" else logging.INFO)
    logger.info("Started")
    application = Application.builder().token(settings.BOT_TOKEN).read_timeout(60).write_timeout(60).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_video_request))
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Finished")

if __name__ == "__main__":
    main()