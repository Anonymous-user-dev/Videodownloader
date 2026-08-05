import json
import logging
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Iterator
from urllib.parse import urlparse

CONTEXT_FIELDS = (
    "request_id",
    "platform",
    "user_id",
    "chat_id",
    "quality",
    "attempt",
    "duration_ms",
)

_log_context: ContextVar[dict[str, object]] = ContextVar("log_context", default={})


def platform_from_url(url: str) -> str:
    host = urlparse(url).hostname or ""
    host = host.lower()

    if host == "youtu.be" or host.endswith(".youtube.com") or host == "youtube.com":
        return "youtube"
    if host == "tiktok.com" or host.endswith(".tiktok.com"):
        return "tiktok"
    if host == "instagram.com" or host.endswith(".instagram.com"):
        return "instagram"
    return "unknown"


@contextmanager
def log_context(**values: object) -> Iterator[None]:
    current = _log_context.get()
    updated = {**current, **{key: value for key, value in values.items() if value is not None}}
    token = _log_context.set(updated)
    try:
        yield
    finally:
        _log_context.reset(token)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        context = _log_context.get()
        for field in CONTEXT_FIELDS:
            if not hasattr(record, field):
                setattr(record, field, context.get(field))
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for field in CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging(app_env: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(ContextFilter())

    if app_env == "development":
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] "
                "request_id=%(request_id)s platform=%(platform)s %(message)s"
            )
        )
        level = logging.DEBUG
    else:
        handler.setFormatter(JsonFormatter())
        level = logging.INFO

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.INFO)
