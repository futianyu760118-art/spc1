"""审批中心 - 领域服务：实例生命周期 / 任务展开 / 流水 / 回写 / 通知。

数据落点为中心三表（approval_instance / approval_task / approval_record）。
业务侧同步（builtin Adapter.on_transition / 声明式 writeback 配置）与审批动作
在同一事务内执行：回写失败则整体回滚，保证强一致（无异步漂移）。
"""

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.common.approval_adapters import adapter_instance
from app.services.common.approval_engine import (
    build_chain_snapshot, check_node_permission, resolve_node_approver_usernames,
)
from app.services.common.approval_metrics import enrich_pending_item
from app.services.common.approval_notify import send_approval_wecom_textcard
from app.services.common.approval_sql import IDENTIFIER_RE, execute_readonly_sql, pick_mapped_value, render_deep_link

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = ("approved", "rejected", "recalled")
ACTION_LABELS = {"submit": "提交", "approve": "通过", "reject": "驳回", "recall": "撤回",
                 "auto_skip": "自动通过", "revoked": "已撤回"}


def _loads(raw, default):
    if not raw:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


class ApprovalCenterService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- 业务元数据（builtin Adapter ∪ 声明式 approval_business 行） ----------

    async def biz_meta(self, biz_type: str) -> Optional[dict]:
        """统一业务元数据：{biz_name, mode(builtin|sql), is_active, deep_link_template,
        condition_field_options, sql_text, field_mapping, writeback}。未接入返回 None。"""
        from app.services.common.approval_adapters import get_adapter_class
        cls = get_adapter_class(biz_type)
        if cls is not None:
            return {"biz_type": biz_type, "biz_name": cls.biz_name, "mode": "builtin",
                    "is_active": True, "deep_link_template": cls.deep_link_template,
                    "condition_field_options": cls.condition_field_options or [],
                    "sql_text": None, "field_mapping": None, "writeback": None}
        row = (await self.db.execute(
            text("SELECT biz_type, biz_name, is_active, deep_link_template, condition_fields_json,"
                 " sql_text, field_mapping_json, writeback_json FROM approval_business WHERE biz_type = :bt LIMIT 1"),
            {"bt": biz_type},
        )).fetchone()
        if not row:
            return None
        d = dict(row._mapping)
        return {"biz_type": d["biz_type"], "biz_name": d["biz_name"] or d["biz_type"], "mode": "sql",
                "is_active": bool(d["is_active"]), "deep_link_template": d["deep_link_template"],
                "condition_field_options": _loads(d["condition_fields_json"], []),
                "sql_text": d["sql_text"], "field_mapping": _loads(d["field_mapping_json"], {}),
                "writeback": _loads(d["writeback_json"], {})}

    async def list_biz_metas(self) -> list[dict]:
        """业务清单：builtin Adapter + 表内 SQL 业务（含停用，便于重新启用）。"""
        from app.services.common.approval_adapters import get_adapter_classes
        metas = []
        for cls in get_adapter_classes():
            metas.append({"biz_type": cls.biz_type, "biz_name": cls.biz_name, "mode": "builtin",
                          "is_active": True, "deep_link_template": cls.deep_link_template,
                          "condition_field_options": cls.condition_field_options or [],
                          "sql_text": None, "field_mapping": None, "writeback": None})
        rows = await self.db.execute(text(
            "SELECT biz_type, biz_name, is_active, deep_link_template, condition_fields_json,"
            " sql_text, field_mapping_json, writeback_json FROM approval_business ORDER BY id"))
        for r in rows:
            d = dict(r._mapping)
            metas.append({"biz_type": d["biz_type"], "biz_name": d["biz_name"] or d["biz_type"],
                          "mode": "sql", "is_active": bool(d["is_active"]),
                          "deep_link_template": d["deep_link_template"],
                          "condition_field_options": _loads(d["condition_fields_json"], []),
                          "sql_text": d["sql_text"], "field_mapping": _loads(d["field_mapping_json"], {}),
                          "writeback": _loads(d["writeback_json"], {})})
        return metas

    # ---------- 实例读写 ----------

    async def _instance_by_biz(self, biz_type: str, biz_id: int) -> Optional[dict]:
        row = (await self.db.execute(
            text("SELECT * FROM approval_instance WHERE biz_type = :bt AND biz_id = :bid LIMIT 1"),
            {"bt": biz_type, "bid": biz_id},
        )).fetchone()
        return dict(row._mapping) if row else None

    async def _instance_row(self, instance_id: int) -> dict:
        row = (await self.db.execute(
            text("SELECT * FROM approval_instance WHERE id = :iid LIMIT 1"), {"iid": instance_id}
        )).fetchone()
        return dict(row._mapping)

    async def _add_record(self, instance_id: int, action: str, node_seq, operator: str, comment: str):
        await self.db.execute(text(
            "INSERT INTO approval_record (instance_id, action, node_seq, operator, comment)"
            " VALUES (:iid, :ac, :lv, :op, :cm)"),
            {"iid": instance_id, "ac": action, "lv": node_seq, "op": operator, "cm": comment})

    # ---------- 提交 ----------

    async def submit(self, biz_type: str, biz_id: int, applicant: str) -> dict:
        meta = await self.biz_meta(biz_type)
        if not meta:
            raise ValueError("该业务流程未接入审批中心")
        if not meta["is_active"]:
            raise ValueError("该业务已停用，无法提交审批")
        adapter = adapter_instance(self.db, biz_type)
        payload = await self._submit_payload(biz_type, biz_id, adapter, meta)
        applicant = str(payload.get("applicant") or applicant or "").strip()
        if not applicant:
            raise ValueError("申请人不能为空")
        inst = await self._instance_by_biz(biz_type, biz_id)
        if inst and inst["status"] not in TERMINAL_STATUSES:
            raise ValueError("该单据已在审批中，不能重复提交")
        snapshot = await build_chain_snapshot(self.db, biz_type, dict(payload.get("extra") or {}))
        if not snapshot:
            raise ValueError("审批链未配置或已停用，无法提交")
        now = datetime.now()
        amount = payload.get("amount")
        try:
            amount = float(amount) if amount is not None else None
        except (TypeError, ValueError):
            amount = None
        common = {"snap": json.dumps(snapshot, ensure_ascii=False), "now": now,
                  "no": payload.get("no") or str(biz_id), "t": payload.get("title") or "",
                  "s": payload.get("summary") or "", "ap": applicant, "amt": amount,
                  "extra": json.dumps(payload.get("extra") or {}, ensure_ascii=False, default=str),
                  "to": snapshot[0].get("timeout_hours")}
        if inst:
            result = await self.db.execute(text("""
                UPDATE approval_instance SET status='pending', current_level=1, snapshot_json=:snap,
                    timeout_hours=:to, version=version+1, submitted_at=:now, finished_at=NULL,
                    biz_no=:no, title=:t, summary=:s, applicant=:ap, amount=:amt, extra_json=:extra, updated_at=NOW()
                WHERE id=:iid AND status IN ('approved','rejected','recalled')
            """), {**common, "iid": inst["id"]})
            if result.rowcount == 0:
                raise ValueError("提交失败，单据状态已变化，请刷新后重试")
            iid = inst["id"]
        else:
            result = await self.db.execute(text("""
                INSERT INTO approval_instance
                    (biz_type, biz_id, biz_no, title, summary, applicant, amount, extra_json,
                     status, current_level, snapshot_json, timeout_hours, version, submitted_at)
                VALUES (:bt, :bid, :no, :t, :s, :ap, :amt, :extra, 'pending', 1, :snap, :to, 1, :now)
                RETURNING id
            """), {**common, "bt": biz_type, "bid": biz_id})
            iid = result.scalar_one()
        await self._add_record(iid, "submit", None, applicant, "提交审批")
        await self._activate_level(iid, 1, snapshot[0])
        await self._sync_business(await self._instance_row(iid))
        return {"success": True, "instance_id": iid}

    async def _submit_payload(self, biz_type: str, biz_id: int, adapter, meta: dict) -> dict:
        if adapter is not None:
            return await adapter.submit_payload(self.db, biz_id)
        # 声明式业务：按取数 SQL 定位目标行，生成实例摘要（id 必须在取数结果中）
        rows = await execute_readonly_sql(self.db, meta["sql_text"])
        mapping = meta["field_mapping"] or {}
        for row in rows:
            source_id = pick_mapped_value(row, mapping, "id")
            if source_id is not None and str(source_id) == str(biz_id):
                amount = pick_mapped_value(row, mapping, "amount")
                try:
                    amount = float(amount) if amount is not None else None
                except (TypeError, ValueError):
                    amount = None
                extra = {str(o.get("value")): row.get(str(o.get("value")))
                         for o in (meta["condition_field_options"] or []) if o.get("value")}
                return {"no": pick_mapped_value(row, mapping, "no"),
                        "title": pick_mapped_value(row, mapping, "title"),
                        "summary": pick_mapped_value(row, mapping, "summary"),
                        "applicant": pick_mapped_value(row, mapping, "applicant"),
                        "amount": amount, "extra": extra}
        raise ValueError("单据不存在或不在取数范围内，无法提交审批")

    # ---------- 节点激活（任务展开到人 + 通知） ----------

    async def _activate_level(self, instance_id: int, level: int, node: dict, notify: bool = True):
        usernames = await resolve_node_approver_usernames(self.db, node)
        if not usernames:
            logger.warning("[审批中心] 节点审批人解析为空 instance=%s level=%s", instance_id, level)
        for u in sorted(usernames):
            await self.db.execute(text(
                "INSERT INTO approval_task (instance_id, node_seq, node_label, role_code, approver, status)"
                " VALUES (:iid, :lv, :lb, :rc, :ap, 'active')"),
                {"iid": instance_id, "lv": level, "lb": node.get("label") or f"L{level}",
                 "rc": node.get("role"), "ap": u})
        if notify:
            await self._notify_level(instance_id, node)

    async def _notify_level(self, instance_id: int, node: dict):
        inst = await self._instance_row(instance_id)
        label = node.get("label") or f"L{inst['current_level']}"
        rows = await self.db.execute(text("""
            SELECT DISTINCT u.id FROM approval_task t
            JOIN sys_user u ON u.username = t.approver AND u.is_active = TRUE
            WHERE t.instance_id = :iid AND t.node_seq = :lv AND t.status = 'active'
        """), {"iid": instance_id, "lv": inst["current_level"]})
        uids = [r[0] for r in rows if r[0]]
        if not uids:
            return
        title = f"[{inst['biz_type']}] 待您审批 - {label}"
        content = (f"单据 {inst['biz_no'] or inst['biz_id']}（{inst['title'] or ''}，"
                   f"申请人：{inst['applicant']}）需要您{label}。")
        for uid in uids:
            await self._insert_notification(uid, title, content, "approval_pending",
                                            inst["biz_type"], inst["biz_id"])
        try:
            await send_approval_wecom_textcard(
                self.db, user_ids=uids, title="待您审批",
                description=f"{inst['biz_no'] or ''} {inst['title'] or ''}\n审批节点：{label}\n点击进入待办工作台处理。",
                path="/approvals/pending", btn_text="去处理")
        except Exception as exc:
            logger.warning("[审批中心] 企微通知失败 instance=%s: %s", instance_id, exc)

    async def _notify_applicant(self, inst: dict, title: str, content: str):
        row = (await self.db.execute(
            text("SELECT id FROM sys_user WHERE username = :a OR id::text = :a LIMIT 1"),
            {"a": str(inst["applicant"])},
        )).fetchone()
        if row:
            await self._insert_notification(row[0], title, content, "approval_result",
                                            inst["biz_type"], inst["biz_id"])

    async def _insert_notification(self, user_id: int, title: str, content: str,
                                   ntype: str, ref_type: str, ref_id: int):
        try:
            await self.db.execute(text("""
                INSERT INTO notification (user_id, type, title, content, ref_type, ref_id,
                                          sender_name, priority, is_read, created_at)
                VALUES (:uid, :ntype, :title, :content, :rt, :rid, '系统', 'high', FALSE, NOW())
            """), {"uid": user_id, "ntype": ntype, "title": title, "content": content,
                   "rt": ref_type, "rid": ref_id})
        except Exception as exc:
            logger.warning("[审批中心] 站内信失败 user_id=%s: %s", user_id, exc)
            return
        from app.services.notification.notification_broker import publish_unread_update
        await publish_unread_update(self.db, user_id)

    # ---------- 审批动作 ----------

    async def approve(self, biz_type: str, biz_id: int, operator: str, comment: str = "", *,
                      operator_role: str = "", expected_version: Optional[int] = None) -> dict:
        inst = await self._instance_by_biz(biz_type, biz_id)
        if not inst or inst["status"] != "pending":
            return {"success": False, "message": "状态不正确"}
        if expected_version is not None and int(expected_version) != int(inst["version"]):
            return {"success": False, "message": "数据已被他人更新，请刷新后重试"}
        snap = _loads(inst["snapshot_json"], [])
        level = inst["current_level"]
        node = next((n for n in snap if n.get("seq") == level), None)
        if not node:
            return {"success": False, "message": f"当前审批级别 {level} 在审批链中不存在"}
        ok, msg = check_node_permission(node, operator, operator_role)
        if not ok:
            return {"success": False, "message": msg}
        iid, now = inst["id"], datetime.now()
        await self._add_record(iid, "approve", level, operator, comment)
        await self.db.execute(text(
            "UPDATE approval_task SET status='approved', comment=:cm, acted_at=:now"
            " WHERE instance_id=:iid AND node_seq=:lv AND status='active' AND approver=:op"),
            {"cm": comment, "now": now, "iid": iid, "lv": level, "op": operator})
        await self.db.execute(text(
            "UPDATE approval_task SET status='skipped', acted_at=:now"
            " WHERE instance_id=:iid AND node_seq=:lv AND status='active' AND approver<>:op"),
            {"now": now, "iid": iid, "lv": level, "op": operator})

        # 推进：下一节点审批人含当前审批人，或其全部审批人已在更早节点审过 → 自动跳过（循环处理连续跳过）
        next_level, skipped = level + 1, []
        while True:
            next_node = next((n for n in snap if n.get("seq") == next_level), None)
            if not next_node:
                result = await self.db.execute(text("""
                    UPDATE approval_instance SET status='approved', finished_at=:now, version=version+1, updated_at=NOW()
                    WHERE id=:iid AND version=:v
                """), {"now": now, "iid": iid, "v": inst["version"]})
                if result.rowcount == 0:
                    return {"success": False, "message": "数据已被他人更新，请刷新后重试"}
                fresh = await self._instance_row(iid)
                meta = await self.biz_meta(biz_type)
                await self._notify_applicant(
                    fresh, f"[{meta['biz_name']}] 审批通过",
                    f"您的单据 {inst['biz_no'] or ''} 已全部审批通过，已归档。")
                await self._sync_business(fresh, approved_by=operator, approved_at=now)
                return {"success": True, "finished": True, "skipped": skipped}
            next_approvers = await resolve_node_approver_usernames(self.db, next_node)
            skip = operator in next_approvers
            if not skip and next_approvers:
                earlier = await self._earlier_approvers(iid, next_level) | {operator}
                if next_approvers.issubset(earlier):
                    skip = True
            if skip:
                await self._add_record(iid, "auto_skip", next_level, operator,
                                       "自动通过（审批人已在更早节点审过，避免重复审批）")
                skipped.append(next_level)
                next_level += 1
                continue
            break

        result = await self.db.execute(text(
            "UPDATE approval_instance SET current_level=:lv, timeout_hours=:to, version=version+1, updated_at=NOW()"
            " WHERE id=:iid AND version=:v"),
            {"lv": next_level, "to": next_node.get("timeout_hours"), "iid": iid, "v": inst["version"]})
        if result.rowcount == 0:
            return {"success": False, "message": "数据已被他人更新，请刷新后重试"}
        await self._activate_level(iid, next_level, next_node)
        await self._sync_business(await self._instance_row(iid))
        return {"success": True, "finished": False, "skipped": skipped}

    async def reject(self, biz_type: str, biz_id: int, operator: str, comment: str = "", *,
                     operator_role: str = "", expected_version: Optional[int] = None) -> dict:
        inst = await self._instance_by_biz(biz_type, biz_id)
        if not inst or inst["status"] != "pending":
            return {"success": False, "message": "状态不正确"}
        if expected_version is not None and int(expected_version) != int(inst["version"]):
            return {"success": False, "message": "数据已被他人更新，请刷新后重试"}
        snap = _loads(inst["snapshot_json"], [])
        level = inst["current_level"]
        node = next((n for n in snap if n.get("seq") == level), None) if snap else None
        if node:
            ok, msg = check_node_permission(node, operator, operator_role)
            if not ok:
                return {"success": False, "message": msg}
        iid, now = inst["id"], datetime.now()
        await self._add_record(iid, "reject", level, operator, comment)
        await self.db.execute(text(
            "UPDATE approval_task SET status='rejected', comment=:cm, acted_at=:now"
            " WHERE instance_id=:iid AND node_seq=:lv AND status='active' AND approver=:op"),
            {"cm": comment, "now": now, "iid": iid, "lv": level, "op": operator})
        await self.db.execute(text(
            "UPDATE approval_task SET status='canceled', acted_at=:now"
            " WHERE instance_id=:iid AND node_seq=:lv AND status='active' AND approver<>:op"),
            {"now": now, "iid": iid, "lv": level, "op": operator})
        result = await self.db.execute(text(
            "UPDATE approval_instance SET status='rejected', finished_at=:now, version=version+1, updated_at=NOW()"
            " WHERE id=:iid AND version=:v"),
            {"now": now, "iid": iid, "v": inst["version"]})
        if result.rowcount == 0:
            return {"success": False, "message": "数据已被他人更新，请刷新后重试"}
        fresh = await self._instance_row(iid)
        meta = await self.biz_meta(biz_type)
        await self._notify_applicant(
            fresh, f"[{meta['biz_name']}] 审批被驳回",
            f"您的单据 {inst['biz_no'] or ''} 被 {operator} 驳回。意见：{comment or '无'}。请修改后重新提交。")
        await self._sync_business(fresh)
        return {"success": True}

    async def recall(self, biz_type: str, biz_id: int, operator: str, *, operator_role: str = "") -> dict:
        inst = await self._instance_by_biz(biz_type, biz_id)
        if not inst or inst["status"] != "pending":
            return {"success": False, "message": "仅审批中状态可撤回"}
        if operator_role != "admin" and str(inst["applicant"]) != str(operator):
            return {"success": False, "message": "仅发起人可撤回该单据"}
        iid, now = inst["id"], datetime.now()
        await self._add_record(iid, "recall", inst["current_level"], operator, "申请人撤回")
        await self.db.execute(text(
            "UPDATE approval_task SET status='canceled', acted_at=:now"
            " WHERE instance_id=:iid AND status='active'"), {"now": now, "iid": iid})
        await self.db.execute(text(
            "UPDATE approval_instance SET status='recalled', finished_at=:now, version=version+1, updated_at=NOW()"
            " WHERE id=:iid"), {"now": now, "iid": iid})
        await self._sync_business(await self._instance_row(iid))
        return {"success": True}

    async def _earlier_approvers(self, instance_id: int, before_level: int) -> set[str]:
        """本轮次内、before_level 之前已审过的人（approve/auto_skip），username+user_id 都算。"""
        rows = await self.db.execute(text("""
            SELECT DISTINCT r.operator, u.id::text
            FROM approval_record r
            LEFT JOIN sys_user u ON u.username = r.operator
            WHERE r.instance_id = :iid AND r.node_seq < :lv AND r.action IN ('approve', 'auto_skip')
              AND r.id >= (SELECT COALESCE(MAX(s.id), 0) FROM approval_record s
                           WHERE s.instance_id = :iid AND s.action = 'submit')
        """), {"iid": instance_id, "lv": before_level})
        result = set()
        for r in rows:
            if r[0]:
                result.add(str(r[0]))
            if r[1]:
                result.add(str(r[1]))
        return result

    # ---------- 业务侧同步（回写） ----------

    async def _sync_business(self, inst: dict, *, approved_by: str = None, approved_at=None):
        """与审批动作同一事务：builtin 走 Adapter.on_transition，声明式走 writeback 配置。失败上抛整体回滚。"""
        state = {"status": inst["status"], "level": inst["current_level"],
                 "snapshot": _loads(inst["snapshot_json"], []),
                 "submitted_at": inst["submitted_at"], "approved_by": approved_by,
                 "approved_at": approved_at, "version": inst["version"]}
        adapter = adapter_instance(self.db, inst["biz_type"])
        if adapter is not None:
            await adapter.on_transition(self.db, inst["biz_id"], state)
            return
        await self._writeback_sql(inst)

    async def _writeback_sql(self, inst: dict):
        meta = await self.biz_meta(inst["biz_type"])
        wb = (meta or {}).get("writeback") or {}
        if not wb:
            return
        table, id_col = wb.get("table"), wb.get("id_column")
        st_col, mp = wb.get("status_column"), wb.get("status_map") or {}
        for name, v in (("table", table), ("id_column", id_col), ("status_column", st_col)):
            if not isinstance(v, str) or not IDENTIFIER_RE.match(v):
                raise ValueError(f"回写配置 {name} 不合法，请联系管理员修正业务接入配置")
        value = mp.get(inst["status"])
        if value is None or str(value) == "":
            return
        result = await self.db.execute(
            text(f"UPDATE {table} SET {st_col} = :v WHERE {id_col} = :id"),
            {"v": str(value), "id": inst["biz_id"]})
        if result.rowcount == 0:
            raise ValueError(f"回写失败：业务表 {table} 中不存在 id={inst['biz_id']} 的行")

    # ---------- 详情 ----------

    async def get_detail(self, biz_type: str, biz_id: int, viewer: str, viewer_role: str) -> Optional[dict]:
        inst = await self._instance_by_biz(biz_type, biz_id)
        if not inst:
            return None
        meta = await self.biz_meta(biz_type)
        snap = _loads(inst["snapshot_json"], [])
        level = inst["current_level"]
        node = next((n for n in snap if n.get("seq") == level), None)
        records = [dict(r._mapping) for r in await self.db.execute(text(
            "SELECT * FROM approval_record WHERE instance_id = :iid ORDER BY id"), {"iid": inst["id"]})]
        last_submit_id = max((r["id"] for r in records if r["action"] == "submit"), default=0)

        def _approver_label(n: dict) -> str:
            approvers = n.get("approvers")
            if approvers:
                names = [a.get("username") or str(a.get("user_id")) for a in approvers]
                return "指定人员：" + "、".join(x for x in names if x)
            return f"角色：{n.get('role')}" if n.get("role") else "-"

        node_log = {r["node_seq"]: r for r in records
                    if r["id"] > last_submit_id and r["action"] in ("approve", "reject", "auto_skip")}
        progress = []
        for n in snap:
            lg = node_log.get(n.get("seq"))
            progress.append({"seq": n.get("seq"), "label": n.get("label"),
                             "approver_label": _approver_label(n),
                             "state": "done" if lg else ("current" if n.get("seq") == level and inst["status"] == "pending" else "todo"),
                             "acted_at": lg.get("created_at") if lg else None,
                             "comment": lg.get("comment") if lg else None})
        logs = [{"time": r["created_at"], "who": r["operator"], "action": r["action"],
                 "action_label": ACTION_LABELS.get(r["action"], r["action"]), "comment": r["comment"]}
                for r in records]

        adapter = adapter_instance(self.db, biz_type)
        fields, attachments = [], []
        if adapter is not None:
            detail = await adapter.fetch_detail(self.db, biz_id) or {}
            fields = detail.get("fields") or []
            attachments = detail.get("attachments") or []
        elif meta and meta["sql_text"]:
            row = await self._sql_source_row(meta, biz_id)
            if row:
                from app.services.common.approval_sql import FIELD_LABELS
                fields = [{"label": FIELD_LABELS[k], "value": pick_mapped_value(row, meta["field_mapping"] or {}, k)}
                          for k in FIELD_LABELS if pick_mapped_value(row, meta["field_mapping"] or {}, k) is not None]
        item = {
            "biz_type": biz_type, "biz_name": (meta or {}).get("biz_name") or biz_type,
            "id": inst["biz_id"], "no": inst["biz_no"], "title": inst["title"],
            "summary": inst["summary"], "applicant": inst["applicant"],
            "submitted_at": inst["submitted_at"], "status": inst["status"],
            "current_node": node.get("label") if node else None, "current_level": level,
            "timeout_hours": (node or {}).get("timeout_hours"), "version": inst["version"],
            "deep_link": render_deep_link((meta or {}).get("deep_link_template"),
                                          {"id": inst["biz_id"], "no": inst["biz_no"], "title": inst["title"]}),
            "fields": fields, "attachments": attachments, "progress": progress, "logs": logs,
            "mode": (meta or {}).get("mode"),
        }
        if inst["status"] == "pending":
            holder = (await self.db.execute(text(
                "SELECT 1 FROM approval_task WHERE instance_id=:iid AND node_seq=:lv"
                " AND status='active' AND approver=:u LIMIT 1"),
                {"iid": inst["id"], "lv": level, "u": viewer})).fetchone()
            item["can_act"] = bool(holder) or viewer_role == "admin"
            item["can_recall"] = viewer_role == "admin" or str(inst["applicant"]) == str(viewer)
            if not item["can_act"]:
                item["action_hint"] = "当前节点由其他审批人处理，您可在此查看详情"
        else:
            item["can_act"] = False
            item["can_recall"] = False
            item["action_hint"] = "该单据审批已结束"
        return enrich_pending_item(item)

    async def _sql_source_row(self, meta: dict, biz_id: int) -> Optional[dict]:
        rows = await execute_readonly_sql(self.db, meta["sql_text"])
        mapping = meta["field_mapping"] or {}
        for row in rows:
            source_id = pick_mapped_value(row, mapping, "id")
            if source_id is not None and str(source_id) == str(biz_id):
                return row
        return None
