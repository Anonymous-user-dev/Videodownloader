class OperationalDownloadError(RuntimeError):
    code = "download_failed"
    public_message = "The download could not be completed. Please try again later."

    def __init__(self, detail: str | None = None):
        self.detail = detail
        super().__init__(detail or self.code)

    def user_message(self, request_id: str) -> str:
        return f"{self.public_message}\n\nReference: {request_id}"


class PrivateContentError(OperationalDownloadError):
    code = "private_or_unavailable"
    public_message = "This media is private, unavailable, or cannot be accessed."


class PlatformBlockedError(OperationalDownloadError):
    code = "platform_blocked"
    public_message = "The platform temporarily refused this download. Please try again later."


class NoVideoStreamError(OperationalDownloadError):
    code = "no_video_stream"
    public_message = "The platform did not provide a usable video stream for this link."


class NoAudioStreamError(OperationalDownloadError):
    code = "no_audio_stream"
    public_message = "The platform did not provide a usable video with audio for this link."


class QualityTooLowError(OperationalDownloadError):
    code = "quality_too_low"
    public_message = "No acceptable video quality was available for this link."


class FormatUnavailableError(OperationalDownloadError):
    code = "format_unavailable"
    public_message = "The requested video format is temporarily unavailable."


class FileTooLargeError(OperationalDownloadError):
    code = "file_too_large"
    public_message = "This video is too large for the current Telegram upload limit."


class DurationLimitError(OperationalDownloadError):
    code = "duration_limit"
    public_message = "This video is too long for the current server limit."


class MissingDownloadedFileError(OperationalDownloadError):
    code = "missing_downloaded_file"


class DownloadFailedError(OperationalDownloadError):
    pass


def classify_download_error(error: BaseException | None) -> OperationalDownloadError:
    if isinstance(error, OperationalDownloadError):
        return error

    detail = str(error) if error else "unknown download error"
    lowered = detail.lower()

    if "requested format is not available" in lowered or "only images are available" in lowered:
        return FormatUnavailableError(detail)

    if any(
        marker in lowered
        for marker in (
            "private video",
            "private account",
            "login required",
            "sign in",
            "not available",
            "unavailable",
            "cookies for the authentication",
        )
    ):
        return PrivateContentError(detail)

    if any(
        marker in lowered
        for marker in (
            "empty media response",
            "unexpected response",
            "challenge solving failed",
            "temporarily blocked",
            "http error 403",
            "http error 429",
        )
    ):
        return PlatformBlockedError(detail)

    return DownloadFailedError(detail)
