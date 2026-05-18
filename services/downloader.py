import yt_dlp
import os
import uuid
import logging

logger = logging.getLogger(__name__)

def get_format_string(url: str, quality: int) -> str:
    """Checks if it's youtube or tiktok, instagram url"""
    if 'youtube.com' in url or 'youtu.be' in url:
        return f'bestvideo[height<={quality}][vcodec^=avc][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={quality}][vcodec^=avc]+bestaudio'
    else:
        return f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best'

def download_video(url: str, quality: int = 1080):
    """Downloads video"""
    os.makedirs("downloads", exist_ok=True)

    options = {
        'format': get_format_string(url, quality),
        'outtmpl': f'downloads/{uuid.uuid4()}.%(ext)s',
        'merge_output_format': 'mp4',
        'postprocessor_args': {
            'ffmpegmerger': ['-movflags', '+faststart'],
        },
    }

    def _download():
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
            file_name = ydl.prepare_filename(info)
            width = info.get('width', 1280)
            height = info.get('height', 720)
            ydl.download([url])
            return file_name, width, height

    try:
        file_name, width, height = _download()
        return file_name, width, height
    except Exception as e:
        logger.error(f"Download error: {e}")
        raise