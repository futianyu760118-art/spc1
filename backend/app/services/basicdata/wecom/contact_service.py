import asyncio
import time
from typing import Optional

from app.services.basicdata.wecom.client import get_wecom_client

_USER_CACHE_TTL = 600
_DEPT_CACHE_TTL = 600

_users_cache: tuple[float, list[dict]] | None = None
_depts_cache: tuple[float, list[dict]] | None = None
_cache_lock = asyncio.Lock()


async def _load_all_departments() -> list[dict]:
    client = get_wecom_client()
    departments = await client.list_departments()
    out: list[dict] = []
    for d in departments:
        out.append(
            {
                "id": int(d.get("id") or 0),
                "parent_id": int(d.get("parentid") or 0),
                "name": d.get("name", ""),
                "order": d.get("order", 0),
            }
        )
    return out


async def _load_all_users() -> list[dict]:
    client = get_wecom_client()
    departments = await client.list_departments()
    root_id = 1
    if departments:
        root_id = int(departments[0]["id"])
    # 一次调用拉全量成员（fetch_child=1 递归子部门），避免逐部门多次往返
    raw = await client.list_users(department_id=root_id, fetch_child=1)
    seen: set[str] = set()
    out: list[dict] = []
    for u in raw:
        uid = u.get("userid")
        if not uid or uid in seen:
            continue
        seen.add(uid)
        out.append(
            {
                "userid": uid,
                "name": u.get("name", ""),
                "department": u.get("department", []),
            }
        )
    return out


async def list_wecom_users(keyword: Optional[str] = None) -> list[dict]:
    global _users_cache
    now = time.time()
    if _users_cache and _users_cache[0] > now:
        users = _users_cache[1]
    else:
        async with _cache_lock:
            if _users_cache and _users_cache[0] > now:
                users = _users_cache[1]
            else:
                users = await _load_all_users()
                _users_cache = (now + _USER_CACHE_TTL, users)
    if keyword:
        kw = keyword.lower()
        return [u for u in users if kw in u["userid"].lower() or kw in u["name"].lower()]
    return users


async def list_wecom_departments() -> list[dict]:
    global _depts_cache
    now = time.time()
    if _depts_cache and _depts_cache[0] > now:
        return _depts_cache[1]
    async with _cache_lock:
        if _depts_cache and _depts_cache[0] > now:
            return _depts_cache[1]
        departments = await _load_all_departments()
        _depts_cache = (now + _DEPT_CACHE_TTL, departments)
        return departments


def invalidate_cache() -> None:
    global _users_cache, _depts_cache
    _users_cache = None
    _depts_cache = None
