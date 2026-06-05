import yt_dlp
import os
import uuid
import subprocess
import logging

logger = logging.getLogger(__name__)


def get_format_string(url: str, quality: int) -> str:
    """Checks if it's youtube, tiktok, or instagram url"""
    if 'youtube.com' in url or 'youtu.be' in url:
        return f'bestvideo[height<={quality}][vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={quality}][vcodec^=avc]+bestaudio'
    elif 'instagram.com' in url:
        # Instagram specific: prefer H264 codec and ensure proper merging
        return f'bestvideo[height<={quality}][ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[height<={quality}][ext=mp4]/best'
    else:
        return f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best'


def fix_instagram_video(file_path: str) -> str:
    """Re-encode Instagram video to ensure compatibility"""
    try:
        temp_output = file_path.replace('.mp4', '_fixed.mp4')

        # Re-encode video with proper codec settings
        cmd = [
            'ffmpeg', '-i', file_path,
            '-c:v', 'libx264',  # H264 codec
            '-c:a', 'aac',  # AAC audio
            '-movflags', '+faststart',  # Optimize for streaming
            '-pix_fmt', 'yuv420p',  # Compatible pixel format
            '-preset', 'fast',
            '-crf', '23',
            temp_output,
            '-y'  # Overwrite output file
        ]

        subprocess.run(cmd, capture_output=True, check=True)

        # Replace original with fixed version
        os.remove(file_path)
        os.rename(temp_output, file_path)

        return file_path
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg error: {e.stderr.decode() if e.stderr else str(e)}")
        return file_path
    except Exception as e:
        logger.error(f"Error fixing video: {e}")
        return file_path


def download_video(url: str, quality: int = 1080):
    """Downloads video with Instagram-specific handling"""
    DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    is_instagram = 'instagram.com' in url

    # Instagram-specific options
    options = {
        'format': get_format_string(url, quality),
        'outtmpl': os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        'merge_output_format': 'mp4',
        "quiet": True,
        "no_warnings": True,
        "retries": 5,
        "socket_timeout": 30,
        "cookiefile": "cookie.txt",
        "sleep_interval": 2,
    }

    # Additional options for Instagram
    if is_instagram:
        options.update({
            'extract_flat': False,
            'ignoreerrors': True,
            'no_check_certificate': True,
            'prefer_ffmpeg': True,  # Force using ffmpeg for merging
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
        })

    def _download():
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            file_name = ydl.prepare_filename(info)

            # For Instagram, ensure proper extension
            if is_instagram and not file_name.endswith('.mp4'):
                base = os.path.splitext(file_name)[0]
                file_name = base + '.mp4'

            width = info.get('width', 1280)
            height = info.get('height', 720)

            ydl.download([url])

            # Fix Instagram video if needed
            if is_instagram and os.path.exists(file_name):
                file_name = fix_instagram_video(file_name)

            return file_name, width, height

    try:
        file_name, width, height = _download()

        # Verify the file is playable
        if is_instagram and os.path.exists(file_name):
            if os.path.getsize(file_name) < 10000:  # File too small
                raise Exception("Downloaded file is too small, possibly corrupted")

        return file_name, width, height
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise