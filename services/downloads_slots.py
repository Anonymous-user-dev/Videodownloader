from dependencies.redis import redis_client

MAX_ACTIVE = 2
EXPIRE = 1800


async def acquire_slot(user_id: int) -> bool:
    key = f"active_downloads:{user_id}"

    async with redis_client.pipeline() as pipe:
        while True:
            try:
                await pipe.watch(key)

                current = await redis_client.get(key)
                current = int(current) if current else 0

                if current >= MAX_ACTIVE:
                    await pipe.unwatch()
                    return False

                pipe.multi()
                pipe.incr(key)
                pipe.expire(key, EXPIRE)

                await pipe.execute()
                return True

            except Exception:
                continue
def release_slot(user_id: int):
    key = f"active_downloads:{user_id}"

    current = redis_client.decr(key)

    if current <= 0:
        redis_client.delete(key)