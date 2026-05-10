import telegram
from telegram import Update
from telegram.ext import MessageHandler, CommandHandler, Application, ApplicationBuilder, ContextTypes, filters
from config import settings
from handlers.download import downloader


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("hi nigga")

def main():
    application = Application.builder().token(settings.BOT_TOKEN).read_timeout(60).write_timeout(60).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, downloader))
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()