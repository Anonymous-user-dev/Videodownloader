import redis

pool = redis.ConnectionPool(host='localhost', port=6379, decode_responses=True, max_connections=10)

redis_client = redis.Redis(connection_pool=pool)