from urllib.parse import urlparse

import logging

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from model import User, Download

logger = logging.getLogger(__name__)


def normalize_username(username, telegram_user_id):
    return username or f"user_{telegram_user_id}"


def detect_link_type(link: str) -> str | None:
    host = urlparse(link).netloc.lower()

    if "tiktok.com" in host:
        return "tiktok"
    if "instagram.com" in host:
        return "instagram"
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"

    return None


async def get_or_create_user(telegram_user_id, username, db):
    """Gets user from database if user already exists, if not, it registers user in DB"""
    result = await db.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    user = result.scalars().first()

    if user:
        return user
    try:
        new_user = User(
            telegram_user_id=telegram_user_id,
            username=normalize_username(username, telegram_user_id),
        )
        db.add(new_user)
        await db.commit()

        return new_user
    except IntegrityError:
        await db.rollback()
        result = await db.execute(select(User).where(User.telegram_user_id == telegram_user_id))

        return result.scalars().first()

async def save_download(
    user_id,
    link,
    db,
    request_id: str | None = None,
    requested_quality: int = 1080,
):
    """Saves download records to DB"""
    download_ob = Download(
        user_id=user_id,
        link=link,
        request_id=request_id,
        requested_quality=requested_quality,
    )
    logger.info("Saving download record to DB")
    download_ob.link_type = detect_link_type(link)

    db.add(download_ob)

    await db.execute(update(User).where(User.id == user_id).values(service_usage=User.service_usage + 1))
    await db.commit()
    await db.refresh(download_ob)

    return download_ob


async def mark_download_failed(request_id: str, error_code: str, db) -> None:
    await db.execute(
        update(Download)
        .where(Download.request_id == request_id)
        .values(status="failed", error_code=error_code, updated_at=func.now())
    )
    await db.commit()
