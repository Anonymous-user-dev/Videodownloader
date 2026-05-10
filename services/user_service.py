
from sqlalchemy import select
from model import User, Download
from schemas.user import UserCreate
async def get_or_create_user(telegram_user_id, username, db):
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
    download_ob = Download(
        user_id=user_id,
        link=link,
    )
    db.add(download_ob)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()

    user.service_usage += 1

    await db.commit()