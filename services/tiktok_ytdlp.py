import random


API_HOSTNAMES = [
    "api16-normal-c-useast1a.tiktokv.com",
    "api19-normal-c-useast1a.tiktokv.com",
    "api22-normal-c-useast1a.tiktokv.com",
]

APP_INFO_PROFILES = [
    ("musical_ly", "35.1.3", "2023501030", "0"),
    ("musical_ly", "34.5.5", "2023405050", "0"),
    ("musical_ly", "33.9.5", "2023309050", "0"),
    ("trill", "35.1.3", "2023501030", "1180"),
]


def random_device_id() -> str:
    return str(random.randint(7250000000000000000, 7325099899999994577))


def app_info(profile_index: int = 0) -> str:
    app_name, app_version, manifest_version, aid = APP_INFO_PROFILES[
        profile_index % len(APP_INFO_PROFILES)
    ]
    return f"{random_device_id()}/{app_name}/{app_version}/{manifest_version}/{aid}"


def tiktok_extractor_args(attempt: int = 1) -> dict:
    profile_index = max(attempt - 1, 0)
    return {
        "tiktok": {
            "api_hostname": [
                API_HOSTNAMES[profile_index % len(API_HOSTNAMES)],
            ],
            "app_info": [
                app_info(profile_index),
                app_info(profile_index + 1),
            ],
            "device_id": [
                random_device_id(),
            ],
        }
    }
