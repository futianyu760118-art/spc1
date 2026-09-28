"""MRP 运算引擎：编排 / 净算 / 落库 / 对比 / 清理。"""

import asyncio
import logging
import time
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.mrp.bucket import MrpBucket
from app.models.mrp.exception import MrpException
from app.models.mrp.run import MrpRun
from app.models.mrp.substitute import MrpSubstitute
from app.models.mrp.suggestion import MrpSuggestion
from app.services.mrp import snapshot as snapshot_service
from app.services.mrp.bom_explosion import (
    BomComponent,
    ChildRequirement,
    compute_low_level_codes,
    explode,
    flatten_phantom,
)
from app.services.mrp.comparison import build_comparison
from app.services.mrp.exception_detector import (
    EXC_BELOW_SAFETY,
    EXC_NO_BOM,
    DemandInfo,
    SupplyInfo,
    detect_material_exceptions,
    make_exception_payload,
)
from app.services.mrp.netting import DemandEvent, SupplyEvent, net_requirements
from app.services.mrp.parameter_service import (
    ResolvedParam,
    ensure_default_scheme,
    load_parameters,
    resolve_param,
    scheme_snapshot,
    total_lead_time,
)
from app.services.mrp.snapshot import SupplyRecord
from app.services.mrp.substitute_calc import (
    LendableBalance,
    SubstituteRule,
    SuggestionDraft,
    apply_substitutes,
    build_lendable_balance,
)

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")
_RUN_RETENTION = 10

_SUPPLY_FIELD_BY_TYPE = {
    "po": "supply_po_qty",
    "task": "supply_task_qty",
    "subcontract": "supply_subcontract_qty",
    "transfer": "supply_transfer_qty",
    "requisition": "supply_requisition_qty",
}


def bill_type_for(material_property: Optional[int], has_bom: bool) -> Optional[int]:
    """物料属性 → 建议类型；虚拟件返回 None。"""
    if material_property == 5:
        return None
    if material_property in (2, 9):
        return 11011
    if material_property == 3:
        return 11012
    if material_property in (6, 7, 8):
        return 11011 if has_bom else 11010
    return 11010  # 1 外购 / 未知属性按外购处理并记数据体检


def _clamp_run_date(d: Optional[date], run_date: date, horizon_end: date) -> Optional[date]:
    if d is None:
        return run_date
    if d < run_date:
        return run_date
    if d > horizon_end:
        return None
    return d


