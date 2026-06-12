# services/downloader.py

import yt_dlp
import os
import uuid
import subprocess
import logging
import time

logger = logging.getLogger(__name__)


def get_format_string(url: str, quality: int) -> str:
    """Get format string based on platform and quality"""
    quality = int(quality)

    # For YouTube
    if 'youtube.com' in url or 'youtu.be' in url:
        # Force merging to mp4
        return f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best'

    # For Instagram
    elif 'instagram.com' in url:
        return f'bestvideo[height<={quality}][ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best'

    # For other platforms (TikTok, etc.)
    else:
        return f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best'


def download_video(url: str, quality: int = 1080):
    """Downloads video with specified quality"""
    DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # Generate unique filename
    unique_id = str(uuid.uuid4())[:8]

    # Basic options
    options = {
        'format': get_format_string(url, quality),
        'outtmpl': os.path.join(DOWNLOAD_DIR, f'%(title)s_{unique_id}.%(ext)s'),
        'merge_output_format': 'mp4',
        "quiet": False,
        "no_warnings": False,
        "retries": 5,
        "socket_timeout": 30,
        "ignoreerrors": False,
        "noplaylist": True,
        # Important: Force post-processing to wait for merge
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4',
        }],
    }

    # Add cookiefile if it exists
    if os.path.exists("cookie.txt"):
        options["cookiefile"] = "cookie.txt"

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            logger.info(f"Downloading {quality}p quality for URL: {url}")

            # Download and merge
            info = ydl.extract_info(url, download=True)

            # Get the final filename after merging
            file_name = ydl.prepare_filename(info)

            # Ensure .mp4 extension
            if not file_name.endswith('.mp4'):
                base = os.path.splitext(file_name)[0]
                file_name = base + '.mp4'

            # Wait a moment for the file to be fully written
            time.sleep(1)

            # Verify the file exists and get its size
            if not os.path.exists(file_name):
                # Try to find the file in downloads directory
                import glob
                mp4_files = glob.glob(os.path.join(DOWNLOAD_DIR, f"*{unique_id}*.mp4"))
                if mp4_files:
                    file_name = mp4_files[0]
                else:
                    # Get the most recent mp4 file
                    mp4_files = glob.glob(os.path.join(DOWNLOAD_DIR, "*.mp4"))
                    if mp4_files:
                        file_name = max(mp4_files, key=os.path.getctime)

            if not os.path.exists(file_name):
                raise Exception(f"Downloaded file not found: {file_name}")

            file_size = os.path.getsize(file_name)
            file_size_mb = file_size / (1024 * 1024)

            # Get video dimensions
            width = info.get('width', 1280)
            height = info.get('height', 720)

            logger.info(f"Download complete: {os.path.basename(file_name)} ({file_size_mb:.2f}MB) for {quality}p")

            return file_name, width, height

    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        raise