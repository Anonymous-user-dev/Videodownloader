from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from services.tiktok_ytdlp import tiktok_extractor_args

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def minimum_acceptable_resolution(quality: int) -> int:
    if quality >= 720:
        return 540
    if quality >= 480:
        return 450
    return 0


def build_social_format(quality: int) -> str:
    min_width = minimum_acceptable_resolution(quality)
    high_quality_formats = []

    if min_width:
        high_quality_formats = [
            f"best*[vcodec!=none][acodec!=none][ext=mp4][width>={min_width}]",
            f"best*[vcodec!=none][acodec!=none][width>={min_width}]",
            f"bestvideo[ext=mp4][width>={min_width}]+bestaudio[ext=m4a]",
            f"bestvideo[width>={min_width}]+bestaudio",
        ]

    fallback_formats = [
        "best*[vcodec!=none][acodec!=none][ext=mp4]",
        "best*[vcodec!=none][acodec!=none]",
        "best[ext=mp4]",
        "best",
    ]
    return "/".join(high_quality_formats + fallback_formats)


def build_youtube_format(quality: int) -> str:
    return (
        f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo[width<={quality}][ext=mp4]+bestaudio[ext=m4a]/"
        f"bestvideo[height<={quality}]+bestaudio/"
        f"bestvideo[width<={quality}]+bestaudio/"
        f"best*[vcodec!=none][acodec!=none][height<={quality}][ext=mp4]/"
        f"best*[vcodec!=none][acodec!=none][width<={quality}][ext=mp4]/"
        f"best*[vcodec!=none][acodec!=none][height<={quality}]/"
        f"best*[vcodec!=none][acodec!=none][width<={quality}]/"
        "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/"
        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
        "bestvideo+bestaudio/"
        "best*[vcodec!=none][acodec!=none][ext=mp4]/"
        "best*[vcodec!=none][acodec!=none]/"
        "best[ext=mp4]/"
        "best"
    )


GENERIC_FORMAT = (
    "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
    "bestvideo+bestaudio/"
    "best*[vcodec!=none][acodec!=none][ext=mp4]/"
    "best*[vcodec!=none][acodec!=none]/"
    "best[ext=mp4]/"
    "best"
)


@dataclass(frozen=True)
class PlatformPolicy:
    name: str = "unknown"
    domains: tuple[str, ...] = ()
    requires_video_and_audio: bool = False

    def matches(self, url: str) -> bool:
        host = (urlsplit(url).hostname or "").lower()
        return any(host == domain or host.endswith(f".{domain}") for domain in self.domains)

    def normalize_url(self, url: str) -> str:
        return url

    def format_selector(self, quality: int) -> str:
        return GENERIC_FORMAT

    def use_cookies(self, attempt: int) -> bool:
        return True

    def ytdlp_options(self, quality: int, attempt: int) -> dict:
        return {}


@dataclass(frozen=True)
class YouTubePolicy(PlatformPolicy):
    name: str = "youtube"
    domains: tuple[str, ...] = ("youtube.com", "youtu.be")
    requires_video_and_audio: bool = True

    def format_selector(self, quality: int) -> str:
        return build_youtube_format(quality)

    def ytdlp_options(self, quality: int, attempt: int) -> dict:
        return {
            "http_headers": {
                "User-Agent": BROWSER_USER_AGENT,
                "Accept-Language": "en-US,en;q=0.9",
            }
        }


@dataclass(frozen=True)
class TikTokPolicy(PlatformPolicy):
    name: str = "tiktok"
    domains: tuple[str, ...] = ("tiktok.com",)
    requires_video_and_audio: bool = True

    def normalize_url(self, url: str) -> str:
        if "www.tiktok.com" in url:
            return url.split("?", 1)[0]
        return url

    def format_selector(self, quality: int) -> str:
        return build_social_format(quality)

    def ytdlp_options(self, quality: int, attempt: int) -> dict:
        return {
            "extractor_args": tiktok_extractor_args(attempt),
            "http_headers": {
                "User-Agent": BROWSER_USER_AGENT,
                "Referer": "https://www.tiktok.com/",
                "Accept-Language": "en-US,en;q=0.9",
            },
        }


@dataclass(frozen=True)
class InstagramPolicy(PlatformPolicy):
    name: str = "instagram"
    domains: tuple[str, ...] = ("instagram.com",)
    requires_video_and_audio: bool = True

    def normalize_url(self, url: str) -> str:
        parsed = urlsplit(url)
        path = parsed.path.rstrip("/") + "/"
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    def format_selector(self, quality: int) -> str:
        return build_social_format(quality)

    def use_cookies(self, attempt: int) -> bool:
        return attempt != 2

    def ytdlp_options(self, quality: int, attempt: int) -> dict:
        return {
            "http_headers": {
                "User-Agent": BROWSER_USER_AGENT,
                "Referer": "https://www.instagram.com/",
                "Accept-Language": "en-US,en;q=0.9",
                "X-IG-App-ID": "936619743392459",
            }
        }


PLATFORM_POLICIES = (YouTubePolicy(), TikTokPolicy(), InstagramPolicy())
GENERIC_POLICY = PlatformPolicy()


def get_platform_policy(url: str) -> PlatformPolicy:
    return next((policy for policy in PLATFORM_POLICIES if policy.matches(url)), GENERIC_POLICY)


def normalize_url(url: str) -> str:
    return get_platform_policy(url).normalize_url(url)


def build_format(url: str, quality: int) -> str:
    return get_platform_policy(url).format_selector(quality)
