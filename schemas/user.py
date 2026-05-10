from pydantic import BaseModel
from sqlalchemy import BigInteger


class UserCreate(BaseModel):
    telegram_id: str
    username: str
