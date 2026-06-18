import yt_dlp
from services.ytdlp_cookies import get_cookie_path

MAX_DURATION = 30 * 60


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