class MrpEngine:
    def __init__(self) -> None:
        self._background_tasks: set[asyncio.Task] = set()

    def _on_background_task_done(self, task: asyncio.Task) -> None:
        self._background_tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.error("MRP 后台运算任务异常", exc_info=task.exception())

    async def create_run_and_launch(
        self, run_type: str, triggered_by: Optional[str], scope: Optional[dict] = None,
    ) -> MrpRun:
        async with AsyncSessionLocal() as db:
            now = datetime.now()
            await db.execute(
                update(MrpRun)
                .where(
                    MrpRun.status == "running",
                    MrpRun.started_at < now - timedelta(minutes=30),
                )
                .values(status="failed", error_message="stale running reaped", finished_at=now)
            )
            await db.commit()
            running = (
                await db.execute(select(func.count()).select_from(MrpRun).where(MrpRun.status == "running"))
            ).scalar() or 0
            if running:
                raise RuntimeError("MRP 正在运算中，请稍后再试")
            seq = (
                await db.execute(
                    select(func.count()).select_from(MrpRun).where(
                        func.date(MrpRun.created_at) == date.today()
                    )
                )
            ).scalar() or 0
            run = MrpRun(
                run_no=f"MRPRUN-{date.today():%Y%m%d}-{seq + 1:03d}",
                run_type=run_type,
                triggered_by=triggered_by,
                status="running",
                started_at=datetime.now(),
                stats={"scope": scope or {"scope": "all"}},
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)
            run_id = run.id
            run_no = run.run_no

        task = asyncio.create_task(self.execute(run_id, scope))
        self._background_tasks.add(task)
        task.add_done_callback(self._on_background_task_done)
        result = MrpRun(run_no=run_no, status="running")
        result.id = run_id
        return result

    async def execute(self, run_id: int, scope: Optional[dict] = None) -> None:
        started = time.time()
        try:
            async with AsyncSessionLocal() as db:
                run = (await db.execute(select(MrpRun).where(MrpRun.id == run_id))).scalar_one()
                scheme = await ensure_default_scheme(db)
                run.scheme_id = scheme.id
                run.horizon_days = scheme.horizon_days
                params, param_stats = await load_parameters(db)
                run.scheme_snapshot = scheme_snapshot(scheme, param_stats)
                await db.commit()

            run_date = date.today()
            horizon_end = run_date + timedelta(days=int(scheme.horizon_days))

            async with AsyncSessionLocal() as db:
                snapshot = await snapshot_service.collect(db, scope or {})
                substitute_rule_rows = (
                    await db.execute(
                        select(MrpSubstitute).where(MrpSubstitute.enabled.is_(True))
                    )
                ).scalars().all()
            substitute_rules = [
                SubstituteRule(
                    id=row.id,
                    main_material_id=row.main_material_id,
                    substitute_material_id=row.substitute_material_id,
                    priority=row.priority or 1,
                    policy=row.policy or "priority",
                    ratio=Decimal(str(row.ratio)) if row.ratio is not None else None,
                    substitute_mode=row.substitute_mode or "offset",
                    valid_from=row.valid_from,
                    valid_to=row.valid_to,
                    enabled=row.enabled,
                )
                for row in substitute_rule_rows
            ]

            child_reqs: dict[int, list[ChildRequirement]] = defaultdict(list)
            for demand in snapshot.demands:
                child_reqs[demand.material_id].append(
                    ChildRequirement(demand.material_id, demand.need_date or run_date, demand.qty)
                )
            pegging_by_key: dict[tuple, list[dict]] = defaultdict(list)
            for demand in snapshot.demands:
                pegging_by_key[(demand.material_id, demand.need_date or run_date)].append(
                    {"sale_order_no": demand.order_no, "line_no": demand.line_no, "qty": float(demand.qty)}
                )

            supplies_by_material: dict[int, list[SupplyRecord]] = defaultdict(list)
            for record in snapshot.supplies:
                supplies_by_material[record.material_id].append(record)

            supply_enabled = {
                "po": bool(scheme.consider_po),
                "task": bool(scheme.consider_task),
                "subcontract": bool(scheme.consider_subcontract),
                "transfer": bool(scheme.consider_transfer),
                "requisition": bool(scheme.consider_requisition),
            }

            bom_edges: dict[int, set[int]] = defaultdict(set)
            for bom_id, parent_id in snapshot.bom_parent_by_id.items():
                for comp in snapshot.details_by_bom.get(bom_id, []):
                    bom_edges[parent_id].add(comp.material_id)
            llc, cycle_nodes = compute_low_level_codes(bom_edges)
            if cycle_nodes:
                snapshot.data_issues.setdefault("bom_cycle", []).extend(cycle_nodes)

            def get_components(material_id: int) -> list[BomComponent]:
                bom_id = snapshot.bom_by_material.get(material_id)
                if not bom_id:
                    return []
                return [
                    BomComponent(
                        material_id=c.material_id,
                        standard_qty=c.standard_qty,
                        scrap_rate=c.scrap_rate,
                        lead_offset_days=c.lead_offset_days,
                        valid_date=c.valid_date,
                        invalid_date=c.invalid_date,
                    )
                    for c in snapshot.details_by_bom.get(bom_id, [])
                ]

            # 处理全集须覆盖 BOM 图全部物料：子件需求在父件净算后才产生，
            # 无初始需求/在途供给的子件若不在排序列表内会被漏算（设计 §4.1 ⑤）
            all_materials = set(llc.keys()) | set(child_reqs.keys())
            for record in snapshot.supplies:
                all_materials.add(record.material_id)
            ordered = sorted(all_materials, key=lambda mid: llc.get(mid, 0))

            bucket_payloads: list[dict] = []
            suggestion_payloads: list[dict] = []
            no_bom_materials: set[int] = set()
            unknown_property: list[int] = []
            processed_materials = 0
            safety_gaps: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)

            for material_id in ordered:
                demands_here = child_reqs.get(material_id, [])
                if not demands_here:
                    continue
                property_code = snapshot.property_by_material.get(material_id)
                bom_id = snapshot.bom_by_material.get(material_id)
                if property_code is None:
                    unknown_property.append(material_id)
                bill_type = bill_type_for(property_code, bool(bom_id))

                if bill_type is None:  # 虚拟件穿透
                    for req in demands_here:
                        if req.need_date > horizon_end:
                            continue
                        flattened = flatten_phantom(
                            material_id, req.need_date, req.qty, get_components,
                            is_phantom=lambda mid: mid in snapshot.phantom_ids,
                        )
                        for flat in flattened:
                            child_reqs[flat.material_id].append(flat)
                            pegging_by_key[(flat.material_id, flat.need_date)].extend(
                                pegging_by_key.get((material_id, req.need_date), [])
                            )
                    continue

                demand_events: list[DemandEvent] = []
                for req in demands_here:
                    clamped = _clamp_run_date(req.need_date, run_date, horizon_end)
                    if clamped is None:
                        continue
                    demand_events.append(
                        DemandEvent(clamped, req.qty, pegging_by_key.get((material_id, req.need_date), []))
                    )
                supply_events: list[SupplyEvent] = []
                for record in supplies_by_material.get(material_id, []):
                    if not supply_enabled.get(record.source_type, True):
                        continue
                    clamped = _clamp_run_date(record.supply_date, run_date, horizon_end)
                    if clamped is None:
                        continue
                    supply_events.append(SupplyEvent(clamped, record.qty, record.source_type))
                if not demand_events:
                    continue
                processed_materials += 1

                param: ResolvedParam = params.get(material_id)
                if param is None:
                    param = resolve_param(None, material_id, None)
                if not scheme.consider_safety_stock:
                    param = ResolvedParam(**{**param.__dict__, "safety_stock": _ZERO})

                opening = snapshot.opening_by_material.get(material_id, _ZERO)
                if not scheme.consider_inventory:
                    opening = _ZERO
                buckets, plans = net_requirements(
                    opening_qty=opening,
                    safety_stock=param.safety_stock,
                    demands=demand_events,
                    supplies=supply_events,
                    moq=param.moq,
                    batch_policy=param.batch_policy,
                    batch_qty=param.batch_qty,
                )

                if param.safety_stock > 0:
                    for row in buckets:
                        if row.net_demand_qty > 0:
                            safety_gaps[material_id].append((row.bucket_date, row.net_demand_qty))

                code = snapshot.code_by_material.get(material_id, "")
                name = snapshot.name_by_material.get(material_id, "")
                for row in buckets:
                    payload = {
                        "run_id": run_id,
                        "material_id": material_id,
                        "bucket_date": row.bucket_date,
                        "opening_qty": row.opening_qty,
                        "gross_demand_qty": row.gross_demand_qty,
                        "supply_po_qty": _ZERO,
                        "supply_task_qty": _ZERO,
                        "supply_subcontract_qty": _ZERO,
                        "supply_transfer_qty": _ZERO,
                        "supply_requisition_qty": _ZERO,
                        "substitute_in_qty": row.substitute_in_qty,
                        "substitute_out_qty": row.substitute_out_qty,
                        "safety_stock_qty": row.safety_stock_qty,
                        "closing_qty": row.closing_qty,
                        "net_demand_qty": row.net_demand_qty,
                        "pegging": row.pegging or None,
                    }
                    for source_type, qty in row.supply_by_type.items():
                        field = _SUPPLY_FIELD_BY_TYPE.get(source_type)
                        if field:
                            payload[field] = qty
                    bucket_payloads.append(payload)

                for plan in plans:
                    action_date = plan.need_date - timedelta(
                        days=total_lead_time(param, bill_type, plan.qty)
                    )
                    suggestion_payloads.append(
                        {
                            "run_id": run_id,
                            "material_id": material_id,
                            "material_code": code,
                            "material_name": name,
                            "bill_type": bill_type,
                            "suggest_qty": plan.qty,
                            "need_date": plan.need_date,
                            "action_date": action_date,
                            "suggested_supplier_id": param.default_supplier_id,
                            "source": plan.source,
                            "status": "pending",
                            "pegging": plan.pegging or None,
                        }
                    )
                    if bill_type in (11011, 11012):
                        if not bom_id:
                            no_bom_materials.add(material_id)
                            continue
                        parent_start = plan.need_date - timedelta(
                            days=total_lead_time(param, bill_type, plan.qty)
                        )
                        for child in explode(parent_start, plan.qty, get_components(material_id)):
                            child_reqs[child.material_id].append(child)
                            pegging_by_key[(child.material_id, child.need_date)].extend(
                                plan.pegging or []
                            )

            substitute_stats = {
                "offset_count": 0,
                "offset_qty": _ZERO,
                "replace_count": 0,
                "replace_skipped": 0,
            }
            if substitute_rules and suggestion_payloads:
                balances: dict[int, LendableBalance] = {}
                for substitute_material_id in {r.substitute_material_id for r in substitute_rules}:
                    sub_param = params.get(substitute_material_id)
                    opening = snapshot.opening_by_material.get(substitute_material_id, _ZERO)
                    if not scheme.consider_inventory:
                        opening = _ZERO
                    safety_stock = sub_param.safety_stock if sub_param else _ZERO
                    if not scheme.consider_safety_stock:
                        safety_stock = _ZERO
                    balances[substitute_material_id] = build_lendable_balance(
                        opening=opening,
                        supplies=[
                            (record.supply_date, record.qty)
                            for record in supplies_by_material.get(substitute_material_id, [])
                            if record.supply_date is not None
                            and supply_enabled.get(record.source_type, True)
                        ],
                        own_demands=[
                            (req.need_date, req.qty)
                            for req in child_reqs.get(substitute_material_id, [])
                        ],
                        safety_stock=safety_stock,
                    )

                pairs = [
                    [
                        SuggestionDraft(
                            suggestion_id=idx,
                            material_id=payload["material_id"],
                            need_date=payload["need_date"],
                            qty=Decimal(str(payload["suggest_qty"])),
                        ),
                        payload,
                    ]
                    for idx, payload in enumerate(suggestion_payloads)
                ]
                pairs.sort(key=lambda pair: (pair[0].need_date, pair[0].material_id))
                for new_idx, pair in enumerate(pairs):
                    pair[0].suggestion_id = new_idx

                _, outcome = apply_substitutes(
                    suggestions=[pair[0] for pair in pairs],
                    rules=substitute_rules,
                    balances=balances,
                    run_date=run_date,
                )

                for draft, payload in pairs:
                    payload.setdefault("is_substitute", False)
                    payload.setdefault("substitute_for_material_id", None)
                    if draft.qty != Decimal(str(payload["suggest_qty"])):
                        payload["suggest_qty"] = draft.qty.quantize(Decimal("0.0001"))
                for idx, substitute_material_id in outcome.replace_targets.items():
                    draft, payload = pairs[idx]
                    sub_bill_type = bill_type_for(
                        snapshot.property_by_material.get(substitute_material_id),
                        bool(snapshot.bom_by_material.get(substitute_material_id)),
                    )
                    if sub_bill_type != 11010:  # 自制/委外替代料的子件展开不在本简化内
                        substitute_stats["replace_skipped"] += 1
                        continue
                    sub_param = params.get(substitute_material_id)
                    if sub_param is None:
                        sub_param = resolve_param(None, substitute_material_id, None)
                    qty = Decimal(str(payload["suggest_qty"]))
                    payload["material_id"] = substitute_material_id
                    payload["material_code"] = snapshot.code_by_material.get(
                        substitute_material_id, payload.get("material_code", "")
                    )
                    payload["material_name"] = snapshot.name_by_material.get(substitute_material_id, "")
                    payload["is_substitute"] = True
                    payload["substitute_for_material_id"] = draft.material_id
                    payload["bill_type"] = sub_bill_type
                    payload["action_date"] = payload["need_date"] - timedelta(
                        days=total_lead_time(sub_param, sub_bill_type, qty)
                    )
                    payload["suggested_supplier_id"] = sub_param.default_supplier_id
                    substitute_stats["replace_count"] += 1

                bucket_index = {(p["material_id"], p["bucket_date"]): p for p in bucket_payloads}
                for item in outcome.offsets:
                    main_row = bucket_index.get((item["main_material_id"], item["need_date"]))
                    if main_row is not None:
                        main_row["substitute_in_qty"] = (
                            Decimal(str(main_row.get("substitute_in_qty") or 0)) + item["qty"]
                        )
                    sub_row = bucket_index.get((item["substitute_material_id"], item["need_date"]))
                    if sub_row is not None:
                        sub_row["substitute_out_qty"] = (
                            Decimal(str(sub_row.get("substitute_out_qty") or 0)) + item["qty"]
                        )
                substitute_stats["offset_count"] = len(outcome.offsets)
                substitute_stats["offset_qty"] = sum((o["qty"] for o in outcome.offsets), _ZERO)

                suggestion_payloads = [
                    payload
                    for payload in suggestion_payloads
                    if Decimal(str(payload["suggest_qty"])) > 0
                ]

            exception_payloads: list[dict] = []
            if scheme.exception_enabled:
                grace = int(scheme.exception_grace_days or 0)
                for material_id in ordered:
                    if material_id in snapshot.phantom_ids:
                        continue
                    material_demands = child_reqs.get(material_id) or []
                    material_supplies = [
                        record
                        for record in (supplies_by_material.get(material_id) or [])
                        if supply_enabled.get(record.source_type, True)
                    ]
                    if not material_demands:
                        continue
                    material_code = snapshot.code_by_material.get(material_id, "")
                    material_name = snapshot.name_by_material.get(material_id, "")
                    supply_infos = [
                        SupplyInfo(
                            date=r.supply_date, qty=r.qty, source_type=r.source_type,
                            doc_no=r.source_doc_no or "", line_no=r.source_line_no or "",
                            source_id=r.source_id,
                        )
                        for r in material_supplies
                    ]
                    demand_qty_by_key: dict[tuple, Decimal] = {}
                    for demand in material_demands:
                        pegging = (pegging_by_key.get((material_id, demand.need_date)) or [{}])[0]
                        key = (
                            demand.need_date,
                            pegging.get("sale_order_no", ""),
                            pegging.get("line_no", ""),
                        )
                        demand_qty_by_key[key] = demand_qty_by_key.get(key, _ZERO) + demand.qty
                    demand_infos = [
                        DemandInfo(need_date=need_date, qty=qty, order_no=order_no, line_no=line_no)
                        for (need_date, order_no, line_no), qty in demand_qty_by_key.items()
                    ]
                    exception_payloads.extend(
                        detect_material_exceptions(
                            material_id=material_id,
                            material_code=material_code,
                            material_name=material_name,
                            supplies=supply_infos,
                            demands=demand_infos,
                            grace_days=grace,
                            run_date=run_date,
                        )
                    )
                    gaps = safety_gaps.get(material_id) or []
                    if gaps:
                        earliest_gap = min(g[0] for g in gaps)
                        total_gap = sum((g[1] for g in gaps), _ZERO)
                        exception_payloads.append(
                            make_exception_payload(
                                material_id, material_code, material_name,
                                code=EXC_BELOW_SAFETY, type_="below_safety_stock",
                                source_type="mrp_material",
                                need_date=earliest_gap, suggest_date=earliest_gap,
                                suggest_qty=total_gap,
                                detail=f"净需求不足，共 {len(gaps)} 个时段低于安全库存，缺口合计 {total_gap}",
                            )
                        )
                    if material_id in no_bom_materials:
                        exception_payloads.append(
                            make_exception_payload(
                                material_id, material_code, material_name,
                                code=EXC_NO_BOM, type_="no_bom",
                                source_type="mrp_material",
                                detail="发出自制/委外建议但未维护有效 BOM，无法展开下阶需求",
                            )
                        )
                for payload in exception_payloads:
                    payload["run_id"] = run_id

            async with AsyncSessionLocal() as db:
                await self._bulk_insert(db, MrpBucket, bucket_payloads)
                await self._bulk_insert(db, MrpSuggestion, suggestion_payloads)
                await self._bulk_insert(db, MrpException, exception_payloads)
                exceptions_by_type: dict[str, int] = defaultdict(int)
                for payload in exception_payloads:
                    exceptions_by_type[payload["exception_type"]] += 1
                stats = {
                    "demand_lines": len(snapshot.demands),
                    "materials_processed": processed_materials,
                    "buckets": len(bucket_payloads),
                    "suggestions": len(suggestion_payloads),
                    "exceptions": len(exception_payloads),
                    "exceptions_by_type": dict(exceptions_by_type),
                    "substitute": {
                        "offset_count": substitute_stats["offset_count"],
                        "offset_qty": float(substitute_stats["offset_qty"]),
                        "replace_count": substitute_stats["replace_count"],
                        "replace_skipped": substitute_stats["replace_skipped"],
                    },
                    "duration_sec": round(time.time() - started, 2),
                    "data_issues": {
                        key: len(value) for key, value in snapshot.data_issues.items()
                    },
                }
                if no_bom_materials:
                    stats["data_issues"]["no_bom"] = len(no_bom_materials)
                if unknown_property:
                    stats["data_issues"]["material_property_missing"] = len(unknown_property)
                try:
                    comparison = await build_comparison(db, run_id, scheme)
                    stats["comparison"] = comparison["summary"]
                except Exception as exc:  # 对比失败不阻塞运算成功
                    logger.warning("MRP 对比失败 run=%s: %s", run_id, exc)
                    stats["comparison"] = {"error": str(exc)}
                run = (await db.execute(select(MrpRun).where(MrpRun.id == run_id))).scalar_one()
                stats["data_issues"]["param_fallback"] = (run.scheme_snapshot or {}).get("param_stats")
                run.status = "success"
                run.stats = stats
                run.finished_at = datetime.now()
                await db.commit()
                await self._cleanup_old_runs(db)

        except asyncio.CancelledError:
            logger.warning("MRP 运算取消 run=%s", run_id)
            await self._fail_run(run_id, "cancelled")
            raise
        except Exception as exc:
            logger.exception("MRP 运算失败 run=%s", run_id)
            await self._fail_run(run_id, str(exc)[:2000])

    async def _fail_run(self, run_id: int, error_message: str) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(delete(MrpBucket).where(MrpBucket.run_id == run_id))
            await db.execute(delete(MrpSuggestion).where(MrpSuggestion.run_id == run_id))
            await db.execute(delete(MrpException).where(MrpException.run_id == run_id))
            run = (await db.execute(select(MrpRun).where(MrpRun.id == run_id))).scalar_one_or_none()
            if run is not None:
                run.status = "failed"
                run.error_message = error_message
                run.finished_at = datetime.now()
            await db.commit()

    async def _bulk_insert(self, db: AsyncSession, model, payloads: list[dict]) -> None:
        chunk = 1000
        for start in range(0, len(payloads), chunk):
            await db.execute(model.__table__.insert(), payloads[start:start + chunk])
            await db.commit()

    async def _cleanup_old_runs(self, db: AsyncSession) -> None:
        keep_ids = (
            await db.execute(
                select(MrpRun.id).order_by(MrpRun.id.desc()).limit(_RUN_RETENTION)
            )
        ).scalars().all()
        if not keep_ids:
            return
        stale = select(MrpRun.id).order_by(MrpRun.id.desc()).offset(_RUN_RETENTION)
        stale_ids = (await db.execute(stale)).scalars().all()
        if not stale_ids:
            return
        await db.execute(delete(MrpBucket).where(MrpBucket.run_id.in_(stale_ids)))
        await db.execute(delete(MrpException).where(MrpException.run_id.in_(stale_ids)))
        await db.execute(
            delete(MrpSuggestion).where(
                MrpSuggestion.run_id.in_(stale_ids),
                MrpSuggestion.status != "converted",
            )
        )
        await db.commit()


mrp_engine = MrpEngine()
