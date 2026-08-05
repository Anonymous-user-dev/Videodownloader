from services.health import summarize_checks


def test_readiness_is_healthy_only_when_every_dependency_is_available() -> None:
    report, status_code = summarize_checks(
        {
            "database": True,
            "redis": True,
            "rabbitmq": True,
            "ffmpeg": True,
            "ffprobe": True,
            "node": True,
        }
    )

    assert status_code == 200
    assert report["status"] == "ready"
    assert set(report["checks"].values()) == {"ok"}


def test_readiness_failure_is_sanitized() -> None:
    report, status_code = summarize_checks(
        {"database": True, "redis": False, "rabbitmq": True}
    )

    assert status_code == 503
    assert report == {
        "status": "not_ready",
        "checks": {
            "database": "ok",
            "redis": "unavailable",
            "rabbitmq": "ok",
        },
    }
