import logging
import shutil
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_COOKIE_PATH = BASE_DIR / "cookies.txt"
RUNTIME_COOKIE_PATH = Path("/tmp/cookies.txt")


def get_cookie_path() -> str | None:
    source_path = (
        Path(settings.YTDLP_COOKIES_PATH)
        if settings.YTDLP_COOKIES_PATH
        else DEFAULT_COOKIE_PATH
    )

    if not source_path.exists():
        logger.warning("yt-dlp cookies file not found")
        return None

    if source_path != RUNTIME_COOKIE_PATH:
        shutil.copyfile(source_path, RUNTIME_COOKIE_PATH)
        logger.info("Copied yt-dlp cookies to /tmp/cookies.txt")

    return str(RUNTIME_COOKIE_PATH)