import pytest

from services.job_status import (
    DOWNLOADING,
    FAILED,
    QUEUED,
    SENT,
    STARTED,
    TERMINAL_JOB_STATUSES,
    UPLOADING,
    VALID_JOB_STATUSES,
    synchronous_database_url,
    update_job_status,
)


def test_job_lifecycle_statuses_are_complete() -> None:
    assert VALID_JOB_STATUSES == {
        QUEUED,
        STARTED,
        DOWNLOADING,
        UPLOADING,
        SENT,
        FAILED,
    }
    assert TERMINAL_JOB_STATUSES == {SENT, FAILED}


def test_async_postgres_url_is_converted_for_worker_status_writes() -> None:
    assert synchronous_database_url(
        "postgresql+asyncpg://user:pass@host/db"
    ) == "postgresql+psycopg2://user:pass@host/db"


def test_unknown_status_is_rejected_before_database_access() -> None:
    with pytest.raises(ValueError, match="Unknown download status"):
        update_job_status("request-id", "mystery")
