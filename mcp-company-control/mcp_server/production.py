"""生产协同类只读 Tool（工单/工序/订单关联/报工/产能）— 对齐 SPC 生产协同中心链路交接文档 §5/§6

与建议契约的已确认偏差（SPC 数据现实，见 SPC 仓库 docs/superpowers/plans/2026-09-23-spc-production-external-api.md）：
- 工单以 OA 生产任务单（production_task_order）为源；cancelled 无来源永不产出
- 工序无工单外键：operations 必填 order_no（非 work_order_no）
- 工单-订单关系为订单级（任务单只带 sale_order_no）：line_no/order_line_id 恒 null；
  另暴露 schedule_snapshot 源（订单行级排产快照，无工单号）
- 报工为 ERP 生产日报累计口径：is_reversed/reversal_of/revision 恒 null
- 产能按（部门, 排产段, 日期）聚合：available 来自排产基础条件，周日不排产为 0

时效（交接文档 §7）：调用公共 list_result 前强制校验真实 data_as_of/置信度，
缺失或非法返回结构化 UPSTREAM_UNAVAILABLE「数据置信度不足」，不落入 helper 默认兜底
（缺失时间→当前时间 / 未知置信度→high）。
"""

from __future__ import annotations

from typing import Annotated, Any, Dict

from pydantic import Field

from .contracts import BizError
from .tool_helpers import (
    READ_ONLY_TOOL,
    Page,
    PageSize,
    RequestId,
    filter_params,
    list_result,
    parse_date,
    parse_iso_datetime,
    tool_error_envelope,
)
from .upstream_client import call as upstream

_VALID_CONFIDENCE = ("high", "medium", "low")


def _require_freshness(payload: Dict[str, Any]) -> None:
    """交接文档 §7：stale → STALE_DATA；缺失/非法时效 → 数据置信度不足，
    不落入公共 helper 默认兜底（缺失时间→当前时间 / 未知置信度→high）。"""
    if payload.get("stale") is True:
        raise BizError("STALE_DATA", "上游数据已过期，超出新鲜度阈值")
    as_of = payload.get("data_as_of")
    confidence = str(payload.get("data_confidence") or "").lower()
    if not as_of or confidence not in _VALID_CONFIDENCE:
        raise BizError(
            "UPSTREAM_UNAVAILABLE",
            "上游缺少有效 data_as_of / data_confidence，数据置信度不足，停止生产风险判断",
        )


def _validate_range(start: str, end: str, name: str) -> None:
    start_date = parse_date(start, f"{name}_start")
    end_date = parse_date(end, f"{name}_end")
    if start_date > end_date:
        raise BizError("INVALID_ARGUMENT", f"{name}_start 不能晚于 {name}_end")


