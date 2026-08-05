import json
import logging

from services.logging_config import ContextFilter, JsonFormatter, log_context, platform_from_url


def test_platform_from_url_does_not_match_path_text() -> None:
    assert platform_from_url("https://youtu.be/abc") == "youtube"
    assert platform_from_url("https://example.com/tiktok.com/video") == "unknown"


def test_json_formatter_includes_bound_context() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "done", (), None)

    with log_context(request_id="abc123", platform="youtube", quality=720):
        ContextFilter().filter(record)
        payload = json.loads(JsonFormatter().format(record))

    assert payload["message"] == "done"
    assert payload["request_id"] == "abc123"
    assert payload["platform"] == "youtube"
    assert payload["quality"] == 720
