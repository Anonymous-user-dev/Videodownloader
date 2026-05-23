# services/rate_limiter.py

import time
import redis.asyncio as redis
from redis.exceptions import WatchError

from dependencies.redis import redis_client

# =========================
# REDIS
# =========================


# =========================
# CONFIG
# =========================

CAPACITY = 5
# max burst requests

REFILL_RATE = 1 / 20
# 1 token every 20 sec

EXPIRE_TIME = 3600

MAX_RETRIES = 5

# =========================
# TOKEN BUCKET
# =========================


async def check_rate_limit(user_id: int):
    key = f"ratelimit:{user_id}"

    for _ in range(MAX_RETRIES):

        try:
            async with redis_client.pipeline() as pipe:

                # =========================
                # WATCH KEY
                # =========================

                await pipe.watch(key)

                # =========================
                # GET DATA
                # =========================

                data = await pipe.hmget(key,["tokens", "last_refill"])

                now = time.time()

                tokens = data[0]
                last_refill = data[1]

                # first request
                if tokens is None:
                    tokens = CAPACITY
                    last_refill = now

                else:
                    tokens = float(tokens)
                    last_refill = float(last_refill)

                # =========================
                # REFILL TOKENS
                # =========================

                elapsed = now - last_refill

                refill = elapsed * REFILL_RATE

                tokens = min(
                    CAPACITY,
                    tokens + refill
                )

                # =========================
                # BLOCK REQUEST
                # =========================

                if tokens < 1:

                    retry_after = int(
                        (1 - tokens) / REFILL_RATE
                    )

                    await pipe.reset()

                    return False, retry_after

                # consume token
                tokens -= 1

                # =========================
                # TRANSACTION
                # =========================

                pipe.multi()

                await pipe.hset(
                    key,
                    mapping={
                        "tokens": tokens,
                        "last_refill": now,
                    }
                )

                await pipe.expire(
                    key,
                    EXPIRE_TIME
                )

                await pipe.execute()

                return True, 0

        except WatchError:
            # another request modified key
            # retry transaction
            continue

    # fallback protection
    return False, 5