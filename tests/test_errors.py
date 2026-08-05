from services.errors import (
    DownloadFailedError,
    FormatUnavailableError,
    NoAudioStreamError,
    PlatformBlockedError,
    PrivateContentError,
    classify_download_error,
)


def test_external_errors_are_classified_into_stable_codes() -> None:
    assert isinstance(
        classify_download_error(Exception("Instagram sent an empty media response")),
        PlatformBlockedError,
    )
    assert isinstance(
        classify_download_error(Exception("Login required; use cookies for the authentication")),
        PrivateContentError,
    )
    assert isinstance(
        classify_download_error(Exception("Requested format is not available")),
        FormatUnavailableError,
    )


def test_typed_error_survives_classification() -> None:
    original = NoAudioStreamError("internal ffprobe detail")
    assert classify_download_error(original) is original


def test_public_message_never_contains_internal_detail() -> None:
    error = PrivateContentError("cookiefile=/etc/secrets/instagram.txt sessionid=secret")
    message = error.user_message("abc123")

    assert "abc123" in message
    assert "cookiefile" not in message
    assert "sessionid" not in message
    assert "secret" not in message


def test_unknown_failure_has_generic_public_message() -> None:
    error = classify_download_error(Exception("internal implementation exploded"))

    assert isinstance(error, DownloadFailedError)
    assert error.code == "download_failed"
