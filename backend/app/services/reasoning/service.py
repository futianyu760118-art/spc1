"""执行面推理服务 — 证据采集 → 大模型推理 → 结论校验 → 审计留痕

职责链：解析业务锚点 → 只读证据采集（与对外查询接口同数据域、同时效口径）→
组装受约束提示词 → 调用中台大模型结构化输出 → 校验结论证据引用 →
产出 AEOS run_complete.result 等价结构并落审计。

安全边界（任务书§四，强制）：
- 只读：本服务仅对业务表执行 SELECT；对数据库的唯一写入是 reasoning_task 审计表；
- 证据强制：require_evidence=true 时，evidence_refs 不指向已采集证据的结论一律剔除；
- 不伪装：未配置真实大模型（provider=rule_based）或调用失败时返回
  UPSTREAM_UNAVAILABLE(503)，绝不以规则结果冒充大模型推理；
- 口径区分：空结果 404、上游不可用 503、超时 504、取消 490 各自成错；
  数据过期不报错，而是 data_confidence=low + stale=true + warnings=["STALE_DATA"]。
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.external.freshness import source_as_of, table_max_as_of
from app.core.config import get_settings
from app.models.basicdata.reasoning import ReasoningTask
from app.models.exception.quality_issue import QualityIssue
from app.models.material.kitting import KittingResult, KittingShortage
from app.models.order.sale_order import SaleOrder, SaleOrderLine
from app.models.production.production_task_order import ProductionTaskOrder
from app.services.ai.base import ChatOptions
from app.services.ai.service import ai_service
from app.services.material.kitting_calc_service import (
    KITTING_RESULT_SYNC_TYPES,
    freshness_of,
    load_source_as_of,
    min_as_of,
)

logger = logging.getLogger(__name__)

# 支持的任务类型 → 证据采集器（与对外查询接口 18 端点同数据域，服务端内置，调用方不可注入）
TASK_TYPES = {
    "order_delivery_analysis",
    "material_kitting_analysis",
    "quality_analysis",
    "production_analysis",
}

ANCHOR_TYPES = {"order", "product", "batch"}

PROMPT_MAX_CHARS = 2000


# ═══════════════════════════════════════════
# 结构化错误（endpoint 层转 ExternalEnvelopeError 信封）
# ═══════════════════════════════════════════

class ReasoningError(Exception):
    """推理失败基类；code 为对外信封码"""

    code = 500
    status = "failed"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class InvalidRequestError(ReasoningError):
    code = 400
    status = "failed"


class EmptyResultError(ReasoningError):
    code = 404
    status = "failed"


class TaskCancelledError(ReasoningError):
    code = 490
    status = "cancelled"


class UpstreamUnavailableError(ReasoningError):
    code = 503
    status = "failed"


class ReasoningTimeoutError(ReasoningError):
    code = 504
    status = "timeout"


# ═══════════════════════════════════════════
# 大模型结构化输出 schema
# ═══════════════════════════════════════════

class ReasoningConclusion(BaseModel):
    matter: str = Field(..., description="结论事项")
    evidence_refs: list[str] = Field(default_factory=list, description="证据引用 URI 列表")
    risk: Optional[str] = Field(None, description="风险影响")
    recommendation: Optional[str] = Field(None, description="建议（金额/承诺/质量/法律类必须标注需人工确认）")
    confidence: Literal["high", "medium", "low"] = Field("medium", description="结论置信度")


class ReasoningAnalysis(BaseModel):
    summary: str = Field(..., description="总体结论")
    conclusions: list[ReasoningConclusion] = Field(default_factory=list)


@dataclass
class BusinessAnchor:
    """业务锚点：context.businessObjectRef 解析结果"""
    type: str  # order / product / batch
    key: str


@dataclass
class EvidenceBundle:
    """单个数据域的采集结果"""
    source: str
    evidence: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    as_of: Optional[datetime] = None
    error: Optional[str] = None


# ═══════════════════════════════════════════
# 锚点解析与结论校验（纯函数，供单测）
# ═══════════════════════════════════════════

def parse_business_object_ref(ref: Optional[str]) -> BusinessAnchor:
    if not ref:
        raise InvalidRequestError("缺少 context.businessObjectRef（试点阶段必须指定分析对象，如 business://order/订单号）")
    if not ref.startswith("business://"):
        raise InvalidRequestError(f"businessObjectRef 格式无效：{ref}，应为 business://<order|product|batch>/<键值>")
    rest = ref[len("business://"):]
    parts = [p for p in rest.split("/") if p]
    if len(parts) < 2:
        raise InvalidRequestError(f"businessObjectRef 格式无效：{ref}，应为 business://<order|product|batch>/<键值>")
    anchor_type, key = parts[0].lower(), parts[1]
    if anchor_type not in ANCHOR_TYPES:
        raise InvalidRequestError(
            f"businessObjectRef 锚点类型不支持：{anchor_type}（当前支持 {sorted(ANCHOR_TYPES)}）"
        )
    return BusinessAnchor(anchor_type, key)


def validate_conclusions(
    analysis: ReasoningAnalysis,
    evidence: list[dict],
    require_evidence: bool,
    max_conclusions: int,
) -> tuple[list[ReasoningConclusion], int]:
    """校验结论的证据引用，返回 (保留结论, 被拒结论数)。

    - evidence_refs 逐条对照已采集证据集合过滤；
    - require_evidence=true：无任何有效引用的结论剔除（任务书§四.3）；
    - require_evidence=false：保留但降级 confidence=low、清空引用；
    - 超出 max_conclusions 的尾部结论剔除。
    """
    valid_refs = {ev["ref"] for ev in evidence}
    kept: list[ReasoningConclusion] = []
    dropped = 0
    for conclusion in analysis.conclusions:
        original = conclusion.evidence_refs or []
        refs = [r for r in original if r in valid_refs]
        if not refs:
            if require_evidence:
                dropped += 1
                continue
            kept.append(conclusion.model_copy(update={"evidence_refs": [], "confidence": "low"}))
        elif len(refs) != len(original):
            kept.append(conclusion.model_copy(update={"evidence_refs": refs}))
        else:
            kept.append(conclusion)
    overflow = max(0, len(kept) - max_conclusions)
    if overflow:
        kept = kept[:max_conclusions]
    return kept, dropped + overflow


# ═══════════════════════════════════════════
# 只读证据采集器（每域一个；仅 SELECT）
# ═══════════════════════════════════════════

def _anchor_condition(anchor: BusinessAnchor, order_no_col, product_col, batch_col):
    """锚点 → 订单表查询条件；不支持该锚点类型时返回 None"""
    if anchor.type == "order":
        return order_no_col == anchor.key
    if anchor.type == "product":
        return product_col == anchor.key
    if anchor.type == "batch":
        return batch_col == anchor.key
    return None


def _order_summary(row: SaleOrder) -> str:
    parts = [
        f"状态 {row.status or '?'}",
        f"数量 {row.order_qty} / 完成 {row.completed_qty or 0}",
        f"交期 {row.promised_date.isoformat() if row.promised_date else '?'}",
        f"风险 {row.risk_level or '未评估'}",
    ]
    return " / ".join(parts)


async def collect_order_evidence(db: AsyncSession, anchor: BusinessAnchor) -> EvidenceBundle:
    """销售订单行（含明细行的 BOM 归属）——与 orders.list / order_details.list 同域"""
    bundle = EvidenceBundle(source="orders")
    condition = _anchor_condition(anchor, SaleOrder.order_no, SaleOrder.product_code, SaleOrder.batch_no)
    if condition is None:
        return bundle
    started = time.time()
    rows = (
        await db.execute(
            select(SaleOrder).where(condition).order_by(SaleOrder.id.asc()).limit(10)
        )
    ).scalars().all()
    bundle.tool_calls.append({
        "tool": "orders.detail", "read_only": True,
        "params": {"anchor": f"{anchor.type}:{anchor.key}"}, "rows": len(rows),
        "duration_ms": round((time.time() - started) * 1000, 1),
    })
    for row in rows:
        line_ref = f"control-platform://order/{row.order_no}/line/{row.line_no}"
        data = {
            "order_no": row.order_no, "line_no": row.line_no,
            "customer": row.customer, "product_code": row.product_code,
            "product_name": row.product_name,
            "order_qty": float(row.order_qty) if row.order_qty is not None else None,
            "completed_qty": float(row.completed_qty) if row.completed_qty is not None else None,
            "order_amount": float(row.order_amount) if row.order_amount is not None else None,
            "status": row.status, "erp_status": row.erp_status,
            "promised_date": row.promised_date.isoformat() if row.promised_date else None,
            "shipping_plan": row.shipping_plan.isoformat() if row.shipping_plan else None,
            "material_ready_date": row.material_ready_date.isoformat() if row.material_ready_date else None,
            "risk_level": row.risk_level,
            "risk_score": float(row.risk_score) if row.risk_score is not None else None,
            "owner": row.owner,
            "batch_no": row.batch_no,
            "is_closed": row.is_closed, "is_deleted": row.is_deleted,
        }
        bundle.evidence.append({
            "ref": line_ref, "source": "orders",
            "title": f"销售订单行 {row.order_no}:{row.line_no}",
            "summary": _order_summary(row), "data": data,
        })
    if rows:
        line_rows = (
            await db.execute(
                select(SaleOrderLine).where(SaleOrderLine.order_no == rows[0].order_no)
                .order_by(SaleOrderLine.id.asc()).limit(20)
            )
        ).scalars().all()
        for line in line_rows:
            bundle.evidence.append({
                "ref": f"control-platform://order/{line.order_no}/detail/{line.line_no}",
                "source": "orders",
                "title": f"订单明细 {line.order_no}:{line.line_no}",
                "summary": f"产品 {line.product_name or line.product_code} / 数量 {line.order_qty} / BOM {line.bom_no}",
                "data": {
                    "order_no": line.order_no, "line_no": line.line_no,
                    "product_code": line.product_code, "product_model": line.product_model,
                    "order_qty": float(line.order_qty) if line.order_qty is not None else None,
                    "promised_date": line.promised_date.isoformat() if line.promised_date else None,
                    "batch_no": line.batch_no, "bom_no": line.bom_no, "bom_id": line.bom_id,
                    "status": line.status,
                },
            })
    bundle.as_of = await source_as_of(
        db,
        columns=(SaleOrder.updated_at, SaleOrderLine.updated_at),
        sync_types=("orders", "order_details"),
    )
    return bundle


async def collect_kitting_evidence(db: AsyncSession, anchor: BusinessAnchor) -> EvidenceBundle:
    """齐套结果 + 缺料明细 —— 与 kitting.results / kitting.shortages 同域"""
    bundle = EvidenceBundle(source="kitting")
    demand_condition = (
        KittingResult.demand_no == anchor.key if anchor.type == "order"
        else (KittingResult.product_code == anchor.key if anchor.type == "product" else None)
    )
    if demand_condition is None:
        return bundle
    started = time.time()
    results = (
        await db.execute(
            select(KittingResult)
            .where(demand_condition, KittingResult.is_deleted == 0)
            .order_by(KittingResult.id.asc()).limit(20)
        )
    ).scalars().all()
    shortages = []
    if results:
        demand_nos = {r.demand_no for r in results}
        shortages = (
            await db.execute(
                select(KittingShortage)
                .where(
                    KittingShortage.demand_no.in_(demand_nos),
                    KittingShortage.is_deleted == 0,
                )
                .order_by(KittingShortage.is_key_material.desc(), KittingShortage.shortage_qty.desc())
                .limit(30)
            )
        ).scalars().all()
    bundle.tool_calls.append({
        "tool": "kitting.detail", "read_only": True,
        "params": {"anchor": f"{anchor.type}:{anchor.key}"},
        "rows": len(results) + len(shortages),
        "duration_ms": round((time.time() - started) * 1000, 1),
    })
    for r in results:
        bundle.evidence.append({
            "ref": f"control-platform://kitting/result/{r.demand_no}:{r.demand_line_no}",
            "source": "kitting",
            "title": f"齐套结果 {r.demand_no}:{r.demand_line_no}",
            "summary": (
                f"状态 {r.kit_status} / 齐套率(物料) {r.kit_rate_by_item} / "
                f"预计齐套 {r.estimated_kit_date or '?'} / 缺料 {r.shortage_item_count} 项 / 风险 {r.risk_level or '未评估'}"
            ),
            "data": {
                "demand_no": r.demand_no, "demand_line_no": r.demand_line_no,
                "product_code": r.product_code, "required_date": r.required_date.isoformat() if r.required_date else None,
                "kit_status": r.kit_status,
                "kit_rate_by_item": float(r.kit_rate_by_item) if r.kit_rate_by_item is not None else None,
                "kit_rate_by_qty": float(r.kit_rate_by_qty) if r.kit_rate_by_qty is not None else None,
                "estimated_kit_date": r.estimated_kit_date.isoformat() if r.estimated_kit_date else None,
                "shortage_item_count": r.shortage_item_count,
                "shortage_amount": float(r.shortage_amount) if r.shortage_amount is not None else None,
                "risk_level": r.risk_level, "key_material_shortage": r.key_material_shortage,
                "calculated_at": r.calculated_at.isoformat() if r.calculated_at else None,
            },
        })
    for s in shortages:
        bundle.evidence.append({
            "ref": f"control-platform://kitting/shortage/{s.demand_no}:{s.demand_line_no}/{s.material_code}",
            "source": "kitting",
            "title": f"缺料 {s.demand_no} / {s.material_code}",
            "summary": (
                f"缺口 {s.shortage_qty}（需求 {s.required_qty} / 可用 {s.available_qty} / 在途 {s.future_supply_qty}）"
                f" / 原因 {s.shortage_reason or '?'} / 供应商 {s.supplier_name or '?'}"
                + (" / 关键料" if s.is_key_material else "")
            ),
            "data": {
                "demand_no": s.demand_no, "demand_line_no": s.demand_line_no,
                "material_code": s.material_code, "material_name": s.material_name,
                "required_qty": float(s.required_qty) if s.required_qty is not None else None,
                "available_qty": float(s.available_qty) if s.available_qty is not None else None,
                "future_supply_qty": float(s.future_supply_qty) if s.future_supply_qty is not None else None,
                "shortage_qty": float(s.shortage_qty) if s.shortage_qty is not None else None,
                "required_date": s.required_date.isoformat() if s.required_date else None,
                "estimated_available_date": s.estimated_available_date.isoformat() if s.estimated_available_date else None,
                "shortage_days": s.shortage_days, "shortage_reason": s.shortage_reason,
                "supply_source": s.supply_source, "supplier_code": s.supplier_code,
                "supplier_name": s.supplier_name, "is_key_material": s.is_key_material,
                "owner_department": s.owner_department, "owner": s.owner,
            },
        })
    # 对外接口口径为 sync_only；此处并入源表 max，避免同步日志缺失时误判不可用（契约§14）
    sync_min = min_as_of(await load_source_as_of(db, KITTING_RESULT_SYNC_TYPES))
    table_max = await table_max_as_of(db, KittingResult.updated_at, KittingShortage.updated_at)
    candidates = [v for v in (sync_min, table_max) if v is not None]
    bundle.as_of = max(candidates) if candidates else None
    return bundle


async def collect_production_evidence(db: AsyncSession, anchor: BusinessAnchor) -> EvidenceBundle:
    """OA 生产任务单 —— 与 production_task_orders.list 同域（仅订单锚点）"""
    bundle = EvidenceBundle(source="production")
    if anchor.type != "order":
        return bundle
    started = time.time()
    rows = (
        await db.execute(
            select(ProductionTaskOrder)
            .where(ProductionTaskOrder.sale_order_no == anchor.key)
            .order_by(ProductionTaskOrder.id.asc()).limit(20)
        )
    ).scalars().all()
    bundle.tool_calls.append({
        "tool": "production_task_orders.detail", "read_only": True,
        "params": {"sale_order_no": anchor.key}, "rows": len(rows),
        "duration_ms": round((time.time() - started) * 1000, 1),
    })
    for row in rows:
        bundle.evidence.append({
            "ref": f"control-platform://production/task-order/{row.task_no or row.id}",
            "source": "production",
            "title": f"生产任务单 {row.task_no or row.id}",
            "summary": (
                f"车间 {row.workshop or '?'} / 物料 {row.material_name or row.material_code or '?'} / "
                f"计划 {row.planned_start_date or '?'}~{row.planned_end_date or '?'} / "
                f"实做 {row.actual_qty or 0}/{row.task_qty or '?'}"
                + (" / 已关闭" if row.is_closed else "")
            ),
            "data": {
                "task_id": row.task_id, "task_no": row.task_no, "workshop": row.workshop,
                "material_code": row.material_code, "material_name": row.material_name,
                "planned_start_date": row.planned_start_date.isoformat() if row.planned_start_date else None,
                "planned_end_date": row.planned_end_date.isoformat() if row.planned_end_date else None,
                "actual_start_date": row.actual_start_date.isoformat() if row.actual_start_date else None,
                "actual_end_date": row.actual_end_date.isoformat() if row.actual_end_date else None,
                "task_qty": float(row.task_qty) if row.task_qty is not None else None,
                "actual_qty": float(row.actual_qty) if row.actual_qty is not None else None,
                "repair_qty": float(row.repair_qty) if row.repair_qty is not None else None,
                "is_closed": row.is_closed, "audit_status": row.audit_status,
            },
        })
    # 与 production_task_orders 对外口径一致：源表 max，空表回退同步时间
    as_of = await table_max_as_of(db, ProductionTaskOrder.updated_at)
    if as_of is None:
        as_of = min_as_of(await load_source_as_of(db, ("production_task_orders",)))
    bundle.as_of = as_of
    return bundle


async def collect_quality_evidence(db: AsyncSession, anchor: BusinessAnchor) -> EvidenceBundle:
    """品质异常 —— 与 quality_issues.list 同域（订单 / 产品锚点直查；批次锚点经订单明细中转）"""
    bundle = EvidenceBundle(source="quality")
    if anchor.type == "order":
        condition = QualityIssue.order_no == anchor.key
    elif anchor.type == "product":
        condition = QualityIssue.product_code == anchor.key
    elif anchor.type == "batch":
        order_nos = (
            await db.execute(
                select(SaleOrderLine.order_no).where(SaleOrderLine.batch_no == anchor.key).limit(20)
            )
        ).scalars().all()
        if not order_nos:
            bundle.as_of = await table_max_as_of(db, QualityIssue.updated_at)
            return bundle
        condition = QualityIssue.order_no.in_(set(order_nos))
    else:
        return bundle
    started = time.time()
    rows = (
        await db.execute(
            select(QualityIssue)
            .where(condition, QualityIssue.is_deleted == False)  # noqa: E712 — SQLAlchemy 条件
            .order_by(QualityIssue.submit_date.desc().nullslast(), QualityIssue.id.desc())
            .limit(20)
        )
    ).scalars().all()
    bundle.tool_calls.append({
        "tool": "quality_issues.detail", "read_only": True,
        "params": {"anchor": f"{anchor.type}:{anchor.key}"}, "rows": len(rows),
        "duration_ms": round((time.time() - started) * 1000, 1),
    })
    for row in rows:
        bundle.evidence.append({
            "ref": f"control-platform://quality-issue/{row.issue_no}",
            "source": "quality",
            "title": f"品质异常 {row.issue_no}",
            "summary": (
                f"{row.defect_type or row.description or '?'} / 状态 {row.status} / "
                f"批次量 {row.batch_qty or '?'} 不良 {row.defect_qty or 0}"
            ),
            "data": {
                "issue_no": row.issue_no, "status": row.status,
                "order_no": row.order_no, "product_code": row.product_code,
                "product_name": row.product_name, "process": row.process,
                "defect_type": row.defect_type, "description": row.description,
                "batch_qty": row.batch_qty, "sample_qty": row.sample_qty,
                "defect_qty": row.defect_qty,
                "submit_date": row.submit_date.isoformat() if row.submit_date else None,
                "responsible_dept": row.responsible_dept,
            },
        })
    bundle.as_of = await table_max_as_of(db, QualityIssue.updated_at)
    return bundle


# 任务类型 → 采集器组合
TASK_COLLECTORS: dict[str, tuple[Callable[..., Any], ...]] = {
    "order_delivery_analysis": (
        collect_order_evidence, collect_kitting_evidence,
        collect_production_evidence, collect_quality_evidence,
    ),
    "material_kitting_analysis": (collect_kitting_evidence, collect_order_evidence),
    "quality_analysis": (collect_quality_evidence, collect_order_evidence),
    "production_analysis": (collect_production_evidence, collect_order_evidence),
}


# ═══════════════════════════════════════════
# 大模型调用（单测替换点：monkeypatch _invoke_reasoning_llm）
# ═══════════════════════════════════════════

_SYSTEM_CONSTRAINTS = (
    "你是中台（SPC）的只读业务分析智能体。请基于「证据」小节中明确列出的数据回答分析问题，遵守：\n"
    "1) 只能依据证据中存在的数据，不得虚构、不得外推不存在的数据；证据不含的信息不要臆测；\n"
    "2) 每条结论必须在 evidence_refs 中引用证据的 ref URI，无法引用证据的内容不要输出；\n"
    "3) 金额、承诺、质量、法律类判断的 recommendation 必须标注「需人工确认」；\n"
    "4) 你只能做只读分析，不执行也不建议任何写操作；结论供参考，不构成业务事实；\n"
    "5) confidence 口径：high=多源证据相互印证，medium=单源证据，low=证据不足或相互矛盾。"
)


def build_analysis_prompt(prompt: str, task_type: str, evidence: list[dict]) -> str:
    lines = [
        _SYSTEM_CONSTRAINTS, "",
        f"## 分析任务（task_type={task_type}）", prompt, "",
        "## 证据（只读采集自中台业务库）",
    ]
    for ev in evidence:
        data_text = json.dumps(ev["data"], ensure_ascii=False, default=str)
        if len(data_text) > 1200:
            data_text = data_text[:1200] + "…"
        lines.append(f"- ref: {ev['ref']}\n  摘要: {ev['summary']}\n  数据: {data_text}")
    lines.append("")
    lines.append("请输出 JSON：summary（总体结论，≤300字）与 conclusions[]（matter / evidence_refs / risk / recommendation / confidence）。")
    return "\n".join(lines)


async def _invoke_reasoning_llm(prompt: str, timeout_s: int) -> tuple[ReasoningAnalysis, dict]:
    """调用中台大模型结构化输出，返回 (分析结果, 真实 token 用量)。rule_based 视为未接通，绝不以规则结果冒充。"""
    provider_name = ai_service.current_provider()
    if provider_name == "rule_based":
        raise UpstreamUnavailableError(
            "中台推理智能体未接通：未配置真实大模型 provider（当前为 rule_based），拒绝伪造推理结果"
        )
    usage_out: dict = {}
    try:
        analysis = await ai_service.structured_output(
            prompt, ReasoningAnalysis,
            options=ChatOptions(temperature=0.2, max_tokens=3000, timeout=timeout_s, usage_out=usage_out),
        )
        return analysis, usage_out
    except ReasoningError:
        raise
    except Exception as e:
        raise UpstreamUnavailableError(f"中台大模型调用失败：{e}") from e


def _provider_model_name() -> Optional[str]:
    provider = ai_service.get_provider()
    return getattr(provider, "_model", None)


# ═══════════════════════════════════════════
# 任务注册表（进程内）与取消
# ═══════════════════════════════════════════

class _RunningHandle:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.cancel_event = asyncio.Event()
        self.started_at = datetime.now()


_running_tasks: dict[str, _RunningHandle] = {}


def running_count() -> int:
    return len(_running_tasks)


async def cancel_task(task_id: str) -> Optional[str]:
    """请求取消运行中的推理任务。返回 "cancelling"；任务不在运行则返回 None（由调用方查终态）。"""
    handle = _running_tasks.get(task_id)
    if handle is None:
        return None
    handle.cancel_event.set()
    logger.info("推理任务 %s 收到取消请求", task_id)
    return "cancelling"


def _check_cancelled(handle: _RunningHandle):
    if handle.cancel_event.is_set():
        raise TaskCancelledError(f"推理任务 {handle.task_id} 已被调用方取消")


# ═══════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════

async def _gather_evidence(db: AsyncSession, task_type: str, anchor: BusinessAnchor) -> tuple[list[dict], list[dict], Optional[datetime]]:
    """按任务类型采集证据；单域失败不致命（记入 tool_calls 审计），全部无证据由调用方判 404。"""
    bundles = []
    for collector in TASK_COLLECTORS[task_type]:
        try:
            bundles.append(await collector(db, anchor))
        except Exception as e:  # noqa: BLE001 — 单域不可用降级，任务继续
            logger.warning("证据采集失败 collector=%s error=%s", getattr(collector, "__name__", "?"), e)
            bundles.append(EvidenceBundle(source=getattr(collector, "__name__", "?"), error=str(e)))

    evidence: list[dict] = []
    tool_calls: list[dict] = []
    as_of_values: list[datetime] = []
    for bundle in bundles:
        tool_calls.extend(bundle.tool_calls)
        if bundle.error:
            tool_calls.append({"tool": bundle.source, "read_only": True, "error": bundle.error})
            continue
        evidence.extend(bundle.evidence)
        if bundle.evidence and bundle.as_of is not None:
            as_of_values.append(bundle.as_of)

    settings = get_settings()
    if len(evidence) > settings.REASONING_MAX_EVIDENCE_ITEMS:
        evidence = evidence[: settings.REASONING_MAX_EVIDENCE_ITEMS]
    # 整体时效 = 各证据来源的薄弱环节（min），与对外接口多源口径一致
    return evidence, tool_calls, (min(as_of_values) if as_of_values else None)


async def run_reasoning_task(
    db: AsyncSession,
    *,
    task_id: str,
    task_type: str,
    prompt: str,
    context: Optional[dict],
    constraints: Optional[dict],
    api_key_id: Optional[int],
    api_key_name: Optional[str],
    app_key: Optional[str],
    request_id: Optional[str],
) -> dict:
    """执行一次只读推理；失败抛 ReasoningError 子类（终态已落审计后 re-raise）。"""
    settings = get_settings()
    context = context or {}
    constraints = constraints or {}
    require_evidence = bool(constraints.get("require_evidence", True))
    if constraints.get("read_only") is False:
        raise InvalidRequestError("constraints.read_only 必须为 true：中台仅接受只读推理任务")
    if task_type not in TASK_TYPES:
        raise InvalidRequestError(f"task_type 不支持：{task_type}（当前支持 {sorted(TASK_TYPES)}）")
    anchor = parse_business_object_ref(context.get("businessObjectRef"))

    handle = _RunningHandle(task_id)
    _running_tasks[task_id] = handle
    started = time.time()
    record = ReasoningTask(
        task_id=task_id, task_type=task_type, prompt=prompt,
        context_json=context, constraints_json={"read_only": True, "require_evidence": require_evidence},
        status="running", api_key_id=api_key_id, api_key_name=api_key_name,
        app_key=app_key, request_id=request_id,
    )
    db.add(record)
    # running 态先提交，让状态/取消请求在其它会话可见（同 log_call 的显式提交先例）
    await db.commit()

    llm_meta: dict = {"called": False, "provider": None, "model": None, "latency_ms": None}
    evidence: list[dict] = []
    tool_calls: list[dict] = []
    result: Optional[dict] = None

    async def _finalize(status: str, error: Optional[ReasoningError] = None):
        record.status = status
        record.duration_ms = round((time.time() - started) * 1000, 1)
        record.finished_at = datetime.now()
        record.evidence_json = evidence
        record.tool_calls_json = tool_calls
        record.llm_called = 1 if llm_meta["called"] else 0
        record.llm_provider = llm_meta["provider"]
        record.llm_model = llm_meta["model"]
        record.llm_latency_ms = llm_meta["latency_ms"]
        if error is not None:
            record.error_code = error.code
            record.error_message = error.message
        if result is not None:
            record.result_json = result
            record.data_as_of = datetime.fromisoformat(result["data_as_of"]) if result["data_as_of"] else None
            record.data_confidence = result["data_confidence"]
            record.dropped_conclusion_count = result.get("dropped_conclusions", 0)

    try:
        # 1) 证据采集
        evidence, tool_calls, data_as_of = await _gather_evidence(db, task_type, anchor)
        _check_cancelled(handle)
        if not evidence:
            raise EmptyResultError(
                f"业务对象 business://{anchor.type}/{anchor.key} 在中台无可用证据"
                f"（可能不存在或数据源暂时不可用），无法执行分析——此情形不代表无风险"
            )

        # 2) 数据时效（过期不报错：降级置信度 + STALE_DATA 警告）
        data_confidence, stale = freshness_of(data_as_of)
        warnings = ["STALE_DATA"] if stale else []

        # 3) 大模型推理（取消 / 超时 / 上游不可用 三路竞争）
        _check_cancelled(handle)
        remaining = max(settings.REASONING_TIMEOUT_S - (time.time() - started), 1)
        prompt_text = build_analysis_prompt(prompt, task_type, evidence)
        llm_started = time.time()
        llm_task = asyncio.create_task(_invoke_reasoning_llm(prompt_text, int(remaining)))
        cancel_wait = asyncio.create_task(handle.cancel_event.wait())
        done, _pending = await asyncio.wait(
            {llm_task, cancel_wait}, timeout=remaining, return_when=asyncio.FIRST_COMPLETED,
        )
        if cancel_wait in done and llm_task not in done:
            llm_task.cancel()
            raise TaskCancelledError(f"推理任务 {task_id} 已被调用方取消")
        if llm_task in done:
            if llm_task.exception() is not None:
                raise llm_task.exception()
            analysis, llm_usage = llm_task.result()
        else:
            llm_task.cancel()
            cancel_wait.cancel()
            raise ReasoningTimeoutError(
                f"推理超时：任务 {task_id} 超过 {settings.REASONING_TIMEOUT_S}s 上限"
            )
        cancel_wait.cancel()
        llm_meta.update(
            called=True, provider=ai_service.current_provider(),
            model=_provider_model_name(),
            latency_ms=round((time.time() - llm_started) * 1000, 1),
        )
        logger.info(
            "推理任务 %s 实际调用中台大模型 provider=%s model=%s latency_ms=%s",
            task_id, llm_meta["provider"], llm_meta["model"], llm_meta["latency_ms"],
        )

        # 4) 结论证据校验（require_evidence=true 时无证据结论剔除）
        kept, dropped = validate_conclusions(analysis, evidence, require_evidence, settings.REASONING_MAX_CONCLUSIONS)

        result = {
            "task_id": task_id,
            "task_type": task_type,
            "status": "succeeded",
            "summary": analysis.summary,
            "conclusions": [c.model_dump() for c in kept],
            "dropped_conclusions": dropped,
            "evidence_refs": [ev["ref"] for ev in evidence],
            "data_as_of": data_as_of.isoformat() if data_as_of else None,
            "data_confidence": data_confidence,
            "stale": stale,
            "warnings": warnings,
            "llm": llm_meta,
            "usage": {
                "modelId": llm_meta["model"] or "",
                "tokensIn": int(llm_usage.get("prompt_tokens", 0) or 0),
                "cachedTokens": int(llm_usage.get("cached_tokens", 0) or 0),
                "tokensOut": int(llm_usage.get("completion_tokens", 0) or 0),
            },
            "duration_ms": round((time.time() - started) * 1000, 1),
            "request_id": request_id,
        }
        await _finalize("succeeded")
        return result
    except ReasoningError as e:
        await _finalize(e.status, error=e)
        raise
    except Exception as e:  # noqa: BLE001 — 未预期异常统一 500 并留痕
        logger.exception("推理任务 %s 内部错误", task_id)
        wrapped = ReasoningError(f"推理任务内部错误：{e}")
        await _finalize("failed", error=wrapped)
        raise wrapped from e
    finally:
        _running_tasks.pop(task_id, None)


# ═══════════════════════════════════════════
# 任务视图（状态/取消接口用）
# ═══════════════════════════════════════════

def _serialize_record(record: ReasoningTask) -> dict:
    view: dict = {
        "task_id": record.task_id,
        "task_type": record.task_type,
        "status": record.status,
        "error_code": record.error_code,
        "error_message": record.error_message,
        "dropped_conclusions": record.dropped_conclusion_count,
        "llm_called": bool(record.llm_called),
        "llm_provider": record.llm_provider,
        "llm_model": record.llm_model,
        "data_as_of": record.data_as_of.isoformat() if record.data_as_of else None,
        "data_confidence": record.data_confidence,
        "duration_ms": float(record.duration_ms) if record.duration_ms is not None else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "finished_at": record.finished_at.isoformat() if record.finished_at else None,
        "request_id": record.request_id,
    }
    if record.status == "succeeded" and record.result_json:
        result = dict(record.result_json)
        view["summary"] = result.get("summary")
        view["conclusions"] = result.get("conclusions", [])
        view["evidence_refs"] = result.get("evidence_refs", [])
        view["warnings"] = result.get("warnings", [])
    return view


async def get_task_view(db: AsyncSession, task_id: str) -> Optional[dict]:
    """运行中 → 实时视图；已结束 → 审计记录视图；不存在 → None。"""
    handle = _running_tasks.get(task_id)
    if handle is not None:
        return {
            "task_id": task_id,
            "status": "running",
            "cancellation_requested": handle.cancel_event.is_set(),
            "started_at": handle.started_at.isoformat(),
        }
    record = (
        await db.execute(select(ReasoningTask).where(ReasoningTask.task_id == task_id))
    ).scalar_one_or_none()
    if record is None:
        return None
    return _serialize_record(record)


def new_task_id() -> str:
    return f"rt-{uuid.uuid4().hex}"
