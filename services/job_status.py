import logging
from datetime import datetime, timezone

from sqlalchemy import create_engine, update
from sqlalchemy.exc import SQLAlchemyError

from config import settings
from model import Download

logger = logging.getLogger(__name__)

QUEUED = "queued"
STARTED = "started"
DOWNLOADING = "downloading"
UPLOADING = "uploading"
SENT = "sent"
FAILED = "failed"

VALID_JOB_STATUSES = {QUEUED, STARTED, DOWNLOADING, UPLOADING, SENT, FAILED}
TERMINAL_JOB_STATUSES = {SENT, FAILED}


def synchronous_database_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)


status_engine = create_engine(
    synchronous_database_url(settings.DATABASE_URL),
    pool_pre_ping=True,
    pool_size=1,
    max_overflow=1,
)


def update_job_status(request_id: str, status: str, error_code: str | None = None) -> bool:
    if status not in VALID_JOB_STATUSES:
        raise ValueError(f"Unknown download status: {status}")

    now = datetime.now(timezone.utc)
    values: dict[str, object] = {
        "status": status,
        "error_code": error_code,
        "updated_at": now,
    }

    if status == STARTED:
        values["started_at"] = now
    if status in TERMINAL_JOB_STATUSES:
        values["completed_at"] = now

    try:
        with status_engine.begin() as connection:
            result = connection.execute(
                update(Download)
                .where(Download.request_id == request_id)
                .values(**values)
            )

        if result.rowcount == 0:
            logger.warning("Download job status update matched no record. status=%s", status)
            return False

        logger.info("Download job status changed. status=%s", status)
        return True
    except SQLAlchemyError:
        logger.exception("Could not persist download job status. status=%s", status)
        return False
