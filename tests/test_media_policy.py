from services.media_policy import (
    MAX_TELEGRAM_FILE_SIZE,
    format_file_size,
    get_known_file_size,
    is_too_long_for_worker,
    should_lower_quality_for_size,
)


def test_format_file_size_does_not_claim_zero_megabytes() -> None:
    assert format_file_size(None) == "unknown size"
    assert format_file_size(10 * 1024 * 1024) == "10.0MB"


def test_known_file_size_prefers_top_level_exact_value() -> None:
    info = {"filesize": 123, "formats": [{"filesize": 999}]}
    assert get_known_file_size(info) == 123


def test_known_file_size_uses_largest_available_format_estimate() -> None:
    info = {"formats": [{"filesize": 100}, {"filesize_approx": 300}, {}]}
    assert get_known_file_size(info) == 300


def test_duration_and_size_protection() -> None:
    assert is_too_long_for_worker({"duration": 151})
    assert not is_too_long_for_worker({"duration": 150})
    assert should_lower_quality_for_size(
        {"filesize": MAX_TELEGRAM_FILE_SIZE + 1}, 1080
    )
    assert not should_lower_quality_for_size(
        {"filesize": MAX_TELEGRAM_FILE_SIZE + 1}, 480
    )
