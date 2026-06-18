import logging
import yt_dlp

from services.ytdlp_cookies import get_cookie_path

logger = logging.getLogger(__name__)

MAX_DURATION = 30 * 60


def is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def is_tiktok_url(url: str) -> bool:
    return "tiktok.com" in url


def get_video_info(url: str):
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "skip_download": True,
        "extract_flat": False,
        "format": None,
        "js_runtimes": {
            "node": {},
        },
    }

    cookie_path = get_cookie_path(url)
    if cookie_path:
        options["cookiefile"] = cookie_path
        logger.info("Using yt-dlp cookies for video info: %s", cookie_path)
    else:
        logger.warning("No yt-dlp cookies found for video info")

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
        options["impersonate"] = "chrome"
        options["http_headers"] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.tiktok.com/",
            "Accept-Language": "en-US,en;q=0.9",
        }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False, process=False)

    if info.get("is_live"):
        raise Exception("Livestream not allowed")

    duration = info.get("duration")
    if duration and duration > MAX_DURATION:
        raise Exception("Video too long")

    return info