
from sqlalchemy import select
from model import User, Download

async def get_or_create_user(telegram_user_id, username, db):
    """Gets user from database if user already exists, if not, it registers user in DB"""
    result = await db.execute(select(User).where(User.telegram_user_id == telegram_user_id))
    user = result.scalars().first()

    if not user:
        new_user = User(
            telegram_user_id=telegram_user_id,
            username=username,
        )
        db.add(new_user)
        await db.commit()

        return new_user
    return user

async def save_download(user_id, link, db):
    """Saves download records to DB"""
    download_ob = Download(
        user_id=user_id,
        link=link,
    )
    db.add(download_ob)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()

    user.service_usage += 1

    await db.commit()