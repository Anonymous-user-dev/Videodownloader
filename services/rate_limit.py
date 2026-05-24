# services/rate_limiter.py

import time
from redis.exceptions import WatchError

from dependencies.redis import redis_client


CAPACITY = 5

REFILL_RATE = 1 / 20

EXPIRE_TIME = 3600

MAX_RETRIES = 5

async def check_rate_limit(user_id: int):
    key = f"ratelimit:{user_id}"

    for _ in range(MAX_RETRIES):

        try:
            async with redis_client.pipeline() as pipe:

                await pipe.watch(key)

                data = await pipe.hmget(key,["tokens", "last_refill"])

                now = time.time()

                tokens = data[0]
                last_refill = data[1]

                if tokens is None:
                    tokens = CAPACITY
                    last_refill = now

                else:
                    tokens = float(tokens)
                    last_refill = float(last_refill)

                elapsed = now - last_refill

                refill = elapsed * REFILL_RATE

                tokens = min(CAPACITY, tokens + refill)

                if tokens < 1:

                    retry_after = int((1 - tokens) / REFILL_RATE)

                    await pipe.reset()

                    return False, retry_after
                tokens -= 1

                pipe.multi()

                await pipe.hset(
                    key, mapping={
                        "tokens": tokens,
                        "last_refill": now,
                    }
                )

                await pipe.expire(key, EXPIRE_TIME)

                await pipe.execute()

                return True, 0

        except WatchError:
            #retry
            continue

    # fallback
    return False, 5