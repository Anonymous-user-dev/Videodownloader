from sqlalchemy import Column, Integer, String, ForeignKey, BigInteger, DateTime, func
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    telegram_user_id = Column(BigInteger, unique=True)
    username = Column(String, nullable=False)
    service_usage = Column(Integer, server_default="0")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Download(Base):
    __tablename__ = "downloads"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True)
    link = Column(String, nullable=False)
    downloaded_at = Column(DateTime(timezone=True), server_default=func.now())