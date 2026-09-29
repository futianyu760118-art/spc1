"""审批链纯函数（快照构建/条件匹配/审批人解析）——供审批中心服务复用。

审批链来源: approval_config 表（biz_type），提交时冻结快照；节点支持按单据字段条件过滤。
"""

import json
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def check_node_permission(node: dict, approver: str, approver_role: str) -> tuple[bool, str]:
    """校验当前用户是否有权操作该审批节点。优先 approvers（动态解析），其次固定 role；admin 旁路。"""
    if approver_role == "admin":
        return True, ""
    approvers = node.get("approvers")
    if approvers is not None:
        if approvers:
            matched = any(approver == a.get("username") or approver == str(a.get("user_id")) for a in approvers)
            if matched:
                return True, ""
            names = ", ".join(a.get("username", "?") for a in approvers)
            return False, f"当前级别 [{node.get('label')}] 需 {names} 审批，您无权操作"
        return False, f"当前级别 [{node.get('label')}] 审批人解析失败，请联系管理员"
    required_role = node.get("role")
    if required_role and approver_role != required_role:
        return False, f"当前级别 [{node.get('label')}] 需角色 {required_role} 审批，您的角色（{approver_role or '未知'}）无权操作"
    return True, ""


def cond_match(cond: Optional[dict], fields: dict) -> bool:
    """节点条件匹配。op 支持 in/>=/<=/>/</==/!=，数值比较失败视为不匹配。"""
    if not cond or not cond.get("field"):
        return True
    val = fields.get(cond.get("field"))
    op = cond.get("op", "in")
    target = cond.get("value")
    if op == "in":
        if isinstance(target, str):
            target = [v.strip() for v in target.split(",") if v.strip()]
        return val in (target or [])
    try:
        val_n = float(val)
        t = float(target)
    except (TypeError, ValueError):
        return False
    return {
        ">=": val_n >= t, "<=": val_n <= t, ">": val_n > t,
        "<": val_n < t, "==": val_n == t, "!=": val_n != t,
    }[op]


def conditions_match(node: Optional[dict], fields: dict) -> bool:
    """节点触发条件：优先 conditions 数组（AND），兼容历史单条件 condition。"""
    if not node:
        return True
    conds = node.get("conditions")
    if conds:
        return all(cond_match(c, fields) for c in conds)
    return cond_match(node.get("condition"), fields)


async def build_chain_snapshot(db: AsyncSession, biz_type: str, fields: dict) -> list[dict]:
    """读 approval_config 解析审批链快照（按条件过滤 + 重排 seq 为连续 1..n），不写库。"""
    r2 = await db.execute(
        text("SELECT nodes FROM approval_config WHERE biz_type = :bt AND is_active = TRUE"),
        {"bt": biz_type},
    )
    row = r2.fetchone()
    if not row:
        return []
    all_nodes = json.loads(row[0]) if isinstance(row[0], str) else (row[0] or [])
    snapshot = []
    for node in all_nodes:
        if not conditions_match(node, fields):
            continue
        snap_node = {"seq": node.get("seq"), "label": node.get("label"), "role": node.get("role")}
        if node.get("approvers"):
            snap_node["approvers"] = node["approvers"]
        # 0 = 不提醒，必须与「未配置」区分，故显式判 None
        if node.get("timeout_hours") is not None:
            try:
                snap_node["timeout_hours"] = int(node["timeout_hours"])
            except (TypeError, ValueError):
                # 历史脏数据：忽略该配置，按「未配置」处理（列表侧回退默认阈值）
                logger.warning("审批链节点 timeout_hours 非法 biz=%s value=%r", biz_type, node.get("timeout_hours"))
        snapshot.append(snap_node)
    # 条件过滤会移除中间节点导致 seq 断档，引擎按 seq+1 找下一节点，必须重排为连续 1..n
    for i, node in enumerate(snapshot, 1):
        node["seq"] = i
    return snapshot


async def resolve_node_approver_user_ids(db: AsyncSession, node: Optional[dict]) -> list[int]:
    """节点审批人的用户 ID 列表：approvers 优先（取 user_id），否则按角色查启用用户。

    非数字 user_id 视为脏数据跳过，避免一条历史配置让待办列表整体 500。
    """
    if not node:
        return []
    approvers = node.get("approvers")
    if approvers is not None:
        result = []
        for a in approvers:
            try:
                result.append(int(a["user_id"]))
            except (TypeError, ValueError, KeyError):
                continue
        return result
    role = node.get("role")
    if not role or db is None:
        return []
    rows = await db.execute(text("""
        SELECT u.id FROM sys_user u
        JOIN sys_role r ON u.role_id = r.id
        WHERE r.role_code = :rc AND u.is_active = TRUE
    """), {"rc": role})
    return [r[0] for r in rows if r[0]]


async def resolve_node_approver_usernames(db: AsyncSession, node: Optional[dict]) -> set[str]:
    """节点审批人 username 集合：approvers 优先，否则按角色查启用用户（username 与 user_id 字符串都算）。"""
    approvers = (node or {}).get("approvers")
    if approvers is not None:
        result = set()
        for a in approvers:
            if a.get("username"):
                result.add(a["username"])
            if a.get("user_id"):
                result.add(str(a["user_id"]))
        return result
    role = (node or {}).get("role")
    if not role:
        return set()
    rows = await db.execute(text("""
        SELECT u.username, u.id FROM sys_user u
        JOIN sys_role r ON u.role_id = r.id
        WHERE r.role_code = :rc AND u.is_active = TRUE
    """), {"rc": role})
    result = set()
    for r in rows:
        if r[0]:
            result.add(r[0])
        result.add(str(r[1]))
    return result
