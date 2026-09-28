"""物料齐套中心 — 采购申请单业务逻辑（编号 / CRUD / 提交审批 / 转采购订单）。

审批对接镜像供应商索赔单（supplier_claim_service）：主表带审批引擎约定列 + 独立日志表，
提交/审批/驳回/撤回委托公共 ApprovalEngine，通知走站内信 + 企微。服务内只 flush，不 commit。
"""

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import partial
from typing import Optional

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import log_audit
from app.models.basicdata.announcement import Notification
from app.models.basicdata.material import Material
from app.models.basicdata.supplier import Supplier
from app.models.material.purchase_order import PurchaseOrder
from app.models.material.purchase_requisition import (
    PurchaseRequisition,
    PurchaseRequisitionApprovalLog,
    PurchaseRequisitionLine,
)
from app.models.mrp.suggestion import MrpSuggestion
from app.services.common.approval_engine import ApprovalEngine, resolve_node_approver_user_ids
from app.services.common.approval_notify import send_approval_wecom_textcard
from app.services.common.approval_registry import ApprovalActionRequest
from app.services.notification.notification_broker import publish_unread_update

logger = logging.getLogger(__name__)

EDITABLE_STATUSES = ("draft", "rejected")
PURCHASE_BILL_TYPE = 11010
_ZERO = Decimal("0")


class RequisitionStateError(ValueError):
    """申请单/建议状态或行状态不允许当前操作（API 层映射为 409）。"""


class RequisitionNotFoundError(ValueError):
    """采购申请单不存在（API 层映射为 404）。"""


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


def _positive_decimal(value, label: str) -> Decimal:
    try:
        qty = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label}必须为数字")
    if qty <= _ZERO:
        raise ValueError(f"{label}必须大于 0")
    return qty


