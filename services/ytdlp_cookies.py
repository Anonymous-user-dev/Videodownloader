import logging
import shutil
from pathlib import Path

from config import settings
from services.platform_policy import get_platform_policy

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_COOKIES_PATH = BASE_DIR / "cookies.txt"
DEFAULT_YOUTUBE_COOKIES_PATH = BASE_DIR / "youtube_cookies.txt"
DEFAULT_TIKTOK_COOKIES_PATH = BASE_DIR / "tiktok_cookies.txt"
DEFAULT_INSTAGRAM_COOKIES_PATH = BASE_DIR / "instagram_cookies.txt"

RUNTIME_DIR = Path("/tmp")
INSTAGRAM_AUTH_COOKIE_NAMES = {"sessionid", "ds_user_id"}


def cookie_names_for_domain(path: Path, domain_fragment: str) -> set[str]:
    names: set[str] = set()

    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()

            if not line or line.startswith("#") and not line.startswith("#HttpOnly_"):
                continue

            parts = line.split("\t")
            if len(parts) < 7:
                continue

            domain = parts[0].removeprefix("#HttpOnly_")
            if domain_fragment not in domain:
                continue

            names.add(parts[5])

    except Exception as exc:
        logger.warning("Could not inspect cookies file %s: %s", path, exc, exc_info=True)

    return names


def has_instagram_auth_cookies(path: Path) -> bool:
    names = cookie_names_for_domain(path, "instagram.com")
    missing = sorted(INSTAGRAM_AUTH_COOKIE_NAMES - names)

    if missing:
        logger.warning(
            "Instagram cookies file is missing auth cookies. path=%s size=%s missing=%s found=%s",
            path,
            path.stat().st_size if path.exists() else "missing",
            ",".join(missing),
            ",".join(sorted(names)) or "none",
        )
        return False

    logger.info(
        "Instagram cookies file contains required auth cookies. path=%s found=%s",
        path,
        ",".join(sorted(names)),
    )
    return True


def instagram_cookie_candidates() -> list[Path]:
    candidates = []

    if settings.INSTAGRAM_COOKIES_PATH:
        candidates.append(Path(settings.INSTAGRAM_COOKIES_PATH))

    candidates.append(DEFAULT_INSTAGRAM_COOKIES_PATH)

    if settings.YTDLP_COOKIES_PATH:
        candidates.append(Path(settings.YTDLP_COOKIES_PATH))

    candidates.append(DEFAULT_COOKIES_PATH)

    unique_candidates = []
    seen = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique_candidates.append(candidate)

    return unique_candidates


def get_instagram_cookie_path() -> Path | None:
    existing_candidates = []

    for candidate in instagram_cookie_candidates():
        if not candidate.exists():
            logger.warning("Instagram cookies candidate not found: %s", candidate)
            continue

        existing_candidates.append(candidate)

        if has_instagram_auth_cookies(candidate):
            return candidate

    if existing_candidates:
        logger.warning(
            "No Instagram cookie file with sessionid and ds_user_id was found. "
            "Using first existing candidate anyway; private/follow-gated reels may fail."
        )
        return existing_candidates[0]

    logger.warning(
        "No Instagram cookies configured. Set INSTAGRAM_COOKIES_PATH for private or login-gated Instagram posts."
    )
    return None


def get_source_cookie_path(url: str) -> Path | None:
    platform = get_platform_policy(url).name

    if platform == "youtube":
        if settings.YOUTUBE_COOKIES_PATH:
            return Path(settings.YOUTUBE_COOKIES_PATH)
        return DEFAULT_YOUTUBE_COOKIES_PATH

    if platform == "tiktok":
        if settings.TIKTOK_COOKIES_PATH:
            return Path(settings.TIKTOK_COOKIES_PATH)
        return DEFAULT_TIKTOK_COOKIES_PATH

    if platform == "instagram":
        return get_instagram_cookie_path()

    if settings.YTDLP_COOKIES_PATH:
        return Path(settings.YTDLP_COOKIES_PATH)

    return DEFAULT_COOKIES_PATH


def get_cookie_path(url: str) -> str | None:
    source_path = get_source_cookie_path(url)

    if source_path is None:
        return None

    if not source_path.exists():
        logger.warning("yt-dlp cookies file not found: %s", source_path)
        return None

    runtime_path = RUNTIME_DIR / source_path.name
    shutil.copyfile(source_path, runtime_path)

    logger.warning(
        "Using yt-dlp cookies: source=%s runtime=%s size=%s",
        source_path,
        runtime_path,
        runtime_path.stat().st_size,
    )

    return str(runtime_path)
