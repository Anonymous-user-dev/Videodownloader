import yt_dlp
import os
import uuid
import logging
import time
from pathlib import Path
from services.media_probe import has_audio_stream, is_audio_file, probe_video
from services.logging_config import log_context
from services.platform_policy import (
    build_format,
    build_social_format,
    build_youtube_format,
    get_platform_policy,
    minimum_acceptable_resolution,
    normalize_url,
)
from services.tiktok_direct import download_tiktok_video_direct
from services.ytdlp_cookies import get_cookie_path

logger = logging.getLogger(__name__)

# BASE_DIR = Path(__file__).resolve().parent.parent
# DEFAULT_COOKIE_PATH = BASE_DIR / "cookies.txt"

DOWNLOAD_DIR = Path(os.getcwd()) / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


class DownloadFailedError(RuntimeError):
    pass


class YtdlpLogBridge:
    def debug(self, message):
        logger.debug("yt-dlp: %s", message)

    def warning(self, message):
        logger.warning("yt-dlp: %s", message)

    def error(self, message):
        logger.error("yt-dlp: %s", message)


def base_options(
    url: str,
    quality: int,
    unique_id: str,
    attempt: int = 1,
    use_cookies: bool = True,
):
    policy = get_platform_policy(url)
    options = {
        "outtmpl": str(DOWNLOAD_DIR / f"%(title)s_{unique_id}.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": False,
        "noplaylist": True,
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 1,
        "postprocessor_args": ["-movflags", "+faststart"],
        "format": build_format(url, quality),
        "logger": YtdlpLogBridge(),
        "js_runtimes": {
            "node": {},
        },
        "remote_components": ["ejs:github"],
    }

    cookie_path = get_cookie_path(url) if use_cookies else None
    if cookie_path:
        options["cookiefile"] = cookie_path
        logger.info("Using yt-dlp cookies from: %s", cookie_path)
    elif not use_cookies:
        logger.info("Skipping yt-dlp cookies for this attempt")
    else:
        logger.warning("No yt-dlp cookies are being used")

    if policy.requires_video_and_audio:
        options["format_sort"] = [f"res:{quality}", "fps", "tbr", "filesize", "ext:mp4:m4a"]
        options["format_sort_force"] = True

    options.update(policy.ytdlp_options(quality, attempt))

    return options


def find_downloaded_file(info: dict, ydl: yt_dlp.YoutubeDL) -> str | None:
    requested_path = ydl.prepare_filename(info)
    base_path = os.path.splitext(requested_path)[0]
    possible_paths = [
        requested_path,
        base_path + ".mp4",
        base_path + ".webm",
        base_path + ".mkv",
        base_path + ".mov",
    ]

    requested_downloads = info.get("requested_downloads") or []
    possible_paths.extend(
        download.get("filepath")
        for download in requested_downloads
        if download.get("filepath")
    )

    return next((path for path in possible_paths if path and os.path.exists(path)), None)


def try_tiktok_direct_video(url: str, unique_id: str) -> tuple[str, int, int] | None:
    output_path = DOWNLOAD_DIR / f"tiktok_direct_{unique_id}.mp4"
    try:
        video_path = download_tiktok_video_direct(url, output_path)
        has_video, width, height, codec = probe_video(video_path)
        if not has_video:
            raise RuntimeError(f"TikTok direct fallback returned no video stream: {video_path}")

        logger.info(
            "TikTok direct fallback succeeded | file=%s | codec=%s | size=%sx%s",
            video_path,
            codec,
            width,
            height,
        )
        return video_path, width, height
    except Exception as exc:
        logger.warning("TikTok direct fallback failed for %s: %s", url, exc, exc_info=True)
        try:
            output_path.unlink(missing_ok=True)
        except Exception as cleanup_exc:
            logger.warning("Could not clean failed TikTok direct file %s: %s", output_path, cleanup_exc)
        return None


def build_quality_ladder(requested_quality: int) -> list[int]:
    requested_quality = min(int(requested_quality), 1080)
    ladder = [requested_quality, 720, 480]
    return list(dict.fromkeys(quality for quality in ladder if quality <= requested_quality))


def visible_resolution(width: int | None, height: int | None) -> int:
    if not width or not height:
        return 0
    return min(width, height)


def is_video_quality_too_low(target_quality: int, width: int | None, height: int | None) -> bool:
    minimum_resolution = minimum_acceptable_resolution(target_quality)
    if not minimum_resolution:
        return False
    return visible_resolution(width, height) < minimum_resolution


def download_video(url: str, quality: int = 1080):
    url = normalize_url(url)
    policy = get_platform_policy(url)
    quality = min(int(quality), 1080)
    unique_id = str(uuid.uuid4())[:8]

    logger.info("Starting download")

    last_error = None
    quality_ladder = build_quality_ladder(quality)

    for attempt, attempt_quality in enumerate(quality_ladder, start=1):
        attempt_started_at = time.monotonic()
        try:
            with log_context(quality=attempt_quality, attempt=attempt):
                options = base_options(
                    url,
                    attempt_quality,
                    unique_id,
                    attempt=attempt,
                    use_cookies=policy.use_cookies(attempt),
                )

                with yt_dlp.YoutubeDL(options) as ydl:
                    logger.info("Download attempt started")

                    info = ydl.extract_info(url, download=True)

                    file_path = find_downloaded_file(info, ydl)

                if not file_path:
                    raise FileNotFoundError(f"Missing downloaded file for: {url}")

                has_video, probed_width, probed_height, codec = probe_video(file_path)
                if not has_video:
                    if is_audio_file(file_path):
                        if policy.name == "tiktok":
                            direct_result = try_tiktok_direct_video(url, unique_id)
                            if direct_result:
                                video_path, width, height = direct_result
                                if is_video_quality_too_low(attempt_quality, width, height):
                                    try:
                                        Path(video_path).unlink(missing_ok=True)
                                    except Exception as cleanup_exc:
                                        logger.warning("Could not clean low-quality TikTok direct file %s: %s", video_path, cleanup_exc)
                                    raise RuntimeError(
                                        f"TikTok direct fallback is only {width}x{height} for target {attempt_quality}p"
                                    )

                                try:
                                    Path(file_path).unlink(missing_ok=True)
                                except Exception as cleanup_exc:
                                    logger.warning("Could not clean yt-dlp audio fallback %s: %s", file_path, cleanup_exc)
                                return video_path, width, height, "video"

                        if policy.requires_video_and_audio:
                            try:
                                Path(file_path).unlink(missing_ok=True)
                            except Exception as cleanup_exc:
                                logger.warning("Could not clean audio-only video-platform file %s: %s", file_path, cleanup_exc)
                            raise RuntimeError(f"Audio-only download selected for video URL: {url}")

                        logger.info("Downloaded audio-only media: %s", file_path)
                        return file_path, 0, 0, "audio"
                    raise RuntimeError(f"Downloaded file has no video stream: {file_path}")

                if policy.requires_video_and_audio and not has_audio_stream(file_path):
                    try:
                        Path(file_path).unlink(missing_ok=True)
                    except Exception as cleanup_exc:
                        logger.warning("Could not clean muted video-platform file %s: %s", file_path, cleanup_exc)
                    raise RuntimeError(f"Downloaded video has no audio stream: {url}")

                width = info.get("width") or probed_width
                height = info.get("height") or probed_height

                if policy.requires_video_and_audio and is_video_quality_too_low(
                    attempt_quality, width, height
                ):
                    try:
                        Path(file_path).unlink(missing_ok=True)
                    except Exception as cleanup_exc:
                        logger.warning("Could not clean low-quality file %s: %s", file_path, cleanup_exc)
                    raise RuntimeError(
                        f"Downloaded video is only {width}x{height} for target {attempt_quality}p"
                    )

                logger.info(
                    "Download attempt succeeded. codec=%s size=%sx%s",
                    codec,
                    width,
                    height,
                    extra={"duration_ms": round((time.monotonic() - attempt_started_at) * 1000)},
                )

                return file_path, width, height, "video"

        except Exception as e:
            last_error = e
            logger.warning(
                "Download attempt failed: %s",
                e,
                exc_info=True,
                extra={
                    "attempt": attempt,
                    "quality": attempt_quality,
                    "duration_ms": round((time.monotonic() - attempt_started_at) * 1000),
                },
            )
            time.sleep(2 * attempt)

    error_detail = str(last_error) if last_error else "unknown error"
    exc_info = (type(last_error), last_error, last_error.__traceback__) if last_error else None
    logger.error("All attempts failed | url=%s | error=%s", url, error_detail, exc_info=exc_info)
    raise DownloadFailedError(f"Download failed for {url}: {error_detail}") from last_error
