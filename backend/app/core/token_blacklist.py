import redis.asyncio as redis
from app.core.config import get_settings

settings = get_settings()

TOKEN_BLACKLIST_PREFIX = "token:blacklist:"
BLACKLIST_TTL = 60 * 60 * 24


async def get_redis_client():
    try:
        client = redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
        return client
    except Exception:
        return None


async def add_token_to_blacklist(jti: str) -> bool:
    client = await get_redis_client()
    if not client:
        return False
    try:
        await client.setex(f"{TOKEN_BLACKLIST_PREFIX}{jti}", BLACKLIST_TTL, "1")
        return True
    except Exception:
        return False
    finally:
        try:
            await client.aclose()
        except Exception:
            pass


async def is_token_blacklisted(jti: str) -> bool:
    client = await get_redis_client()
    if not client:
        return False
    try:
        result = await client.exists(f"{TOKEN_BLACKLIST_PREFIX}{jti}")
        return result > 0
    except Exception:
        return False
    finally:
        try:
            await client.aclose()
        except Exception:
            pass