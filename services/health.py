import asyncio
import logging
import shutil
from collections.abc import Awaitable

from kombu import Connection
from sqlalchemy import text

from config import settings
from database import engine
from dependencies.redis import redis_client

logger = logging.getLogger(__name__)

CHECK_TIMEOUT_SECONDS = 3
REQUIRED_BINARIES = ("ffmpeg", "ffprobe", "node")


async def check_database() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def check_redis() -> None:
    if not await redis_client.ping():
        raise RuntimeError("Redis ping returned false")


def _check_rabbitmq_sync() -> None:
    connection = Connection(settings.RABBITMQ_HOST, connect_timeout=CHECK_TIMEOUT_SECONDS)
    try:
        connection.ensure_connection(max_retries=0, timeout=CHECK_TIMEOUT_SECONDS)
    finally:
        connection.release()


async def check_rabbitmq() -> None:
    await asyncio.to_thread(_check_rabbitmq_sync)


async def run_dependency_check(name: str, check: Awaitable[None]) -> tuple[str, bool]:
    try:
        await asyncio.wait_for(check, timeout=CHECK_TIMEOUT_SECONDS)
        return name, True
    except Exception:
        logger.exception("Readiness dependency failed. dependency=%s", name)
        return name, False


def binary_checks() -> dict[str, bool]:
    return {binary: shutil.which(binary) is not None for binary in REQUIRED_BINARIES}


def summarize_checks(checks: dict[str, bool]) -> tuple[dict, int]:
    ready = all(checks.values())
    report = {
        "status": "ready" if ready else "not_ready",
        "checks": {
            name: "ok" if available else "unavailable"
            for name, available in checks.items()
        },
    }
    return report, 200 if ready else 503


async def readiness_report() -> tuple[dict, int]:
    dependency_results = await asyncio.gather(
        run_dependency_check("database", check_database()),
        run_dependency_check("redis", check_redis()),
        run_dependency_check("rabbitmq", check_rabbitmq()),
    )
    checks = dict(dependency_results)
    runtime_binaries = binary_checks()
    checks.update(runtime_binaries)

    for binary, available in runtime_binaries.items():
        if not available:
            logger.error("Required runtime binary is unavailable. binary=%s", binary)

    return summarize_checks(checks)
