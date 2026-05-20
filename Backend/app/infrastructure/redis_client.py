import redis
import redis.asyncio as aioredis
from core.config import settings

pool = redis.ConnectionPool(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD,
    decode_responses=False 
)

redis_conn = redis.Redis(connection_pool=pool)

async_pool = aioredis.ConnectionPool(host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD,
    decode_responses=False)
async_redis_conn = aioredis.Redis(connection_pool=async_pool)