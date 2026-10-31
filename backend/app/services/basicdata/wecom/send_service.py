from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.basicdata.share_link import ShareLink
from app.models.basicdata.share_link_recipient import ShareLinkRecipient
from app.models.basicdata.permission import SysPermission
from app.models.basicdata.user import SysUser
from app.services.basicdata.wecom.client import get_wecom_client
from app.services.basicdata.wecom.exceptions import WecomAPIError, WecomNotConfiguredError

_PERMISSION_LABELS = {
    "read": "查看",
    "create": "新增",
    "update": "修改",
    "delete": "删除",
}


@dataclass
class RecipientSpec:
    id: str
    name: str = ""


@dataclass
class WecomPushResult:
    success: int = 0
    failed: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"success": self.success, "failed": self.failed}


async def _creator_display_name(db: AsyncSession, user_id: int) -> str:
    if not user_id:
        return ""
    result = await db.execute(
        select(SysUser.display_name, SysUser.username).where(SysUser.id == int(user_id))
    )
    row = result.first()
    if not row:
        return str(user_id)
    return row[0] or row[1] or str(user_id)


def _permissions_text(permissions) -> str:
    if not permissions:
        return "查看"
    labels = [_PERMISSION_LABELS.get(p, p) for p in permissions]
    return "、".join(labels) or "查看"


def _expires_text(expires_at) -> str:
    if not expires_at:
        return "永久有效"
    remaining = expires_at - datetime.now(timezone.utc)
    days = remaining.days
    if days < 0:
        return "已过期"
    if days == 0:
        return "今天到期"
    return f"{days} 天后到期"


async def _page_name(db: AsyncSession, target_path: str | None) -> str | None:
    """根据 route_path 反查页面名称，找不到返回 None"""
    if not target_path:
        return None
    result = await db.execute(
        select(SysPermission.name).where(
            SysPermission.route_path == target_path,
            SysPermission.is_active == True,  # noqa: E712
        )
    )
    name = result.scalars().first()
    return name


async def _build_textcard(db: AsyncSession, share_link: ShareLink, share_url: str) -> dict:
    title = "页面分享"
    creator = await _creator_display_name(db, getattr(share_link, "created_by", None) or 0)
    page = await _page_name(db, getattr(share_link, "target_path", None))
    parts: list[str] = []
    if creator:
        parts.append(f"发起人：{creator}")
    if page:
        parts.append(f"页面：{page}")
    reason = getattr(share_link, "reason", None)
    if reason:
        parts.append(f"分享原因：{reason}")
    parts.append(f"权限：{_permissions_text(share_link.permissions)}")
    parts.append(f"有效期：{_expires_text(getattr(share_link, 'expires_at', None))}")
    description = "\n".join(parts)
    return {"title": title, "description": description, "url": share_url, "btntxt": "查看详情"}


async def push_share_link(
    db: AsyncSession,
    share_link: ShareLink,
    recipients: list[RecipientSpec],
    share_url: str,
) -> WecomPushResult:
    """按批发送到企业微信应用，每次失败独立记录。"""
    if not recipients:
        return WecomPushResult()

    client = get_wecom_client()
    settings = client._settings
    agent_id = int(settings.wecom_agent_id or 0)

    textcard = await _build_textcard(db, share_link, share_url)
    result = WecomPushResult()
    rows: list[ShareLinkRecipient] = []

    BATCH = 1000
    for i in range(0, len(recipients), BATCH):
        batch = recipients[i:i + BATCH]
        payload = {
            "touser": "|".join([r.id for r in batch]),
            "msgtype": "textcard",
            "agentid": agent_id,
            "textcard": textcard,
        }
        try:
            resp = await client.send_app_message(payload)
            errcode = resp.get("errcode", 0)
            msgid = resp.get("msgid")
            if errcode == 0:
                for r in batch:
                    rows.append(_row(share_link.id, r, True, msgid, None))
                    result.success += 1
            else:
                err = f"errcode={errcode} {resp.get('errmsg','')}"
                for r in batch:
                    rows.append(_row(share_link.id, r, False, None, err))
                    result.failed.append({"recipient_id": r.id, "error_msg": err})
        except (WecomAPIError, WecomNotConfiguredError) as e:
            err = str(e)
            for r in batch:
                rows.append(_row(share_link.id, r, False, None, err))
                result.failed.append({"recipient_id": r.id, "error_msg": err})

    if rows:
        db.add_all(rows)
        await db.flush()
    return result


def _row(link_id: int, r: RecipientSpec, ok: bool, msgid: str | None, err: str | None) -> ShareLinkRecipient:
    return ShareLinkRecipient(
        share_link_id=link_id,
        recipient_type="user",
        recipient_id=r.id,
        recipient_name=r.name,
        delivered=ok,
        delivered_at=datetime.utcnow() if ok else None,
        wecom_msg_id=msgid,
        error_msg=err,
    )
