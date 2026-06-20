from pydantic import BaseModel


class UserCreate(BaseModel):
    telegram_id: str
    username: str