def register_production_tools(mcp) -> None:
    """注册 5 个生产协同类 Tool（由 server.py 调用一次）"""

    @mcp.tool(annotations=READ_ONLY_TOOL)
    @tool_error_envelope
    async def production_work_orders_list(
        work_order_no: Annotated[str, Field(max_length=64, description="任务单号精确匹配")] = "",
        order_no: Annotated[str, Field(max_length=64, description="销售订单号精确匹配")] = "",
        product_code: Annotated[str, Field(max_length=64, description="物料代码精确匹配")] = "",
        status: Annotated[str, Field(max_length=120, description="标准状态逗号分隔多选：planned/released/in_progress/completed/unknown（cancelled 无来源）")] = "",
        workshop: Annotated[str, Field(max_length=128, description="生产车间精确匹配")] = "",
        planned_end_start: Annotated[str, Field(max_length=10, description="计划完工日期起 YYYY-MM-DD（含）")] = "",
        planned_end_end: Annotated[str, Field(max_length=10, description="计划完工日期止 YYYY-MM-DD（含）")] = "",
        updated_after: Annotated[str, Field(max_length=40, description="增量同步锚点 ISO 8601")] = "",
        page: Page = 1,
        page_size: PageSize = 20,
        request_id: RequestId = "",
    ) -> Dict[str, Any]:
        """分页查询生产工单（OA 生产任务单快照，只读）。数量口径 task/actual/repair；状态映射待生产负责人签认，status_raw 保留源语义；uom/入库/预测完工无来源恒 null。"""
        if planned_end_start and planned_end_end:
            _validate_range(planned_end_start, planned_end_end, "planned_end")
        if updated_after:
            parse_iso_datetime(updated_after, "updated_after")
        params = filter_params(
            page=page, page_size=page_size, work_order_no=work_order_no, order_no=order_no,
            product_code=product_code, status=status, workshop=workshop,
            planned_end_start=planned_end_start, planned_end_end=planned_end_end,
            updated_after=updated_after, request_id=request_id,
        )
        payload = await upstream("/external/production/work-orders/list", params)
        _require_freshness(payload)
        return list_result(
            "production_work_orders_list", payload, page=page, page_size=page_size,
            request_id=request_id, evidence_entity="production-work-order",
            evidence_id=lambda row: str(row.get("work_order_id") or ""),
        )

    @mcp.tool(annotations=READ_ONLY_TOOL)
    @tool_error_envelope
    async def production_operations_list(
        order_no: Annotated[str, Field(max_length=64, description="订单号精确匹配（必填：SPC 工序进度无工单外键）")] = "",
        process_type: Annotated[str, Field(max_length=120, description="工序类型逗号分隔多选：前道/贴片/精益/组装/包装")] = "",
        status: Annotated[str, Field(max_length=120, description="原始状态逗号分隔多选，如 pending,in_progress")] = "",
        plan_date_start: Annotated[str, Field(max_length=10, description="计划日期起 YYYY-MM-DD（含）")] = "",
        plan_date_end: Annotated[str, Field(max_length=10, description="计划日期止 YYYY-MM-DD（含）")] = "",
        updated_after: Annotated[str, Field(max_length=40, description="增量同步锚点 ISO 8601")] = "",
        page: Page = 1,
        page_size: PageSize = 20,
        request_id: RequestId = "",
    ) -> Dict[str, Any]:
        """分页查询工序进度（只读）。order_no 必填（SPC 无工单级工序）；工单/工作中心/前置工序无来源恒 null，不假设线性工艺。"""
        if not order_no:
            raise BizError("INVALID_ARGUMENT", "order_no 必填（SPC 工序进度以订单号为锚点，无工单外键）")
        if plan_date_start and plan_date_end:
            _validate_range(plan_date_start, plan_date_end, "plan_date")
        if updated_after:
            parse_iso_datetime(updated_after, "updated_after")
        params = filter_params(
            page=page, page_size=page_size, order_no=order_no, process_type=process_type,
            status=status, plan_date_start=plan_date_start, plan_date_end=plan_date_end,
            updated_after=updated_after, request_id=request_id,
        )
        payload = await upstream("/external/production/operations/list", params)
        _require_freshness(payload)
        return list_result(
            "production_operations_list", payload, page=page, page_size=page_size,
            request_id=request_id, evidence_entity="production-operation",
            evidence_id=lambda row: str(row.get("operation_id") or ""),
        )

    @mcp.tool(annotations=READ_ONLY_TOOL)
    @tool_error_envelope
    async def production_order_links_list(
        work_order_no: Annotated[str, Field(max_length=64, description="任务单号精确匹配（与 order_no 至少一个）")] = "",
        order_no: Annotated[str, Field(max_length=64, description="销售订单号精确匹配（与 work_order_no 至少一个）")] = "",
        link_type: Annotated[str, Field(max_length=64, description="关联来源逗号分隔多选：production_task,schedule_snapshot")] = "",
        updated_after: Annotated[str, Field(max_length=40, description="增量同步锚点 ISO 8601")] = "",
        page: Page = 1,
        page_size: PageSize = 20,
        request_id: RequestId = "",
    ) -> Dict[str, Any]:
        """分页查询工单与销售订单关系（只读）。双源：production_task（订单级，line_no 恒 null）+ schedule_snapshot（行级排产快照，无工单号）；禁止按产品编码推断关联。"""
        if not (work_order_no or order_no):
            raise BizError("INVALID_ARGUMENT", "work_order_no / order_no 至少提供一个")
        if updated_after:
            parse_iso_datetime(updated_after, "updated_after")
        params = filter_params(
            page=page, page_size=page_size, work_order_no=work_order_no, order_no=order_no,
            link_type=link_type, updated_after=updated_after, request_id=request_id,
        )
        payload = await upstream("/external/production/order-links/list", params)
        _require_freshness(payload)
        return list_result(
            "production_order_links_list", payload, page=page, page_size=page_size,
            request_id=request_id, evidence_entity="production-order-link",
            evidence_id=lambda row: str(row.get("link_id") or ""),
        )

    @mcp.tool(annotations=READ_ONLY_TOOL)
    @tool_error_envelope
    async def production_reports_list(
        work_order_no: Annotated[str, Field(max_length=64, description="生产订单号精确匹配（必填锚点）")] = "",
        order_no: Annotated[str, Field(max_length=64, description="销售订单号精确匹配")] = "",
        report_date_start: Annotated[str, Field(max_length=10, description="报工日期起 YYYY-MM-DD（含）")] = "",
        report_date_end: Annotated[str, Field(max_length=10, description="报工日期止 YYYY-MM-DD（含）")] = "",
        updated_after: Annotated[str, Field(max_length=40, description="增量同步锚点 ISO 8601")] = "",
        page: Page = 1,
        page_size: PageSize = 20,
        request_id: RequestId = "",
    ) -> Dict[str, Any]:
        """分页查询生产报工（ERP 生产日报，只读）。work_order_no 必填；累计口径，撤销/更正无来源恒 null（is_reversed/reversal_of/revision），不重复计数。"""
        if not work_order_no:
            raise BizError("INVALID_ARGUMENT", "work_order_no 必填（按生产订单号查询 ERP 生产日报）")
        if report_date_start and report_date_end:
            _validate_range(report_date_start, report_date_end, "report_date")
        if updated_after:
            parse_iso_datetime(updated_after, "updated_after")
        params = filter_params(
            page=page, page_size=page_size, work_order_no=work_order_no, order_no=order_no,
            report_date_start=report_date_start, report_date_end=report_date_end,
            updated_after=updated_after, request_id=request_id,
        )
        payload = await upstream("/external/production/reports/list", params)
        _require_freshness(payload)
        return list_result(
            "production_reports_list", payload, page=page, page_size=page_size,
            request_id=request_id, evidence_entity="production-report",
            evidence_id=lambda row: str(row.get("report_id") or ""),
        )

    @mcp.tool(annotations=READ_ONLY_TOOL)
    @tool_error_envelope
    async def production_capacity_list(
        department: Annotated[str, Field(max_length=32, description="车间/部门精确匹配（缺省为全部）")] = "",
        schedule_bucket: Annotated[str, Field(max_length=32, description="排产段精确匹配：lean/assembly/packaging")] = "",
        date_start: Annotated[str, Field(max_length=10, description="日期起 YYYY-MM-DD（必填，含）")] = "",
        date_end: Annotated[str, Field(max_length=10, description="日期止 YYYY-MM-DD（必填，含）")] = "",
        updated_after: Annotated[str, Field(max_length=40, description="增量同步锚点 ISO 8601")] = "",
        page: Page = 1,
        page_size: PageSize = 20,
        request_id: RequestId = "",
    ) -> Dict[str, Any]:
        """分页查询产能占用与可用分钟（只读）。date_start/date_end 必填；按（部门, 排产段, 日期）聚合；可用分钟缺基础条件为 null，周日不排产为 0，不做除零负荷率。"""
        if not (date_start and date_end):
            raise BizError("INVALID_ARGUMENT", "date_start / date_end 必填（产能按日期窗口聚合）")
        _validate_range(date_start, date_end, "date")
        if updated_after:
            parse_iso_datetime(updated_after, "updated_after")
        params = filter_params(
            page=page, page_size=page_size, department=department, schedule_bucket=schedule_bucket,
            date_start=date_start, date_end=date_end, updated_after=updated_after, request_id=request_id,
        )
        payload = await upstream("/external/production/capacity/list", params)
        _require_freshness(payload)
        return list_result(
            "production_capacity_list", payload, page=page, page_size=page_size,
            request_id=request_id, evidence_entity="production-capacity",
            evidence_id=lambda row: "/".join(
                str(p) for p in (row.get("work_center_code"), row.get("capacity_date")) if p
            ),
        )
