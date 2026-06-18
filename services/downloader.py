import yt_dlp
import os
import uuid
import logging
import time
import requests
from pathlib import Path
from yt_dlp.utils import DownloadError, ExtractorError
from services.ytdlp_cookies import get_cookie_path

logger = logging.getLogger(__name__)

# BASE_DIR = Path(__file__).resolve().parent.parent
# DEFAULT_COOKIE_PATH = BASE_DIR / "cookies.txt"

DOWNLOAD_DIR = Path(os.getcwd()) / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)


def expand_url(url: str) -> str:
    """
    Expands short TikTok URLs (vt.tiktok.com).
    """
    try:
        if "vt.tiktok.com" in url:
            return requests.head(url, allow_redirects=True, timeout=10).url
    except Exception as e:
        logger.warning(f"URL expand failed, using original: {e}")
    return url


def build_format(url: str, quality: int) -> str:
    if "youtube.com" in url or "youtu.be" in url:
        return (
            f"bestvideo*[height<={quality}][vcodec^=avc1]+bestaudio[ext=m4a]/"
            f"best*[height<={quality}][vcodec^=avc1]/"
            f"bestvideo*[height<={quality}]+bestaudio/"
            f"best*[height<={quality}]/"
            "bestvideo*+bestaudio/"
            "best*"
        )


    if "instagram.com" in url:
        return (
            f"bestvideo[height<={quality}][ext=mp4][vcodec^=avc]+"
            f"bestaudio[ext=m4a]/best[height<={quality}]/best"
        )

    return (
        f"bestvideo[height<={quality}]+bestaudio/"
        f"best[height<={quality}]/best/best"
    )


def base_options(url: str, quality: int, unique_id: str):
    options = {
        "outtmpl": str(DOWNLOAD_DIR / f"%(title)s_{unique_id}.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": False,
        "noplaylist": True,
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 3,
        "postprocessor_args": ["-movflags", "+faststart"],
        "format": build_format(url, quality),
        "js_runtimes": {
            "node": {},
        },
    }

    cookie_path = get_cookie_path(url)
    if cookie_path:
        options["cookiefile"] = cookie_path
        logger.info(f"Using yt-dlp cookies from: {cookie_path}")
    else:
        logger.warning("No yt-dlp cookies are being used")

    if "youtube.com" in url or "youtu.be" in url:
        options["http_headers"] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

    # TikTok anti-block headers
    if "tiktok.com" in url:
        options["http_headers"] = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0 Safari/537.36"
            ),
            "Referer": "https://www.tiktok.com/",
            "Accept-Language": "en-US,en;q=0.9",
        }

    return options



def download_video(url: str, quality: int = 1080):
    url = expand_url(url)
    unique_id = str(uuid.uuid4())[:8]

    logger.info(f"Starting download | url={url} | quality={quality}")

    last_error = None

    for attempt in range(1, 4):
        try:
            options = base_options(url, quality, unique_id)

            if "youtube.com" in url or "youtu.be" in url:
                if attempt == 1:
                    options["format"] = (
                        f"bestvideo*[height<={quality}]+bestaudio/"
                        f"best*[height<={quality}]"
                    )
                elif attempt == 2:
                    options["format"] = "bestvideo*+bestaudio/best*"
                else:
                    options["format"] = "best*"

            if "tiktok.com" in url:
                if attempt == 1:
                    options["format"] = f"best[height<={quality}]"
                elif attempt == 2:
                    options["format"] = "best"
                else:
                    options["format"] = "worst/best"

            with yt_dlp.YoutubeDL(options) as ydl:
                logger.info(f"Attempt {attempt}/3")

                info = ydl.extract_info(url, download=True)

                file_path = ydl.prepare_filename(info)

                if not file_path.endswith(".mp4"):
                    file_path = os.path.splitext(file_path)[0] + ".mp4"

                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"Missing file: {file_path}")

                width = info.get("width", 1280)
                height = info.get("height", 720)

                logger.info(f"Success | file={file_path}")

                return file_path, width, height

        except (DownloadError, ExtractorError, Exception) as e:
            last_error = e
            logger.warning(f"Attempt {attempt} failed: {e}")
            time.sleep(2 * attempt)

    logger.error(f"All attempts failed | url={url} | error={last_error}")
    raise RuntimeError(f"Download failed: {url}") from last_error