import logging
from pathlib import Path
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)

TIKWM_API_URL = "https://www.tikwm.com/api/"
TIKWM_BASE_URL = "https://www.tikwm.com"


class TikTokDirectError(RuntimeError):
    pass


def resolve_tiktok_video_url(url: str) -> str | None:
    response = requests.get(
        TIKWM_API_URL,
        params={"url": url},
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
        },
        timeout=20,
    )
    response.raise_for_status()

    payload = response.json()
    data = payload.get("data") or {}
    video_url = data.get("hdplay") or data.get("play") or data.get("wmplay")
    if not video_url:
        logger.warning("TikTok direct resolver returned no video URL: %s", payload)
        return None

    return urljoin(TIKWM_BASE_URL, video_url)


def download_tiktok_video_direct(url: str, output_path: Path) -> str:
    video_url = resolve_tiktok_video_url(url)
    if not video_url:
        raise TikTokDirectError("TikTok direct resolver did not return a video URL")

    logger.info("Downloading TikTok direct video: %s", video_url)
    with requests.get(
        video_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": TIKWM_BASE_URL,
        },
        stream=True,
        timeout=120,
    ) as response:
        response.raise_for_status()
        with open(output_path, "wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file.write(chunk)

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise TikTokDirectError("TikTok direct download produced an empty file")

    logger.info(
        "Downloaded TikTok direct video: %s (%.2fMB)",
        output_path,
        output_path.stat().st_size / (1024 * 1024),
    )
    return str(output_path)
