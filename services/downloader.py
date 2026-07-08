import yt_dlp
import os
import uuid
import logging
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from services.media_probe import has_audio_stream, is_audio_file, probe_video
from services.tiktok_direct import download_tiktok_video_direct
from services.tiktok_ytdlp import tiktok_extractor_args
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


def normalize_url(url: str) -> str:
    if "tiktok.com" in url:
        if "www.tiktok.com" in url:
            return url.split("?")[0]
        return url

    if "instagram.com" in url:
        parsed = urlsplit(url)
        path = parsed.path.rstrip("/") + "/"
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    return url


def is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def is_tiktok_url(url: str) -> bool:
    return "tiktok.com" in url


def is_instagram_url(url: str) -> bool:
    return "instagram.com" in url


def is_video_platform_url(url: str) -> bool:
    return is_youtube_url(url) or is_tiktok_url(url) or is_instagram_url(url)


def build_format(url: str, quality: int) -> str:
    if is_youtube_url(url):
        return (
            "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo+bestaudio/"
            "best*[vcodec!=none][acodec!=none][ext=mp4]/"
            "best*[vcodec!=none][acodec!=none]/"
            "best[ext=mp4]/"
            "best"
        )

    if is_tiktok_url(url):
        return (
            "best[format_id^=h264][ext=mp4]/"
            "best[ext=mp4]/"
            "best"
        )

    if is_instagram_url(url):
        return (
            "best*[vcodec!=none][acodec!=none][ext=mp4]/"
            "best*[vcodec!=none][acodec!=none]/"
            "best[ext=mp4]/"
            "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo+bestaudio/"
            "best"
        )

    return (
        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
        "bestvideo+bestaudio/"
        "best*[vcodec!=none][acodec!=none][ext=mp4]/"
        "best*[vcodec!=none][acodec!=none]/"
        "best[ext=mp4]/"
        "best"
    )


def base_options(url: str, quality: int, unique_id: str, use_cookies: bool = True):
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

    if is_youtube_url(url) or is_instagram_url(url):
        options["format_sort"] = [f"res:{quality}", "ext:mp4:m4a"]
        options["format_sort_force"] = True

    if is_youtube_url(url):
        options["http_headers"] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

    if is_tiktok_url(url):
        options["format_sort"] = [f"res:{quality}", "ext:mp4:m4a"]
        options["format_sort_force"] = True
        options["extractor_args"] = tiktok_extractor_args()
        options["http_headers"] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.tiktok.com/",
            "Accept-Language": "en-US,en;q=0.9",
        }

    if is_instagram_url(url):
        options["http_headers"] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.instagram.com/",
            "Accept-Language": "en-US,en;q=0.9",
            "X-IG-App-ID": "936619743392459",
        }

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
    if target_quality < 720:
        return False
    return visible_resolution(width, height) < 540


def download_video(url: str, quality: int = 1080):
    url = normalize_url(url)
    quality = min(int(quality), 1080)
    unique_id = str(uuid.uuid4())[:8]

    logger.info(f"Starting download | url={url} | quality={quality}")

    last_error = None
    quality_ladder = build_quality_ladder(quality)

    for attempt, attempt_quality in enumerate(quality_ladder, start=1):
        try:
            use_cookies = not (is_instagram_url(url) and attempt == 2)
            options = base_options(url, attempt_quality, unique_id, use_cookies=use_cookies)

            if is_youtube_url(url):
                options["format"] = build_format(url, attempt_quality)

            if is_tiktok_url(url):
                options["extractor_args"] = tiktok_extractor_args(attempt)
                if attempt == 1:
                    options["format"] = "best[format_id^=h264][ext=mp4]/best[ext=mp4]"
                elif attempt == 2:
                    options["format"] = "best[ext=mp4]/best"
                else:
                    options["format"] = "best"

            with yt_dlp.YoutubeDL(options) as ydl:
                logger.info("Attempt %s/%s | target_quality=%sp", attempt, len(quality_ladder), attempt_quality)

                info = ydl.extract_info(url, download=True)

                file_path = find_downloaded_file(info, ydl)

                if not file_path:
                    raise FileNotFoundError(f"Missing downloaded file for: {url}")

                has_video, probed_width, probed_height, codec = probe_video(file_path)
                if not has_video:
                    if is_audio_file(file_path):
                        if is_tiktok_url(url):
                            direct_result = try_tiktok_direct_video(url, unique_id)
                            if direct_result:
                                try:
                                    Path(file_path).unlink(missing_ok=True)
                                except Exception as cleanup_exc:
                                    logger.warning("Could not clean yt-dlp audio fallback %s: %s", file_path, cleanup_exc)
                                video_path, width, height = direct_result
                                return video_path, width, height, "video"

                        if is_video_platform_url(url):
                            try:
                                Path(file_path).unlink(missing_ok=True)
                            except Exception as cleanup_exc:
                                logger.warning("Could not clean audio-only video-platform file %s: %s", file_path, cleanup_exc)
                            raise RuntimeError(f"Audio-only download selected for video URL: {url}")

                        logger.info("Downloaded audio-only media: %s", file_path)
                        return file_path, 0, 0, "audio"
                    raise RuntimeError(f"Downloaded file has no video stream: {file_path}")

                if is_video_platform_url(url) and not has_audio_stream(file_path):
                    try:
                        Path(file_path).unlink(missing_ok=True)
                    except Exception as cleanup_exc:
                        logger.warning("Could not clean muted video-platform file %s: %s", file_path, cleanup_exc)
                    raise RuntimeError(f"Downloaded video has no audio stream: {url}")

                width = info.get("width") or probed_width
                height = info.get("height") or probed_height

                if is_video_quality_too_low(attempt_quality, width, height):
                    try:
                        Path(file_path).unlink(missing_ok=True)
                    except Exception as cleanup_exc:
                        logger.warning("Could not clean low-quality file %s: %s", file_path, cleanup_exc)
                    raise RuntimeError(
                        f"Downloaded video is only {width}x{height} for target {attempt_quality}p"
                    )

                logger.info(f"Success | file={file_path} | codec={codec} | size={width}x{height}")

                return file_path, width, height, "video"

        except Exception as e:
            last_error = e
            logger.warning("Attempt %s failed for %s: %s", attempt, url, e, exc_info=True)
            time.sleep(2 * attempt)

    error_detail = str(last_error) if last_error else "unknown error"
    exc_info = (type(last_error), last_error, last_error.__traceback__) if last_error else None
    logger.error("All attempts failed | url=%s | error=%s", url, error_detail, exc_info=exc_info)
    raise DownloadFailedError(f"Download failed for {url}: {error_detail}") from last_error
