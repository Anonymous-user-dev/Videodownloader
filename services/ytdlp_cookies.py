import logging
import shutil
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_COOKIES_PATH = BASE_DIR / "cookies.txt"
DEFAULT_YOUTUBE_COOKIES_PATH = BASE_DIR / "youtube_cookies.txt"
DEFAULT_TIKTOK_COOKIES_PATH = BASE_DIR / "tiktok_cookies.txt"

RUNTIME_DIR = Path("/tmp")


def is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def is_tiktok_url(url: str) -> bool:
    return "tiktok.com" in url


def get_source_cookie_path(url: str) -> Path:
    if is_youtube_url(url):
        if settings.YOUTUBE_COOKIES_PATH:
            return Path(settings.YOUTUBE_COOKIES_PATH)
        return DEFAULT_YOUTUBE_COOKIES_PATH

    if is_tiktok_url(url):
        if settings.TIKTOK_COOKIES_PATH:
            return Path(settings.TIKTOK_COOKIES_PATH)
        return DEFAULT_TIKTOK_COOKIES_PATH

    if settings.YTDLP_COOKIES_PATH:
        return Path(settings.YTDLP_COOKIES_PATH)

    return DEFAULT_COOKIES_PATH


def get_cookie_path(url: str) -> str | None:
    source_path = get_source_cookie_path(url)

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