import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".m4a", ".mp3", ".aac", ".opus", ".ogg", ".wav"}


def is_audio_file(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in AUDIO_EXTENSIONS


def probe_video(file_path: str) -> tuple[bool, int, int, str | None]:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height",
                "-of",
                "csv=p=0",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as exc:
        logger.warning("Could not run ffprobe for %s: %s", file_path, exc)
        return True, 1280, 720, None

    output = result.stdout.strip()
    if result.returncode != 0 or not output:
        return False, 0, 0, None

    parts = output.split(",")
    codec = parts[0] if len(parts) > 0 else None
    width = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1280
    height = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 720
    return True, width, height, codec


def has_audio_stream(file_path: str) -> bool:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name",
                "-of",
                "csv=p=0",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except Exception as exc:
        logger.warning("Could not run audio ffprobe for %s: %s", file_path, exc)
        return True

    return result.returncode == 0 and bool(result.stdout.strip())
