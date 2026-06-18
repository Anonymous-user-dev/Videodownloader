import redis as redis
from config import settings

pool = redis.ConnectionPool.from_url(url=settings.REDIS_HOST, decode_responses=True, max_connections=10)

redis_client = redis.Redis(connection_pool=pool)

