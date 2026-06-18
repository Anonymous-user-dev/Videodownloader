import yt_dlp
from pathlib import Path
from config import settings

MAX_DURATION = 30 * 60

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_COOKIE_PATH = BASE_DIR / "cookies.txt"


def get_cookie_path() -> str | None:
    cookie_path = Path(settings.YTDLP_COOKIES_PATH) if settings.YTDLP_COOKIES_PATH else DEFAULT_COOKIE_PATH
    return str(cookie_path) if cookie_path.exists() else None


def get_video_info(url: str):
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 20,
    }

    cookie_path = get_cookie_path()
    if cookie_path:
        options["cookiefile"] = cookie_path

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if info.get("is_live"):
        raise Exception("Livestream not allowed")

    duration = info.get("duration")
    if duration and duration > MAX_DURATION:
        raise Exception("Video too long")

    return info