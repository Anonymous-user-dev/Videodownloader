from dependencies.redis_sync import redis_client

MAX_ACTIVE = 3
EXPIRE = 1800


def acquire_slot(user_id: int) -> bool:
    key = f"active_downloads:{user_id}"

    current = redis_client.incr(key)

    # set expiry only on first slot
    if current == 1:
        redis_client.expire(key, EXPIRE)

    if current > MAX_ACTIVE:
        redis_client.decr(key)
        return False

    return True


def release_slot(user_id: int):
    key = f"active_downloads:{user_id}"

    current = redis_client.decr(key)

    if current <= 0:
        redis_client.delete(key)