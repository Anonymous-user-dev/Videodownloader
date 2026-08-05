import logging
import time

from redis.exceptions import WatchError

from dependencies.redis import redis_client

logger = logging.getLogger(__name__)

CAPACITY = 5
REFILL_RATE = 1 / 20
EXPIRE_TIME = 3600
MAX_RETRIES = 5


def calculate_token_state(
    tokens: float | None,
    last_refill: float | None,
    now: float,
) -> tuple[bool, float, int]:
    """Refill and consume one token without performing any Redis I/O."""
    if tokens is None or last_refill is None:
        available_tokens = float(CAPACITY)
    else:
        elapsed = max(0.0, now - last_refill)
        available_tokens = min(CAPACITY, float(tokens) + elapsed * REFILL_RATE)

    if available_tokens < 1:
        retry_after = max(1, int((1 - available_tokens) / REFILL_RATE))
        return False, available_tokens, retry_after

    return True, available_tokens - 1, 0


async def check_rate_limit(user_id: int) -> tuple[bool, int]:
    key = f"ratelimit:{user_id}"

    for _ in range(MAX_RETRIES):
        try:
            async with redis_client.pipeline() as pipe:
                await pipe.watch(key)
                tokens, last_refill = await pipe.hmget(key, ["tokens", "last_refill"])
                now = time.time()

                allowed, tokens, retry_after = calculate_token_state(
                    float(tokens) if tokens is not None else None,
                    float(last_refill) if last_refill is not None else None,
                    now,
                )

                if not allowed:
                    await pipe.reset()
                    return False, retry_after

                pipe.multi()
                await pipe.hset(
                    key,
                    mapping={
                        "tokens": tokens,
                        "last_refill": now,
                    },
                )
                await pipe.expire(key, EXPIRE_TIME)
                await pipe.execute()

                return True, 0

        except WatchError:
            logger.warning("Rate-limit state changed concurrently; retrying")

    logger.error("Rate-limit update failed after %s retries", MAX_RETRIES)
    return False, 5
