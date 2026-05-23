import yt_dlp

MAX_SIZE = 45 * 1024 * 1024
MAX_DURATION = 30 * 60

def get_video_info(url: str):
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 20,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)

    if info.get("is_live"):
        raise Exception("Livestream not allowed")

    duration = info.get("duration")
    if duration and duration > MAX_DURATION:
        raise Exception("Video too long")

    size = info.get("filesize") or info.get("filesize_approx")
    if size and size > MAX_SIZE:
        raise Exception("Video too large")

    return info
