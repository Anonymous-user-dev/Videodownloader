from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
from telegram import Update
from bot import create_application
from config import settings
import logging
from services.logging_config import configure_logging
from services.health import readiness_report

configure_logging(settings.APP_ENV)

logger = logging.getLogger(__name__)

app = FastAPI()
telegram_app = create_application()


@app.on_event("startup")
async def startup():
    logger.info("Starting webhook bot")

    await telegram_app.initialize()
    await telegram_app.start()

    await telegram_app.bot.set_webhook(
        url=settings.WEBHOOK_URL,
        secret_token=settings.WEBHOOK_SECRET,
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )

    logger.info("Webhook set successfully")


@app.on_event("shutdown")
async def shutdown():
    logger.info("Stopping webhook bot")

    await telegram_app.stop()
    await telegram_app.shutdown()


@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/live")
async def health_live():
    return {"status": "alive"}


@app.get("/health/ready")
async def health_ready():
    report, status_code = await readiness_report()
    return JSONResponse(content=report, status_code=status_code)


@app.post("/webhook/telegram")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    if x_telegram_bot_api_secret_token != settings.WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)

    await telegram_app.process_update(update)

    return {"ok": True}