def _iso(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


class PurchaseRequisitionService:
    # ---------- 引擎 / 通知 ----------

    def _engine(self, db: AsyncSession) -> ApprovalEngine:
        return ApprovalEngine(
            db,
            biz_type="purchase_requisition",
            table="purchase_requisition",
            log_table="purchase_requisition_approval_log",
            ref_col="req_id",
            notify_approvers=partial(self._notify_approvers_of_level, db),
            notify_applicant=partial(self._notify_applicant_hook, db),
            biz_label="采购申请单",
            doc_no_field="req_no",
        )

    async def _notify_user(self, db: AsyncSession, user_id: int, title: str, content: str, *,
                           notify_type: str = "purchase_requisition", ref_id: Optional[int] = None,
                           sender_name: Optional[str] = None, sender_id: Optional[int] = None) -> None:
        try:
            db.add(Notification(
                user_id=user_id, type=notify_type, title=title, content=content,
                ref_type="purchase_requisition", ref_id=ref_id,
                sender_id=sender_id, sender_name=sender_name, priority="high", is_read=False,
            ))
            await db.flush()
        except Exception as e:
            logger.warning("采购申请单通知推送失败 user_id=%s: %s", user_id, e)
            return
        await publish_unread_update(db, user_id)

    async def _notify_wecom(self, db: AsyncSession, user_ids: list, rec: dict, label: str) -> None:
        """企微 textcard 推送，未配置/失败时降级，不影响审批流程。"""
        if not user_ids:
            return
        await send_approval_wecom_textcard(
            db,
            user_ids=[int(uid) for uid in user_ids],
            title=f"采购申请单待审批 - {label}",
            description=(f"采购申请单 {rec.get('req_no', '')}\n申请人：{rec.get('applicant', '') or '-'}\n"
                         f"部门：{rec.get('department', '') or '-'}\n审批节点：{label}\n点击查看详情并处理审批。"),
            path=f"/purchase-requisitions/{rec['id']}",
        )

    async def _notify_approvers_of_level(self, db: AsyncSession, rec: dict, level: int, title_prefix: str) -> None:
        snap = rec.get("approval_snapshot") or []
        node = next((n for n in snap if n.get("seq") == level), None)
        if not node:
            return
        target_uids = await resolve_node_approver_user_ids(db, node)
        if not target_uids:
            return
        label = node.get("label", f"L{level}")
        title = f"[采购申请单] {title_prefix} - {label}"
        content = (f"采购申请单 {rec.get('req_no', '')}（申请人：{rec.get('applicant', '') or '-'}，"
                   f"部门：{rec.get('department', '') or '-'}）需要您{label}。")
        try:
            applicant_id = int(rec.get("applicant"))
        except (TypeError, ValueError):
            applicant_id = None
        for uid in target_uids:
            await self._notify_user(db, uid, title, content, notify_type="approval_pending",
                                    ref_id=rec.get("id"), sender_name=rec.get("applicant"),
                                    sender_id=applicant_id)
        await self._notify_wecom(db, target_uids, rec, label)

    async def _notify_applicant_hook(self, db: AsyncSession, rec: dict, title: str, content: str) -> None:
        applicant = rec.get("applicant")
        if not applicant:
            return
        row = await db.execute(
            text("SELECT id FROM sys_user WHERE id::text = :a OR username = :a LIMIT 1"),
            {"a": str(applicant)},
        )
        r = row.fetchone()
        if r:
            await self._notify_user(db, r[0], title, content, ref_id=rec.get("id"))

    # ---------- 基础查询 ----------

    async def _load_req(self, db: AsyncSession, req_id: int) -> PurchaseRequisition:
        """populate_existing：引擎用原生 SQL 改审批列后，必须强制刷新 ORM 缓存避免读到旧值。

        找不到时抛 RequisitionNotFoundError（API 层映射 404）；只读入口 get_detail 捕获后返回 None。
        """
        stmt = (
            select(PurchaseRequisition)
            .where(PurchaseRequisition.id == req_id)
            .execution_options(populate_existing=True)
        )
        req = (await db.execute(stmt)).scalar_one_or_none()
        if req is None:
            raise RequisitionNotFoundError("采购申请单不存在")
        return req

    async def _line_stats(self, db: AsyncSession, req_ids: list[int]) -> dict[int, tuple[int, Decimal]]:
        if not req_ids:
            return {}
        rows = await db.execute(
            select(
                PurchaseRequisitionLine.req_id,
                func.count(PurchaseRequisitionLine.id),
                func.coalesce(func.sum(PurchaseRequisitionLine.req_qty * PurchaseRequisitionLine.unit_price), 0),
            )
            .where(PurchaseRequisitionLine.req_id.in_(req_ids))
            .group_by(PurchaseRequisitionLine.req_id)
        )
        return {rid: (int(cnt), Decimal(str(total or 0))) for rid, cnt, total in rows}

    def _serialize_req(self, req: PurchaseRequisition, *, line_count: Optional[int] = None,
                       total_amount: Optional[Decimal] = None) -> dict:
        data = {
            "id": req.id,
            "req_no": req.req_no,
            "status": req.status,
            "applicant": req.applicant,
            "department": req.department,
            "source": req.source,
            "run_id": req.run_id,
            "remark": req.remark,
            "approval_status": req.approval_status,
            "approval_level": req.approval_level,
            "approval_snapshot": req.approval_snapshot or [],
            "submitted_at": _iso(req.submitted_at),
            "approved_by": req.approved_by,
            "approved_at": _iso(req.approved_at),
            "version": req.version,
            "created_at": _iso(req.created_at),
            "updated_at": _iso(req.updated_at),
        }
        if line_count is not None:
            data["line_count"] = line_count
        if total_amount is not None:
            data["total_amount"] = float(total_amount)
        return data

    def _serialize_line(self, line: PurchaseRequisitionLine) -> dict:
        return {
            "id": line.id,
            "req_id": line.req_id,
            "line_no": line.line_no,
            "material_id": line.material_id,
            "material_code": line.material_code,
            "material_name": line.material_name,
            "spec_model": line.spec_model,
            "unit": line.unit,
            "req_qty": float(line.req_qty or 0),
            "need_date": _iso(line.need_date),
            "supplier_id": line.supplier_id,
            "supplier_code": line.supplier_code,
            "supplier_name": line.supplier_name,
            "unit_price": float(line.unit_price) if line.unit_price is not None else None,
            "source_suggestion_id": line.source_suggestion_id,
            "converted_qty": float(line.converted_qty or 0),
            "converted_po_no": line.converted_po_no,
            "converted_po_detail_id": line.converted_po_detail_id,
            "status": line.status,
            "remark": line.remark,
            "created_at": _iso(line.created_at),
            "updated_at": _iso(line.updated_at),
        }

    async def get_detail(self, db: AsyncSession, req_id: int) -> Optional[dict]:
        try:
            req = await self._load_req(db, req_id)
        except RequisitionNotFoundError:
            return None
        lines = (await db.execute(
            select(PurchaseRequisitionLine)
            .where(PurchaseRequisitionLine.req_id == req_id)
            .order_by(PurchaseRequisitionLine.line_no)
        )).scalars().all()
        logs = (await db.execute(
            select(PurchaseRequisitionApprovalLog)
            .where(PurchaseRequisitionApprovalLog.req_id == req_id)
            .order_by(PurchaseRequisitionApprovalLog.id)
        )).scalars().all()
        data = self._serialize_req(req)
        data["lines"] = [self._serialize_line(l) for l in lines]
        data["line_count"] = len(lines)
        data["total_qty"] = float(sum((l.req_qty or _ZERO for l in lines), _ZERO))
        data["total_amount"] = float(sum(
            ((l.req_qty or _ZERO) * (l.unit_price or _ZERO) for l in lines), _ZERO))
        approval_round = 0
        log_items = []
        for log in logs:
            if log.action == "submit":
                approval_round += 1
            log_items.append({
                "id": log.id, "approval_level": log.approval_level, "approver": log.approver,
                "action": log.action, "comment": log.comment,
                "operated_at": _iso(log.operated_at), "round": approval_round,
            })
        data["approval_logs"] = log_items
        data["approval_round"] = approval_round
        return data

    async def list_requisitions(self, db: AsyncSession, *, page: int = 1, page_size: int = 20,
                                keyword: Optional[str] = None, status: Optional[str] = None,
                                applicant: Optional[str] = None, date_start=None, date_end=None,
                                source: Optional[str] = None) -> tuple[int, list]:
        conditions = []
        if keyword:
            like = f"%{keyword}%"
            conditions.append(or_(
                PurchaseRequisition.req_no.ilike(like),
                PurchaseRequisition.applicant.ilike(like),
            ))
        if status:
            conditions.append(PurchaseRequisition.status == status)
        if applicant:
            conditions.append(PurchaseRequisition.applicant == applicant)
        if source:
            conditions.append(PurchaseRequisition.source == source)
        date_from = _to_date(date_start)
        date_to = _to_date(date_end)
        if date_from:
            conditions.append(func.date(PurchaseRequisition.created_at) >= date_from)
        if date_to:
            conditions.append(func.date(PurchaseRequisition.created_at) <= date_to)

        total = (await db.execute(
            select(func.count(PurchaseRequisition.id)).where(*conditions)
        )).scalar() or 0
        rows = (await db.execute(
            select(PurchaseRequisition)
            .where(*conditions)
            .order_by(PurchaseRequisition.created_at.desc(), PurchaseRequisition.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        stats = await self._line_stats(db, [r.id for r in rows])
        items = [
            self._serialize_req(r, line_count=stats.get(r.id, (0, _ZERO))[0],
                                total_amount=stats.get(r.id, (0, _ZERO))[1])
            for r in rows
        ]
        return total, items

    async def export_rows(self, db: AsyncSession, req_id: int) -> list[dict]:
        detail = await self.get_detail(db, req_id)
        if not detail:
            raise RequisitionNotFoundError("采购申请单不存在")
        return [{
            "req_no": detail["req_no"],
            "status": detail["status"],
            "applicant": detail.get("applicant") or "",
            "department": detail.get("department") or "",
            "source": detail.get("source") or "",
            "submitted_at": detail.get("submitted_at") or "",
            "line_no": line["line_no"],
            "material_code": line["material_code"],
            "material_name": line.get("material_name") or "",
            "spec_model": line.get("spec_model") or "",
            "unit": line.get("unit") or "",
            "req_qty": line["req_qty"],
            "need_date": line.get("need_date") or "",
            "supplier_name": line.get("supplier_name") or "",
            "unit_price": line.get("unit_price") if line.get("unit_price") is not None else "",
            "converted_qty": line["converted_qty"],
            "converted_po_no": line.get("converted_po_no") or "",
            "line_status": line["status"],
            "remark": line.get("remark") or "",
        } for line in detail["lines"]]

    # ---------- 编号 / 明细构建 ----------

    async def _gen_req_no(self, db: AsyncSession) -> str:
        today = datetime.now().strftime("%Y%m%d")
        max_no = (await db.execute(
            select(func.max(PurchaseRequisition.req_no))
            .where(PurchaseRequisition.req_no.like(f"PR-{today}%"))
        )).scalar()
        max_no = max_no or f"PR-{today}-000"
        seq = int(max_no.split("-")[-1]) + 1
        return f"PR-{today}-{seq:03d}"

    async def _material_map(self, db: AsyncSession, codes: list[str]) -> dict[str, Material]:
        rows = (await db.execute(
            select(Material).where(Material.material_code.in_(codes), Material.is_deleted == 0)
        )).scalars().all()
        return {m.material_code: m for m in rows}

    async def _supplier_map(self, db: AsyncSession, supplier_ids: list) -> dict[int, Supplier]:
        unique = sorted({int(i) for i in supplier_ids if i is not None})
        if not unique:
            return {}
        rows = (await db.execute(select(Supplier).where(Supplier.id.in_(unique)))).scalars().all()
        return {int(s.id): s for s in rows}

    async def _build_line_specs(self, db: AsyncSession, lines: list[dict]) -> list[dict]:
        codes = [(line.get("material_code") or "").strip() for line in lines]
        if any(not code for code in codes):
            raise ValueError("物料编码不能为空")
        material_map = await self._material_map(db, codes)
        missing = [code for code in codes if code not in material_map]
        if missing:
            raise ValueError(f"物料编码不存在: {missing[0]}")

        supplier_ids: list = []
        for line, code in zip(lines, codes):
            sid = line.get("supplier_id")
            if sid is None and material_map[code].supplier_id is not None:
                sid = material_map[code].supplier_id
            if sid is not None:
                supplier_ids.append(sid)
        supplier_map = await self._supplier_map(db, supplier_ids)

        specs = []
        for idx, (line, code) in enumerate(zip(lines, codes), start=1):
            material = material_map[code]
            explicit_supplier = line.get("supplier_id")
            supplier_id = (
                int(explicit_supplier) if explicit_supplier is not None
                else (int(material.supplier_id) if material.supplier_id is not None else None)
            )
            supplier = supplier_map.get(supplier_id) if supplier_id is not None else None
            if explicit_supplier is not None and supplier is None:
                raise ValueError(f"第 {idx} 行供应商不存在: {explicit_supplier}")
            specs.append({
                "material": material,
                "req_qty": _positive_decimal(line.get("req_qty"), f"第 {idx} 行申请数量"),
                "need_date": _to_date(line.get("need_date")),
                "supplier_id": supplier_id if supplier else None,
                "supplier": supplier,
                "source_suggestion_id": line.get("source_suggestion_id"),
                "remark": line.get("remark"),
            })
        return specs

    async def _insert_lines(self, db: AsyncSession, req: PurchaseRequisition,
                            specs: list[dict]) -> list[PurchaseRequisitionLine]:
        created = []
        for idx, spec in enumerate(specs, start=1):
            material = spec["material"]
            supplier = spec["supplier"]
            line = PurchaseRequisitionLine(
                req_id=req.id, line_no=idx,
                material_id=int(material.erp_material_id) if material.erp_material_id is not None else None,
                material_code=material.material_code,
                material_name=material.material_name,
                spec_model=material.spec_model,
                unit=material.unit_of_measure,
                req_qty=spec["req_qty"],
                need_date=spec["need_date"],
                supplier_id=spec["supplier_id"],
                supplier_code=supplier.supplier_code if supplier else None,
                supplier_name=supplier.supplier_name if supplier else None,
                unit_price=material.order_unit_price,
                source_suggestion_id=spec.get("source_suggestion_id"),
                remark=spec.get("remark"),
            )
            db.add(line)
            created.append(line)
        await db.flush()
        return created

    # ---------- 创建 / 编辑 ----------

    async def create_requisition(self, db: AsyncSession, *, applicant: str,
                                 department: Optional[str] = None, lines: list[dict],
                                 source: str = "manual", run_id: Optional[int] = None,
                                 remark: Optional[str] = None) -> PurchaseRequisition:
        if not lines:
            raise ValueError("采购申请明细不能为空")
        req_no = await self._gen_req_no(db)
        specs = await self._build_line_specs(db, lines)
        req = PurchaseRequisition(
            req_no=req_no, status="draft", applicant=applicant, department=department,
            source=source, run_id=run_id, remark=remark,
            approval_status="draft", approval_level=1, version=1,
        )
        db.add(req)
        await db.flush()
        await self._insert_lines(db, req, specs)
        return req

    async def _load_approved_suggestions(self, db: AsyncSession,
                                         suggestion_ids: list[int]) -> list[MrpSuggestion]:
        if not suggestion_ids:
            raise ValueError("请至少选择一条 MRP 建议")
        if len(set(suggestion_ids)) != len(suggestion_ids):
            raise ValueError("所选 MRP 建议存在重复")
        rows = (await db.execute(
            select(MrpSuggestion)
            .where(MrpSuggestion.id.in_(suggestion_ids))
            .order_by(MrpSuggestion.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )).scalars().all()
        found = {s.id: s for s in rows}
        missing = [str(i) for i in suggestion_ids if i not in found]
        if missing:
            raise ValueError(f"MRP 建议不存在: {', '.join(missing)}")
        ordered = [found[i] for i in suggestion_ids]
        for suggestion in ordered:
            if suggestion.status != "approved":
                raise RequisitionStateError(
                    f"建议 {suggestion.id}（{suggestion.material_code}）状态为 {suggestion.status}，"
                    f"仅已审核通过的建议可转申请单"
                )
            if suggestion.bill_type != PURCHASE_BILL_TYPE:
                raise ValueError(
                    f"建议 {suggestion.id}（{suggestion.material_code}）非外购类型，不能转采购申请单"
                )
        return ordered

    async def create_from_suggestions(self, db: AsyncSession, *, username: str,
                                      suggestion_ids: list[int]) -> PurchaseRequisition:
        suggestions = await self._load_approved_suggestions(db, suggestion_ids)
        req_no = await self._gen_req_no(db)
        req = PurchaseRequisition(
            req_no=req_no, status="draft", applicant=username,
            source="mrp", run_id=suggestions[0].run_id,
            approval_status="draft", approval_level=1, version=1,
        )
        db.add(req)
        await db.flush()
        specs = await self._build_line_specs(db, [{
            "material_code": s.material_code,
            "req_qty": s.suggest_qty,
            "need_date": s.need_date,
            "supplier_id": s.suggested_supplier_id,
            "source_suggestion_id": s.id,
        } for s in suggestions])
        lines = await self._insert_lines(db, req, specs)
        for suggestion, line in zip(suggestions, lines):
            suggestion.status = "converted"
            suggestion.converted_target_type = "purchase_requisition"
            suggestion.converted_target_id = line.id
        await db.flush()
        return req

    async def update_requisition(self, db: AsyncSession, req_id: int, payload: dict,
                                 username: str) -> PurchaseRequisition:
        req = await self._load_req(db, req_id)
        if req.status not in EDITABLE_STATUSES:
            raise ValueError("仅草稿/驳回状态可编辑")

        header_updates = {
            field: payload.get(field) for field in ("department", "remark") if field in payload
        }
        if header_updates:
            await log_audit(db, "purchase_requisition", req.id, "update",
                            old_obj=req, update_data=header_updates, operator=username)
            for field, value in header_updates.items():
                setattr(req, field, value)

        new_lines = payload.get("lines")
        if new_lines is not None:
            if not new_lines:
                raise ValueError("采购申请明细不能为空")
            specs = await self._build_line_specs(db, new_lines)
            old_count = (await db.execute(
                select(func.count(PurchaseRequisitionLine.id))
                .where(PurchaseRequisitionLine.req_id == req.id)
            )).scalar() or 0
            await db.execute(delete(PurchaseRequisitionLine).where(PurchaseRequisitionLine.req_id == req.id))
            await self._insert_lines(db, req, specs)
            await log_audit(db, "purchase_requisition", req.id, "update",
                            field_name="line_count", old_value=str(old_count),
                            new_value=str(len(specs)), operator=username)
        await db.flush()
        return req

    # ---------- 提交 / 审批（委托引擎） ----------

    async def submit(self, db: AsyncSession, req_id: int, username: str) -> dict:
        req = await self._load_req(db, req_id)
        if req.status not in EDITABLE_STATUSES:
            raise ValueError("仅草稿/驳回状态可提交审批")
        fresh = await self._engine(db).submit(req_id, username)  # 链未配置/已停用抛 ValueError，原样上抛
        if not fresh:
            raise ValueError("提交失败，请刷新后重试")
        req = await self._load_req(db, req_id)
        req.status = "approving"
        await db.flush()
        return await self.get_detail(db, req_id)

    async def approve(self, db: AsyncSession, request: ApprovalActionRequest) -> dict:
        result = await self._engine(db).approve(
            request.entity_id, request.approver, request.comment,
            approver_role=request.approver_role, expected_version=request.expected_version,
        )
        if result.get("success") and result.get("finished"):
            req = await self._load_req(db, request.entity_id)
            req.status = "approved"
            await db.flush()
        return result

    async def reject(self, db: AsyncSession, request: ApprovalActionRequest) -> dict:
        result = await self._engine(db).reject(
            request.entity_id, request.approver, request.comment,
            approver_role=request.approver_role, expected_version=request.expected_version,
        )
        if result.get("success"):
            req = await self._load_req(db, request.entity_id)
            req.status = "rejected"
            await db.flush()
        return result

    async def recall(self, db: AsyncSession, request: ApprovalActionRequest) -> dict:
        try:
            req = await self._load_req(db, request.entity_id)
        except RequisitionNotFoundError:
            return {"success": False, "message": "采购申请单不存在"}
        if request.approver_role != "admin" and req.applicant != request.approver:
            return {"success": False, "message": "仅发起人可撤回该采购申请单"}
        ok = await self._engine(db).recall(request.entity_id, request.approver)
        if not ok:
            return {"success": False, "message": "仅审批中状态可撤回"}
        req = await self._load_req(db, request.entity_id)
        req.status = "draft"
        await db.flush()
        return {"success": True, "message": "已撤回"}

    # ---------- 审批中心取数 ----------

    async def pending_approvals(self, db: AsyncSession, approver_username: str = "",
                                approver_role: str = "") -> list[dict]:
        rows = (await db.execute(
            select(PurchaseRequisition)
            .where(PurchaseRequisition.approval_status == "pending")
            .order_by(PurchaseRequisition.submitted_at.desc().nulls_last())
        )).scalars().all()
        engine = self._engine(db)
        stats = await self._line_stats(db, [r.id for r in rows])
        items = []
        for req in rows:
            count, amount = stats.get(req.id, (0, _ZERO))
            data = self._serialize_req(req, line_count=count, total_amount=amount)
            if approver_role != "admin" and not engine.is_current_node_approver(data, approver_username, approver_role):
                continue
            items.append(data)
        return items

    async def approved_requisitions(self, db: AsyncSession, approver: str) -> list[dict]:
        """我已审批：我最近一次 approve/reject 的单据（被反审核的审批已置 revoked，不计入）。"""
        latest_log_id = (
            select(func.max(PurchaseRequisitionApprovalLog.id))
            .where(
                PurchaseRequisitionApprovalLog.req_id == PurchaseRequisition.id,
                PurchaseRequisitionApprovalLog.approver == approver,
                PurchaseRequisitionApprovalLog.action.in_(("approve", "reject")),
            )
            .correlate(PurchaseRequisition)
            .scalar_subquery()
        )
        rows = (await db.execute(
            select(PurchaseRequisition, PurchaseRequisitionApprovalLog.action,
                   PurchaseRequisitionApprovalLog.comment, PurchaseRequisitionApprovalLog.operated_at)
            .join(PurchaseRequisitionApprovalLog, PurchaseRequisitionApprovalLog.id == latest_log_id)
            .order_by(PurchaseRequisitionApprovalLog.operated_at.desc().nulls_last())
        )).all()
        stats = await self._line_stats(db, [r[0].id for r in rows])
        items = []
        for req, action, comment, operated_at in rows:
            count, amount = stats.get(req.id, (0, _ZERO))
            data = self._serialize_req(req, line_count=count, total_amount=amount)
            data.update({"my_action": action, "my_comment": comment, "acted_at": _iso(operated_at)})
            items.append(data)
        return items

    async def submitted_requisitions(self, db: AsyncSession, applicant: str) -> list[dict]:
        rows = (await db.execute(
            select(PurchaseRequisition)
            .where(PurchaseRequisition.applicant == applicant)
            .order_by(PurchaseRequisition.submitted_at.desc().nulls_last())
        )).scalars().all()
        stats = await self._line_stats(db, [r.id for r in rows])
        items = []
        for req in rows:
            count, amount = stats.get(req.id, (0, _ZERO))
            items.append(self._serialize_req(req, line_count=count, total_amount=amount))
        return items

    # ---------- 转采购订单 ----------

    async def convert_to_po(self, db: AsyncSession, *, req_id: int, username: str,
                            items: list[dict]) -> dict:
        req = (await db.execute(
            select(PurchaseRequisition)
            .where(PurchaseRequisition.id == req_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if not req:
            raise RequisitionNotFoundError("采购申请单不存在")
        if req.status != "approved":
            raise RequisitionStateError("仅审批通过的采购申请单可转采购订单")
        if not items:
            raise ValueError("请至少选择一行转采购订单")

        lines = (await db.execute(
            select(PurchaseRequisitionLine).where(PurchaseRequisitionLine.req_id == req_id)
        )).scalars().all()
        line_map = {line.id: line for line in lines}
        supplier_map = await self._supplier_map(db, [line.supplier_id for line in lines])

        created = 0
        for item in items:
            line = line_map.get(item.get("line_id"))
            if line is None:
                raise ValueError(f"明细行不存在: {item.get('line_id')}")
            if line.status == "closed":
                raise RequisitionStateError(f"行 {line.line_no} 已关闭，不能转单")
            qty = _positive_decimal(item.get("qty"), f"第 {line.line_no} 行转单数量")
            remaining = (line.req_qty or _ZERO) - (line.converted_qty or _ZERO)
            if qty > remaining:
                raise ValueError(f"第 {line.line_no} 行转单数量 {qty} 超过剩余可转数量 {remaining}")

            po_no = f"MRP-{req.req_no}-{line.line_no}"
            detail_id = (await db.execute(
                select(func.coalesce(func.max(PurchaseOrder.detail_id), 0))
                .where(PurchaseOrder.po_no == po_no)
            )).scalar() + 1
            supplier = supplier_map.get(int(line.supplier_id)) if line.supplier_id else None
            db.add(PurchaseOrder(
                po_no=po_no, detail_id=detail_id,
                material_code=line.material_code, material_name=line.material_name,
                supplier_code=supplier.supplier_code if supplier else line.supplier_code,
                supplier_name=supplier.supplier_name if supplier else line.supplier_name,
                po_qty=qty, po_price=line.unit_price, po_date=date.today(),
                po_status="placed", eta=line.need_date, data_source="mrp", owner=username,
            ))
            line.converted_qty = (line.converted_qty or _ZERO) + qty
            line.converted_po_no = po_no
            line.converted_po_detail_id = detail_id
            line.status = "closed" if line.converted_qty >= (line.req_qty or _ZERO) else "partially_converted"
            created += 1

        await db.flush()
        closed = await self._close_header_if_no_open_line(db, req)
        return {"created": created, "closed": closed}

    async def _close_header_if_no_open_line(self, db: AsyncSession,
                                            req: PurchaseRequisition) -> bool:
        open_count = (await db.execute(
            select(func.count(PurchaseRequisitionLine.id)).where(
                PurchaseRequisitionLine.req_id == req.id,
                PurchaseRequisitionLine.status != "closed",
            )
        )).scalar() or 0
        if open_count:
            return False
        if req.status != "closed":
            req.status = "closed"
            await db.flush()
        return True

    async def close_line_and_maybe_header(self, db: AsyncSession,
                                          line: PurchaseRequisitionLine) -> None:
        """MRP 例外取消/减量：关闭明细行；主表无未关闭行时一并关闭。"""
        line.status = "closed"
        await db.flush()
        req = await self._load_req(db, line.req_id)
        await self._close_header_if_no_open_line(db, req)
