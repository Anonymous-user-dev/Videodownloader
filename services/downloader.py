import yt_dlp
import os
import uuid
import logging
import time
import requests
import subprocess
from pathlib import Path
from yt_dlp.utils import urlencode_postdata
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


def download_image(image_url: str, output_path: Path) -> Path:
    response = requests.get(
        image_url,
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


def image_urls_from_aweme_detail(aweme_detail: dict) -> list[str]:
    urls = []
    images = aweme_detail.get("image_post_info", {}).get("images") or []

    for image in images:
        url_list = (
            image.get("display_image", {}).get("url_list")
            or image.get("owner_watermark_image", {}).get("url_list")
            or image.get("thumbnail", {}).get("url_list")
            or []
        )
        if url_list:
            urls.append(url_list[-1])

    seen = set()
    unique_urls = []
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            unique_urls.append(url)
    return unique_urls


def extract_tiktok_slideshow_image_urls(video_id: str, options: dict, attempt: int) -> list[str]:
    if not video_id:
        return []

    api_options = dict(options)
    api_options["extractor_args"] = tiktok_extractor_args(attempt)

    with yt_dlp.YoutubeDL(api_options) as ydl:
        ie = ydl.get_info_extractor("TikTok")
        aweme_detail = ie._call_api(
            "multi/aweme/detail",
            video_id,
            data=urlencode_postdata({
                "aweme_ids": f"[{video_id}]",
                "request_source": "0",
            }),
            headers={"X-Argus": ""},
        ).get("aweme_details", [{}])[0]

    image_urls = image_urls_from_aweme_detail(aweme_detail)
    logger.info("Extracted %s TikTok slideshow image(s) for %s", len(image_urls), video_id)
    return image_urls


def ffconcat_path(path: Path) -> str:
    return path.as_posix().replace("'", "'\\''")


def build_slideshow_video_from_audio(audio_path: str, image_urls: list[str]) -> str:
    audio = Path(audio_path)
    image_paths = []
    output_path = audio.with_suffix(".slideshow.mp4")
    image_list_path = audio.with_suffix(".images.txt")

    for index, image_url in enumerate(image_urls, start=1):
        image_path = audio.with_suffix(f".slide{index}.jpg")
        download_image(image_url, image_path)
        image_paths.append(image_path)

    if not image_paths:
        raise RuntimeError("No slideshow images were downloaded")

    audio_duration = get_audio_duration(audio_path)
    seconds_per_image = max(audio_duration / len(image_paths), 1.0)

    image_list_path.write_text(
        "".join(
            f"file '{ffconcat_path(image_path)}'\n"
            f"duration {seconds_per_image:.3f}\n"
            for image_path in image_paths
        )
        + f"file '{ffconcat_path(image_paths[-1])}'\n",
        encoding="utf-8",
    )

    command = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(image_list_path),
        "-i",
        str(audio),
        "-vf",
        "scale=720:-2,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-r",
        "30",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=240)
    if result.returncode != 0 or not output_path.exists():
        raise RuntimeError(f"Could not build TikTok slideshow video: {result.stderr[-500:]}")

    for image_path in image_paths:
        try:
            image_path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("Could not clean slideshow image %s: %s", image_path, exc)

    try:
        image_list_path.unlink(missing_ok=True)
        audio.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Could not clean slideshow temp file: %s", exc)

    logger.info("Built TikTok slideshow video: %s", output_path)
    return str(output_path)


def get_audio_duration(audio_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        return 30.0
    try:
        return max(float(result.stdout.strip()), 1.0)
    except ValueError:
        return 30.0


def build_video_from_audio_cover(audio_path: str, thumbnail_url: str) -> str:
    audio = Path(audio_path)
    thumb_path = audio.with_suffix(".cover.jpg")
    output_path = audio.with_suffix(".cover.mp4")

    download_image(thumbnail_url, thumb_path)

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
                            try:
                                image_urls = extract_tiktok_slideshow_image_urls(info.get("id"), options, attempt)
                            except Exception as exc:
                                logger.warning(
                                    "Could not extract TikTok slideshow images: %s",
                                    exc,
                                    exc_info=True,
                                )
                                image_urls = []

                            if image_urls:
                                try:
                                    video_path = build_slideshow_video_from_audio(file_path, image_urls)
                                    _, video_width, video_height, _ = probe_video(video_path)
                                    return video_path, video_width, video_height, "video"
                                except Exception as exc:
                                    logger.warning(
                                        "Could not build TikTok slideshow video: %s",
                                        exc,
                                        exc_info=True,
                                    )

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
