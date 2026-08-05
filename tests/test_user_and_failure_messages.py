from services.user_service import detect_link_type, normalize_username
from services.worker import download_failure_message, short_request_id


def test_detect_link_type_uses_hostname() -> None:
    assert detect_link_type("https://youtu.be/video") == "youtube"
    assert detect_link_type("https://www.youtube.com/watch?v=video") == "youtube"
    assert detect_link_type("https://www.tiktok.com/@user/video/1") == "tiktok"
    assert detect_link_type("https://www.instagram.com/reel/1/") == "instagram"
    assert detect_link_type("https://example.com/youtube.com") is None


def test_missing_username_gets_stable_database_value() -> None:
    assert normalize_username(None, 12345) == "user_12345"
    assert normalize_username("faridun", 12345) == "faridun"


def test_failure_message_is_safe_and_traceable() -> None:
    request_id = short_request_id("12345678-abcd-efgh")
    message = download_failure_message(request_id)

    assert request_id == "12345678"
    assert "Reference: 12345678" in message
    assert "cookie" not in message.lower()
    assert "traceback" not in message.lower()
