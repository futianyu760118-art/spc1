"""执行面 actor token：短时身份凭证，只证明 user/agent，不携带数据。"""

from datetime import timedelta

from fastapi import HTTPException

from app.core.security import create_access_token, decode_access_token

ACTOR_TTL = timedelta(minutes=5)
ACTOR_TYPE = "agent_actor"


def issue_actor_token(*, user_id: int, agent_id: int, username: str = "", role: str = "") -> str:
    return create_access_token(
        {
            "sub": str(user_id),
            "agent_id": int(agent_id),
            "typ": ACTOR_TYPE,
            "username": username,
            "role": role,
        },
        expires_delta=ACTOR_TTL,
    )


def decode_actor_token(token: str) -> dict:
    payload = decode_access_token(token)
    if payload.get("typ") != ACTOR_TYPE:
        raise HTTPException(status_code=401, detail="无效的 actor token 类型")
    if not payload.get("sub") or not payload.get("agent_id"):
        raise HTTPException(status_code=401, detail="actor token 缺少身份信息")
    try:
        payload["agent_id"] = int(payload["agent_id"])
        payload["user_id"] = int(payload["sub"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="actor token 身份信息非法")
    return payload
