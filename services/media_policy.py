MEMORY_SAFE_QUALITY = 480
MEMORY_SAFE_QUALITY_AFTER_SECONDS = 90
MEMORY_SAFE_MAX_DURATION_SECONDS = 150
MAX_TELEGRAM_FILE_SIZE = 50 * 1024 * 1024


def format_file_size(size: int | None) -> str:
    if not size:
        return "unknown size"
    return f"{size / (1024 * 1024):.1f}MB"


def get_known_file_size(video_info: dict) -> int | None:
    size = video_info.get("filesize") or video_info.get("filesize_approx")
    if size:
        return int(size)

    format_sizes = []
    for item in video_info.get("requested_formats") or video_info.get("formats") or []:
        item_size = item.get("filesize") or item.get("filesize_approx")
        if item_size:
            format_sizes.append(int(item_size))

    return max(format_sizes) if format_sizes else None


def choose_quality(requested_quality: int, video_info: dict | None) -> int:
    quality = min(int(requested_quality), 720)
    if not video_info:
        return min(quality, MEMORY_SAFE_QUALITY)

    duration = video_info.get("duration")
    if duration and duration >= MEMORY_SAFE_QUALITY_AFTER_SECONDS:
        return min(quality, MEMORY_SAFE_QUALITY)
    return quality


def is_too_long_for_worker(video_info: dict) -> bool:
    duration = video_info.get("duration")
    return bool(duration and duration > MEMORY_SAFE_MAX_DURATION_SECONDS)


def should_lower_quality_for_size(video_info: dict, quality: int) -> bool:
    size = get_known_file_size(video_info)
    return bool(size and size > MAX_TELEGRAM_FILE_SIZE and quality > MEMORY_SAFE_QUALITY)
