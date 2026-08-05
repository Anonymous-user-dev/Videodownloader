import logging
import validators
import yt_dlp
from services.platform_policy import get_platform_policy
from services.ytdlp_cookies import get_cookie_path

logger = logging.getLogger(__name__)

MAX_DURATION = 30 * 60


class YtdlpLogBridge:
    def debug(self, message):
        logger.debug("yt-dlp: %s", message)

    def warning(self, message):
        logger.warning("yt-dlp: %s", message)

    def error(self, message):
        logger.error("yt-dlp: %s", message)


def get_video_info(url: str):
    policy = get_platform_policy(url)
    url = policy.normalize_url(url)

    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 20,
        "skip_download": True,
        "extract_flat": False,
        "format": None,
        "logger": YtdlpLogBridge(),
        "js_runtimes": {
            "node": {},
        },
        "remote_components": ["ejs:github"],
    }

    cookie_path = get_cookie_path(url)
    if cookie_path:
        options["cookiefile"] = cookie_path
        logger.info("Using yt-dlp cookies for video info: %s", cookie_path)
    else:
        logger.warning("No yt-dlp cookies found for video info")

    options.update(policy.ytdlp_options(quality=1080, attempt=1))

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False, process=True)

    if info.get("is_live"):
        raise Exception("Livestream not allowed")

    duration = info.get("duration")
    if duration and duration > MAX_DURATION:
        raise Exception("Video too long")

    return info

def is_valid_url(url):
    return validators.url(url)

