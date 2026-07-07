"""用户权限 payload 缓存 — 减轻 PermissionChecker 每次请求查库的负担

缓存内容：role_code / supplier_name / supplier_code / oa_user_id / org_scope_ids / login_version
缓存粒度：按 user_id + login_version（重新登录会 bump login_version，自动失效旧缓存）
TTL：5 分钟（兜底，即使 login_version 失效机制出问题也不会缓存太久）
"""
import json
import redis.asyncio as redis
from app.core.config import get_settings

settings = get_settings()

PAYLOAD_CACHE_PREFIX = "perm:payload:"
PAYLOAD_CACHE_TTL = 5 * 60  # 5 分钟


async def _get_redis():
    try:
        return redis.from_url(settings.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
    except Exception:
        return None


def _cache_key(user_id: int, login_version: int) -> str:
    return f"{PAYLOAD_CACHE_PREFIX}{user_id}:v{login_version}"


async def get_cached_user_payload(user_id: int, login_version: int) -> dict | None:
    """读取缓存的用户 payload（不含 permissions，permissions 单独查）。返回 None 表示未命中。"""
    client = await _get_redis()
    if not client:
        return None
    try:
        raw = await client.get(_cache_key(user_id, login_version))
        if not raw:
            return None
        return json.loads(raw)
    except Exception:
        return None
    finally:
        try:
            await client.aclose()
        except Exception:
            pass


async def set_cached_user_payload(user_id: int, login_version: int, payload: dict) -> None:
    """写入用户 payload 缓存"""
    client = await _get_redis()
    if not client:
        return
    try:
        # org_scope_ids 是 set，需要转 list 才能序列化
        safe = dict(payload)
        if isinstance(safe.get("org_scope_ids"), set):
            safe["org_scope_ids"] = list(safe["org_scope_ids"])
        await client.setex(_cache_key(user_id, login_version), PAYLOAD_CACHE_TTL, json.dumps(safe, default=str))
    except Exception:
        pass
    finally:
        try:
            await client.aclose()
        except Exception:
            pass


async def invalidate_user_payload(user_id: int) -> None:
    """主动失效某用户的所有版本缓存（扫前缀）"""
    client = await _get_redis()
    if not client:
        return
    try:
        # 扫所有版本 key（不同 login_version 的）
        pattern = f"{PAYLOAD_CACHE_PREFIX}{user_id}:v*"
        async for key in client.scan_iter(match=pattern, count=100):
            await client.delete(key)
    except Exception:
        pass
    finally:
        try:
            await client.aclose()
        except Exception:
            pass
