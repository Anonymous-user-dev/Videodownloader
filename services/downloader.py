import yt_dlp
import os
import uuid
import logging
import time
import requests
import subprocess
from pathlib import Path
from services.media_probe import is_audio_file, probe_video
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

    return url


def is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def is_tiktok_url(url: str) -> bool:
    return "tiktok.com" in url


def build_format(url: str, quality: int) -> str:
    if is_youtube_url(url):
        if quality <= 480:
            return (
                f"best[height<={quality}][ext=mp4]/"
                f"best*[height<={quality}][ext=mp4]/"
                f"best[height<={quality}]/"
                "best[ext=mp4]/"
                "best"
            )

        return (
            f"best[height<={quality}][ext=mp4]/"
            f"best*[height<={quality}]/"
            "best"
        )

    if is_tiktok_url(url):
        return (
            "best[format_id^=h264][ext=mp4]/"
            f"best[ext=mp4][height<={quality}]/"
            "best[ext=mp4]/"
            "best"
        )

    if "instagram.com" in url:
        return (
            f"bestvideo[height<={quality}][ext=mp4][vcodec^=avc]+"
            f"bestaudio[ext=m4a]/best[height<={quality}]/best"
        )

    return (
        f"bestvideo*[height<={quality}]+bestaudio/"
        f"best*[height<={quality}]/"
        "best"
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
        "concurrent_fragment_downloads": 1,
        "postprocessor_args": ["-movflags", "+faststart"],
        "format": build_format(url, quality),
        "logger": YtdlpLogBridge(),
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


def get_thumbnail_url(info: dict) -> str | None:
    thumbnails = info.get("thumbnails") or []
    for thumbnail in reversed(thumbnails):
        url = thumbnail.get("url")
        if url:
            return url
    return info.get("thumbnail")


def download_thumbnail(thumbnail_url: str, output_path: Path) -> Path:
    response = requests.get(
        thumbnail_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        },
        timeout=30,
    )
    response.raise_for_status()
    output_path.write_bytes(response.content)
    return output_path


def build_video_from_audio_cover(audio_path: str, thumbnail_url: str) -> str:
    audio = Path(audio_path)
    thumb_path = audio.with_suffix(".cover.jpg")
    output_path = audio.with_suffix(".cover.mp4")

    download_thumbnail(thumbnail_url, thumb_path)

    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(thumb_path),
        "-i",
        str(audio),
        "-vf",
        "scale=720:-2,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-tune",
        "stillimage",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if result.returncode != 0 or not output_path.exists():
        raise RuntimeError(f"Could not build video from audio-only TikTok: {result.stderr[-500:]}")

    try:
        thumb_path.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Could not clean thumbnail %s: %s", thumb_path, exc)

    try:
        audio.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Could not clean audio source %s: %s", audio, exc)

    logger.info("Built video from audio-only TikTok media: %s", output_path)
    return str(output_path)


def download_video(url: str, quality: int = 1080):
    url = normalize_url(url)
    quality = min(int(quality), 720)
    unique_id = str(uuid.uuid4())[:8]

    logger.info(f"Starting download | url={url} | quality={quality}")

    last_error = None

    for attempt in range(1, 4):
        try:
            options = base_options(url, quality, unique_id)

            if is_youtube_url(url):
                if attempt == 1:
                    options["format"] = build_format(url, quality)
                elif attempt == 2:
                    options["format"] = (
                        f"best*[height<={quality}][ext=mp4]/"
                        f"best*[height<={quality}]/"
                        "best[ext=mp4]/"
                        "best"
                    )
                else:
                    options["format"] = "best[ext=mp4]/best"

            if is_tiktok_url(url):
                options["extractor_args"] = tiktok_extractor_args(attempt)
                if attempt == 1:
                    options["format"] = "best[format_id^=h264][ext=mp4]/best[ext=mp4]"
                elif attempt == 2:
                    options["format"] = "best[ext=mp4]/best"
                else:
                    options["format"] = "best"

            with yt_dlp.YoutubeDL(options) as ydl:
                logger.info(f"Attempt {attempt}/3")

                info = ydl.extract_info(url, download=True)

                file_path = find_downloaded_file(info, ydl)

                if not file_path:
                    raise FileNotFoundError(f"Missing downloaded file for: {url}")

                has_video, probed_width, probed_height, codec = probe_video(file_path)
                if not has_video:
                    if is_audio_file(file_path):
                        if is_tiktok_url(url):
                            thumbnail_url = get_thumbnail_url(info)
                            if thumbnail_url:
                                try:
                                    video_path = build_video_from_audio_cover(file_path, thumbnail_url)
                                    _, video_width, video_height, _ = probe_video(video_path)
                                    return video_path, video_width, video_height, "video"
                                except Exception as exc:
                                    logger.warning(
                                        "Could not build video from TikTok audio-only media: %s",
                                        exc,
                                        exc_info=True,
                                    )
                            logger.warning("TikTok audio-only media had no thumbnail to build video: %s", url)

                        logger.info("Downloaded audio-only media: %s", file_path)
                        return file_path, 0, 0, "audio"
                    raise RuntimeError(f"Downloaded file has no video stream: {file_path}")

                width = info.get("width") or probed_width
                height = info.get("height") or probed_height

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
