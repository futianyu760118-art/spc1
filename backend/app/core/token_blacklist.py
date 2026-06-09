import redis.asyncio as redis
from app.core.config import get_settings

settings = get_settings()

TOKEN_BLACKLIST_PREFIX = "token:blacklist:"
BLACKLIST_TTL = 60 * 60 * 24


async def get_redis_client():
    client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return client


async def add_token_to_blacklist(jti: str) -> bool:
    client = await get_redis_client()
    try:
        await client.setex(f"{TOKEN_BLACKLIST_PREFIX}{jti}", BLACKLIST_TTL, "1")
        return True
    finally:
        await client.aclose()


async def is_token_blacklisted(jti: str) -> bool:
    client = await get_redis_client()
    try:
        result = await client.exists(f"{TOKEN_BLACKLIST_PREFIX}{jti}")
        return result > 0
    finally:
        await client.aclose()