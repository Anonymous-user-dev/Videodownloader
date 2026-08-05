from pathlib import Path

import yaml


BLUEPRINT_PATH = Path(__file__).resolve().parent.parent / "render.yaml"


def test_render_blueprint_wires_required_services_and_dependencies() -> None:
    blueprint = yaml.safe_load(BLUEPRINT_PATH.read_text(encoding="utf-8"))
    services = {service["name"]: service for service in blueprint["services"]}

    web = services["videodownloader-service"]
    worker = services["videodownloader-worker"]
    redis = services["videodownloader-redis"]

    assert web["type"] == "web"
    assert web["healthCheckPath"] == "/health/ready"
    assert web["preDeployCommand"] == "alembic upgrade head"
    assert worker["type"] == "worker"
    assert "--concurrency=1" in worker["startCommand"]
    assert redis["type"] == "keyvalue"
    assert redis["persistenceMode"] == "off"
    assert blueprint["databases"][0]["name"] == "videodownloader-db"


def test_render_blueprint_does_not_commit_secret_values() -> None:
    blueprint = yaml.safe_load(BLUEPRINT_PATH.read_text(encoding="utf-8"))
    secret_keys = {"BOT_TOKEN", "WEBHOOK_URL", "WEBHOOK_SECRET", "RABBITMQ_HOST"}

    for service in blueprint["services"]:
        if service["type"] not in {"web", "worker"}:
            continue
        env_vars = {item["key"]: item for item in service["envVars"]}
        assert all(env_vars[key] == {"key": key, "sync": False} for key in secret_keys)
