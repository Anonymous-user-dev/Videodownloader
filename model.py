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
    link_type = Column(String, nullable=True)
    request_id = Column(String(36), unique=True, index=True, nullable=True)
    status = Column(String(20), nullable=False, server_default="queued", index=True)
    requested_quality = Column(Integer, nullable=False, server_default="1080")
    error_code = Column(String(50), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    downloaded_at = Column(DateTime(timezone=True), server_default=func.now())
