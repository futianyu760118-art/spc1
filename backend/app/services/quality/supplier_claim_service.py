"""供应商索赔通知单 - 业务逻辑（raw SQL + 审批中心）"""

import json
import logging
from datetime import datetime, date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.common.approval_center_service import ApprovalCenterService
from app.services.common.approval_engine import check_node_permission

logger = logging.getLogger(__name__)

CLAIM_REASONS = {"field_customer_claim", "supply_performance"}
CLAIM_ITEMS = {
    "replacement", "packing_fee", "transporting_fee", "man_hour_fee",
    "additional_fee", "punishment", "downgrade_use", "direct_loss",
}
CLAIM_ITEM_LABELS = {
    "replacement": "替代件费用", "packing_fee": "包装费用", "transporting_fee": "运输费用",
    "man_hour_fee": "人工费用", "additional_fee": "额外费用", "punishment": "处罚",
    "downgrade_use": "降级使用", "direct_loss": "直接损失",
}
RETURN_REQUIREMENTS = {"no_return", "return_supplier_fee"}


def _to_date(value) -> Optional[date]:
    """把前端传来的日期统一转成 date：asyncpg 对 DATE 列只接受 date 对象，字符串会直接报 DataError。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ValueError(f"日期格式不正确：{value}（应为 YYYY-MM-DD）")


class SupplierClaimService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- 查询 ----------

    def _filter_conditions(self, *, keyword=None, status=None, date_start=None,
                           date_end=None, applicant=None, supplier=None):
        conditions = ["1=1"]
        params: dict = {}
        if keyword:
            conditions.append("(c.claim_no ILIKE :kw OR c.supplier_name ILIKE :kw OR c.applicant ILIKE :kw)")
            params["kw"] = f"%{keyword}%"
        if status:
            conditions.append("c.approval_status = :st")
            params["st"] = status
        if date_start:
            conditions.append("c.claim_date >= :ds")
            params["ds"] = _to_date(date_start)
        if date_end:
            conditions.append("c.claim_date <= :de")
            params["de"] = _to_date(date_end)
        if applicant:
            conditions.append("c.applicant = :ap")
            params["ap"] = applicant
        if supplier:
            conditions.append("c.supplier_name ILIKE :sup")
            params["sup"] = f"%{supplier}%"
        return " AND ".join(conditions), params

    _LIST_SELECT = """
        SELECT c.*, COALESCE(u.display_name, c.applicant) AS applicant_display
        FROM supplier_claim c
        LEFT JOIN sys_user u ON u.username = c.applicant OR CAST(u.id AS VARCHAR) = c.applicant
    """

    async def list_claims(self, *, page=1, page_size=20, keyword=None, status=None,
                          date_start=None, date_end=None, applicant=None, supplier=None):
        where, params = self._filter_conditions(
            keyword=keyword, status=status, date_start=date_start, date_end=date_end,
            applicant=applicant, supplier=supplier)
        total = (await self.db.execute(
            text(f"SELECT COUNT(*) FROM supplier_claim c WHERE {where}"), params
        )).scalar() or 0
        rows = await self.db.execute(text(f"""
            {self._LIST_SELECT}
            WHERE {where}
            ORDER BY c.created_at DESC LIMIT :lim OFFSET :off
        """), {**params, "lim": page_size, "off": (page - 1) * page_size})
        items = [self._serialize(dict(r._mapping)) for r in rows]
        return items, total

    async def export_claims(self, **filters) -> list[dict]:
        """导出用：同 list_claims 的过滤口径，不分页全量。"""
        where, params = self._filter_conditions(**filters)
        rows = await self.db.execute(text(f"""
            {self._LIST_SELECT}
            WHERE {where}
            ORDER BY c.claim_date DESC, c.id DESC
        """), params)
        return [self._serialize(dict(r._mapping)) for r in rows]

    async def stats(self, *, approver_username: str = "", approver_role: str = "") -> dict:
        """台账 KPI 带：全量状态计数（与列表 chips 同口径）+ 本月金额 + 待我审批数。"""
        by_status = {"draft": 0, "pending": 0, "approved": 0, "rejected": 0, "recalled": 0}
        rows = await self.db.execute(
            text("SELECT approval_status, COUNT(*) FROM supplier_claim GROUP BY approval_status")
        )
        for st, n in rows:
            if st in by_status:
                by_status[st] = n
        month = (await self.db.execute(text("""
            SELECT COUNT(*), COALESCE(SUM(claim_amount), 0)
            FROM supplier_claim WHERE claim_date >= date_trunc('month', CURRENT_DATE)
        """))).fetchone()
        pending_mine = 0
        if approver_username or approver_role == "admin":
            pending_mine = len(await self.pending_approvals(
                approver_username=approver_username, approver_role=approver_role))
        return {
            "total": sum(by_status.values()),
            "by_status": by_status,
            "month_count": month[0] or 0,
            "month_amount": float(month[1] or 0),
            "pending_mine": pending_mine,
        }

    async def get_claim(self, claim_id: int) -> Optional[dict]:
        row = await self.db.execute(text("""
            SELECT c.*, COALESCE(u.display_name, c.applicant) AS applicant_display
            FROM supplier_claim c
            LEFT JOIN sys_user u ON u.username = c.applicant OR CAST(u.id AS VARCHAR) = c.applicant
            WHERE c.id = :eid
        """), {"eid": claim_id})
        r = row.fetchone()
        if not r:
            return None
        d = dict(r._mapping)
        if isinstance(d.get("approval_snapshot"), str):
            d["approval_snapshot"] = json.loads(d["approval_snapshot"] or "[]")
        if isinstance(d.get("claim_items"), str):
            d["claim_items"] = json.loads(d["claim_items"] or "[]")
        if isinstance(d.get("attachments"), str):
            d["attachments"] = json.loads(d["attachments"] or "[]")
        logs_row = await self.db.execute(
            text("SELECT * FROM supplier_claim_approval_log WHERE claim_id = :eid ORDER BY id"),
            {"eid": claim_id},
        )
        logs = [dict(x._mapping) for x in logs_row]
        # 中心化后新流水只写 approval_record：并入并映射回旧日志形状，业务页/打印不感知架构切换。
        # 存量迁移（migrate_approval_center.py）曾把旧日志复制进中心表，按 (action, approver,
        # operated_at) 去重防双计（与迁移脚本自身的幂等键一致）。
        legacy_keys = {(lg.get("action"), lg.get("approver"), lg.get("operated_at")) for lg in logs}
        records_row = await self.db.execute(text("""
            SELECT r.id, r.node_seq AS approval_level, r.operator AS approver, r.action,
                   r.comment, r.created_at AS operated_at
            FROM approval_record r
            JOIN approval_instance i ON i.id = r.instance_id
            WHERE i.biz_type = 'supplier_claim' AND i.biz_id = :eid
            ORDER BY r.id
        """), {"eid": claim_id})
        for x in records_row:
            rec = dict(x._mapping)
            if (rec.get("action"), rec.get("approver"), rec.get("operated_at")) in legacy_keys:
                continue
            logs.append(rec)
        logs.sort(key=lambda lg: (lg.get("operated_at") or datetime.min, lg.get("id") or 0))
        current_round = 0
        for lg in logs:
            if lg.get("action") == "submit":
                current_round += 1
            lg["round"] = current_round
        d["approval_logs"] = logs
        d["approval_round"] = current_round
        return self._serialize(d)

    def _serialize(self, d: dict) -> dict:
        if isinstance(d.get("claim_date"), date):
            d["claim_date"] = d["claim_date"].isoformat()
        for key in ("created_at", "updated_at", "submitted_at", "approved_at"):
            if isinstance(d.get(key), datetime):
                d[key] = d[key].isoformat()
        if isinstance(d.get("claim_items"), str):
            d["claim_items"] = json.loads(d["claim_items"] or "[]")
        if isinstance(d.get("attachments"), str):
            d["attachments"] = json.loads(d["attachments"] or "[]")
        if isinstance(d.get("approval_snapshot"), str):
            d["approval_snapshot"] = json.loads(d["approval_snapshot"] or "[]")
        if d.get("claim_amount") is not None:
            d["claim_amount"] = float(d["claim_amount"])
        return d

    # ---------- 编号 ----------

    async def _gen_claim_no(self) -> str:
        today = datetime.now().strftime("%Y%m%d")
        row = await self.db.execute(
            text("SELECT MAX(claim_no) FROM supplier_claim WHERE claim_no LIKE :pfx"),
            {"pfx": f"SC{today}%"},
        )
        max_no = row.scalar() or f"SC{today}-000"
        seq = int(max_no.split("-")[-1]) + 1
        return f"SC{today}-{seq:03d}"

    # ---------- CRUD ----------

    def _validate(self, data: dict) -> Optional[str]:
        if not (data.get("supplier_name") or "").strip():
            return "供应商不能为空"
        if data.get("claim_reason") not in CLAIM_REASONS:
            return "索赔原因不合法"
        items = data.get("claim_items") or []
        if not isinstance(items, list) or any(i not in CLAIM_ITEMS for i in items):
            return "索赔细项不合法"
        if data.get("return_requirement") not in RETURN_REQUIREMENTS:
            return "退回要求不合法"
        if data.get("claim_amount") is None or float(data["claim_amount"]) < 0:
            return "索赔金额必须为非负数字"
        return None

    @staticmethod
    def _params(data: dict) -> dict:
        return {
            "sid": data.get("supplier_id"),
            "sc": (data.get("supplier_code") or "").strip(),
            "sn": (data.get("supplier_name") or "").strip(),
            "cr": data.get("claim_reason"),
            "ci": json.dumps(data.get("claim_items") or []),
            "amt": data.get("claim_amount"),
            "cm": data.get("claim_method"),
            "ce": data.get("calc_explanation"),
            "rr": data.get("return_requirement"),
            "cd": _to_date(data.get("claim_date")) or date.today(),
            "rm": data.get("remarks"),
            "att": json.dumps(data.get("attachments") or []),
        }

    async def create_claim(self, data: dict, *, applicant: str = "", submit: bool = False) -> dict:
        """先落库为 draft，提交动作统一走审批中心（保证快照/流水/通知一致）。"""
        err = self._validate(data)
        if err:
            raise ValueError(err)
        claim_no = await self._gen_claim_no()
        p = self._params(data)
        await self.db.execute(text("""
            INSERT INTO supplier_claim
                (claim_no, supplier_id, supplier_code, supplier_name, claim_reason, claim_items,
                 claim_amount, claim_method, calc_explanation, return_requirement, claim_date,
                 remarks, attachments, approval_status, approval_level, version, applicant)
            VALUES (:no, :sid, :sc, :sn, :cr, :ci, :amt, :cm, :ce, :rr, :cd, :rm, :att, 'draft', 1, 1, :ap)
        """), {**p, "no": claim_no, "ap": applicant})
        claim_id = (await self.db.execute(
            text("SELECT id FROM supplier_claim WHERE claim_no = :no"), {"no": claim_no}
        )).scalar()
        if submit:
            await self._do_submit(claim_id, applicant)
        return await self.get_claim(claim_id)

    async def update_claim(self, claim_id: int, data: dict) -> Optional[dict]:
        rec = await self.get_claim(claim_id)
        if not rec or rec.get("approval_status") not in ("draft", "rejected", "recalled"):
            return None
        err = self._validate(data)
        if err:
            raise ValueError(err)
        p = self._params(data)
        await self.db.execute(text("""
            UPDATE supplier_claim SET
                supplier_id=:sid, supplier_code=:sc, supplier_name=:sn, claim_reason=:cr,
                claim_items=:ci, claim_amount=:amt, claim_method=:cm, calc_explanation=:ce,
                return_requirement=:rr, claim_date=:cd, remarks=:rm, attachments=:att, updated_at=NOW()
            WHERE id=:eid
        """), {**p, "eid": claim_id})
        return await self.get_claim(claim_id)

    async def delete_claim(self, claim_id: int, *, can_archive_delete: bool = False) -> dict:
        rec = await self.get_claim(claim_id)
        if not rec:
            return {"success": False, "message": "索赔单不存在"}
        status = rec.get("approval_status")
        if status == "pending":
            return {"success": False, "message": "审批中的索赔单不可删除，请先撤回"}
        if status == "approved" and not can_archive_delete:
            return {"success": False, "message": "已归档的索赔单需「索赔单归档删除」权限"}
        # 解绑附件引用计数（ref_count 归零的孤儿文件由清理任务统一处理）
        try:
            from app.services.common.file_service import FileService
            keys = [a.get("key") for a in (rec.get("attachments") or []) if isinstance(a, dict) and a.get("key")]
            if keys:
                await FileService(self.db).detach(keys)
        except Exception as e:
            logger.warning("索赔单附件引用计数解绑失败(claim_id=%s): %s", claim_id, e)
        await self.db.execute(text("DELETE FROM supplier_claim_approval_log WHERE claim_id = :eid"), {"eid": claim_id})
        # 中心三表随单据硬删一并清理，避免留孤儿实例/流水（与旧日志行同生命周期）
        await self.db.execute(text("""
            DELETE FROM approval_record WHERE instance_id IN (
                SELECT id FROM approval_instance WHERE biz_type = 'supplier_claim' AND biz_id = :eid)
        """), {"eid": claim_id})
        await self.db.execute(text("""
            DELETE FROM approval_task WHERE instance_id IN (
                SELECT id FROM approval_instance WHERE biz_type = 'supplier_claim' AND biz_id = :eid)
        """), {"eid": claim_id})
        await self.db.execute(text(
            "DELETE FROM approval_instance WHERE biz_type = 'supplier_claim' AND biz_id = :eid"), {"eid": claim_id})
        await self.db.execute(text("DELETE FROM supplier_claim WHERE id = :eid"), {"eid": claim_id})
        return {"success": True, "message": "已删除"}

    # ---------- 审批（委托审批中心） ----------

    async def _do_submit(self, claim_id: int, applicant: str):
        rec = await self.get_claim(claim_id)
        if not rec or rec.get("approval_status") not in ("draft", "rejected", "recalled"):
            raise ValueError("仅草稿/驳回/撤回状态可提交")
        if not (rec.get("supplier_name") or "").strip():
            raise ValueError("供应商不能为空，无法提交")
        await ApprovalCenterService(self.db).submit("supplier_claim", claim_id, applicant)  # 链未配置/已停用抛 ValueError，原样上抛
        # 绑定附件引用计数，避免孤儿清理误删已被单据引用的文件
        try:
            from app.services.common.file_service import FileService
            keys = [a.get("key") for a in (rec.get("attachments") or []) if isinstance(a, dict) and a.get("key")]
            if keys:
                await FileService(self.db).attach(keys, "supplier-claim", f"supplier_claim:{claim_id}")
        except Exception as e:
            logger.warning("索赔单附件引用计数绑定失败(claim_id=%s): %s", claim_id, e)

    async def submit_claim(self, claim_id: int, applicant: str, *, caller_role: str = "") -> Optional[dict]:
        rec = await self.get_claim(claim_id)
        if not rec or rec.get("approval_status") not in ("draft", "rejected", "recalled"):
            return None
        if caller_role != "admin" and rec.get("applicant") != applicant:
            raise ValueError("仅发起人可提交该索赔单")
        await self._do_submit(claim_id, applicant)
        return await self.get_claim(claim_id)

    async def approve(self, claim_id: int, approver: str, comment: str = "", *,
                      approver_role: str = "", expected_version: Optional[int] = None) -> dict:
        return await ApprovalCenterService(self.db).approve(
            "supplier_claim", claim_id, approver, comment,
            operator_role=approver_role, expected_version=expected_version)

    async def reject(self, claim_id: int, approver: str, comment: str = "", *,
                     approver_role: str = "", expected_version: Optional[int] = None) -> dict:
        return await ApprovalCenterService(self.db).reject(
            "supplier_claim", claim_id, approver, comment,
            operator_role=approver_role, expected_version=expected_version)

    async def recall(self, claim_id: int, applicant: str = "", *, caller_role: str = "") -> bool:
        rec = await self.get_claim(claim_id)
        if not rec:
            return False
        if caller_role != "admin" and rec.get("applicant") != applicant:
            raise ValueError("仅发起人可撤回该索赔单")
        result = await ApprovalCenterService(self.db).recall(
            "supplier_claim", claim_id, applicant, operator_role=caller_role)
        return bool(result.get("success"))

    async def revoke(self, claim_id: int, revoker: str, *, revoker_role: str = "") -> dict:
        # 中心化后暂不提供反审核；保留方法兼容业务端点
        return {"success": False, "message": "暂不支持"}

    async def pending_approvals(self, *, approver_username: str = "", approver_role: str = "") -> list[dict]:
        rows = await self.db.execute(text("""
            SELECT * FROM supplier_claim WHERE approval_status = 'pending' ORDER BY submitted_at DESC NULLS LAST
        """))
        items = []
        for r in rows:
            d = self._serialize(dict(r._mapping))
            if approver_role != "admin" and not self._is_current_node_approver(d, approver_username, approver_role):
                continue
            items.append(d)
        return items

    @staticmethod
    def _current_node(d: dict) -> Optional[dict]:
        snap = d.get("approval_snapshot") or []
        return next((n for n in snap if n.get("seq") == d.get("approval_level")), None)

    def _is_current_node_approver(self, d: dict, approver: str, approver_role: str) -> bool:
        node = self._current_node(d)
        if not node:
            return False
        ok, _ = check_node_permission(node, approver, approver_role)
        return ok

    async def approved_by_me(self, approver: str) -> list[dict]:
        """我已审批：我最近一次 approve/reject 的单据（被反审核的审批已置 revoked，不计入）。"""
        rows = await self.db.execute(text("""
            SELECT c.*, l.action AS my_action, l.comment AS my_comment, l.operated_at AS acted_at
            FROM supplier_claim c
            JOIN LATERAL (
                SELECT action, comment, operated_at
                FROM supplier_claim_approval_log
                WHERE claim_id = c.id AND approver = :ap AND action IN ('approve', 'reject')
                ORDER BY id DESC LIMIT 1
            ) l ON TRUE
            ORDER BY l.operated_at DESC NULLS LAST
        """), {"ap": approver})
        return [self._serialize(dict(r._mapping)) for r in rows]

    async def submitted_by_me(self, applicant: str) -> list[dict]:
        rows = await self.db.execute(text("""
            SELECT * FROM supplier_claim WHERE applicant = :ap ORDER BY submitted_at DESC NULLS LAST
        """), {"ap": applicant})
        return [self._serialize(dict(r._mapping)) for r in rows]

