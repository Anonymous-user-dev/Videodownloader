import redis as redis
from config import settings

pool = redis.ConnectionPool(host=settings.REDIS_HOST, port=settings.REDIS_PORT, decode_responses=True, max_connections=10)

redis_client = redis.Redis(connection_pool=pool)