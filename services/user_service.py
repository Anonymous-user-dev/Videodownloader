
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from model import User, Download
import logging

logger = logging.getLogger(__name__)

async def get_or_create_user(telegram_user_id, username, db):
    """Gets user from database if user already exists, if not, it registers user in DB"""
    result = await db.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    user = result.scalars().first()

    if user:
        return user
    try:
        new_user = User(
            telegram_user_id=telegram_user_id,
            username=username,
        )
        db.add(new_user)
        await db.commit()

        return new_user
    except IntegrityError:
        await db.rollback()
        result = await db.execute(select(User).where(User.telegram_user_id == telegram_user_id))

        return result.scalars().first()

async def save_download(user_id, link, db):
    """Saves download records to DB"""
    download_ob = Download(
        user_id=user_id,
        link=link,
    )
    logger.info("Saving download record to DB")
    if "tiktok" in link:
        download_ob.link_type = "tiktok"
    if "instagram" in link:
        download_ob.link_type = "instagram"
    elif "youtube" in link:
        download_ob.link_type = "youtube"
    # Add link type record to db

    db.add(download_ob)

    await db.execute(update(User).where(User.id == user_id).values(service_usage=User.service_usage + 1))
    await db.commit()
    await db.refresh(download_ob)