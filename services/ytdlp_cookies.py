import logging
import shutil
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_COOKIES_PATH = BASE_DIR / "cookies.txt"
DEFAULT_YOUTUBE_COOKIES_PATH = BASE_DIR / "youtube_cookies.txt"
DEFAULT_TIKTOK_COOKIES_PATH = BASE_DIR / "tiktok_cookies.txt"
DEFAULT_INSTAGRAM_COOKIES_PATH = BASE_DIR / "instagram_cookies.txt"

RUNTIME_DIR = Path("/tmp")


def is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def is_tiktok_url(url: str) -> bool:
    return "tiktok.com" in url


def is_instagram_url(url: str) -> bool:
    return "instagram.com" in url


def get_source_cookie_path(url: str) -> Path | None:
    if is_youtube_url(url):
        if settings.YOUTUBE_COOKIES_PATH:
            return Path(settings.YOUTUBE_COOKIES_PATH)
        return DEFAULT_YOUTUBE_COOKIES_PATH

    if is_tiktok_url(url):
        if settings.TIKTOK_COOKIES_PATH:
            return Path(settings.TIKTOK_COOKIES_PATH)
        return DEFAULT_TIKTOK_COOKIES_PATH

    if is_instagram_url(url):
        if settings.INSTAGRAM_COOKIES_PATH:
            return Path(settings.INSTAGRAM_COOKIES_PATH)
        if DEFAULT_INSTAGRAM_COOKIES_PATH.exists():
            return DEFAULT_INSTAGRAM_COOKIES_PATH
        logger.warning(
            "No Instagram-specific cookies configured. Set INSTAGRAM_COOKIES_PATH for private or login-gated Instagram posts."
        )
        return None

    if settings.YTDLP_COOKIES_PATH:
        return Path(settings.YTDLP_COOKIES_PATH)

    return DEFAULT_COOKIES_PATH


def get_cookie_path(url: str) -> str | None:
    source_path = get_source_cookie_path(url)

    if source_path is None:
        return None

    if not source_path.exists():
        logger.warning("yt-dlp cookies file not found: %s", source_path)
        return None

    runtime_path = RUNTIME_DIR / source_path.name
    shutil.copyfile(source_path, runtime_path)

    logger.warning(
        "Using yt-dlp cookies: source=%s runtime=%s size=%s",
        source_path,
        runtime_path,
        runtime_path.stat().st_size,
    )

    return str(runtime_path)
