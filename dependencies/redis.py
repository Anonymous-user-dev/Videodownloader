import redis

pool = redis.ConnectionPool(host='localhost', port=6379, decode_responses=True, max_connections=10)

red = redis.Redis(connection_pool=pool)