from services.downloader import (
    build_quality_ladder,
    build_social_format,
    build_youtube_format,
    is_video_quality_too_low,
    normalize_url,
)


def test_normalize_instagram_url_removes_tracking_query() -> None:
    assert normalize_url("https://www.instagram.com/reel/ABC123/?igsh=secret") == (
        "https://www.instagram.com/reel/ABC123/"
    )


def test_normalize_tiktok_canonical_url_removes_query() -> None:
    assert normalize_url("https://www.tiktok.com/@creator/video/123?lang=en") == (
        "https://www.tiktok.com/@creator/video/123"
    )


def test_quality_ladder_falls_back_without_duplicates() -> None:
    assert build_quality_ladder(1080) == [1080, 720, 480]
    assert build_quality_ladder(720) == [720, 480]
    assert build_quality_ladder(480) == [480]


def test_quality_ladder_caps_untrusted_input() -> None:
    assert build_quality_ladder(2160) == [1080, 720, 480]


def test_portrait_video_uses_short_edge_as_visible_resolution() -> None:
    assert not is_video_quality_too_low(480, 480, 854)
    assert is_video_quality_too_low(720, 360, 640)


def test_platform_formats_require_video_and_audio_before_fallback() -> None:
    social_format = build_social_format(720)
    youtube_format = build_youtube_format(1080)

    assert social_format.startswith("best*[vcodec!=none][acodec!=none]")
    assert "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]" in youtube_format
