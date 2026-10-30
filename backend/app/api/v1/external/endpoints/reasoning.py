"""执行面推理对外接口（AEOS reason_control_platform，任务书 2026-10 版）

- POST /reasoning/analyze        同步执行只读推理（可被取消/超时中断）
- POST /reasoning/tasks/{id}/cancel   取消进行中的推理任务（Hub 召回联动，幂等）
- GET  /reasoning/tasks/{id}          任务状态 / 结果视图（运行中读内存，已结束读审计）

鉴权与查询接口同套 HMAC（X-App-Key + X-Timestamp + X-Signature，
签名串 = timestamp + app_key + endpoint_code + query_string；POST body 不参与签名）。
"""

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.basicdata.data_supply import DataSupplyApiKey
from app.schemas.common import ResponseModel
from app.services import reasoning as reasoning_service
from app.services.agent.capabilities import CONFIGURABLE_CAPABILITIES

from ..common import ExternalEnvelopeError
from ..deps import external_auth
from ..log_wrap import log_external_call
from ..registry import register_external

router = APIRouter(prefix="/reasoning", tags=["执行面推理"])


class ReasoningAnalyzeRequest(BaseModel):
    """dispatch.input 等价结构（多余字段容忍，向前兼容）"""

    model_config = ConfigDict(extra="ignore")

    prompt: str = Field(..., description="分析问题（≤2000 字符）")
    task_type: str = Field(..., description="任务类型：order_delivery_analysis / material_kitting_analysis / quality_analysis / production_analysis")
    context: Optional[dict] = Field(
        None,
        description='业务锚点，如 {"businessObjectRef": "business://order/HJY20260903-261"}',
    )
    constraints: Optional[dict] = Field(
        None,
        description='约束，如 {"read_only": true, "require_evidence": true}；read_only 必须为 true',
    )
    task_id: Optional[str] = Field(
        None, max_length=64,
        description="调用方任务 ID（缺省服务端生成）；取消/状态接口按此寻址，Hub 侧传 dispatch.task_id",
    )
    request_id: Optional[str] = Field(None, max_length=128, description="调用方请求 ID（回显）")

    @field_validator("prompt")
    @classmethod
    def _prompt_within_limit(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("prompt 不能为空")
        if len(v) > 2000:
            raise ValueError("prompt 长度不能超过 2000 字符")
        return v


class ReasoningConclusionOut(BaseModel):
    matter: str
    evidence_refs: List[str] = []
    risk: Optional[str] = None
    recommendation: Optional[str] = None
    confidence: Literal["high", "medium", "low"] = "medium"


class ReasoningLLMMetaOut(BaseModel):
    """大模型调用元信息（审计证明：任务确实调用了中台大模型）"""

    called: bool = False
    provider: Optional[str] = None
    model: Optional[str] = None
    latency_ms: Optional[float] = None


class ReasoningUsageOut(BaseModel):
    """大模型 Token 用量（执行面透传给 Hub run_complete.usage 记用量台账）"""

    modelId: str = ""
    tokensIn: int = 0
    cachedTokens: int = 0
    tokensOut: int = 0


class ReasoningResultOut(BaseModel):
    """run_complete.result 等价结构"""

    task_id: str
    task_type: str
    status: str
    summary: Optional[str] = None
    conclusions: List[ReasoningConclusionOut] = []
    dropped_conclusions: int = 0
    evidence_refs: List[str] = []
    data_as_of: Optional[str] = None
    data_confidence: Optional[Literal["high", "medium", "low"]] = None
    stale: bool = False
    warnings: List[str] = []
    llm: Optional[ReasoningLLMMetaOut] = None
    usage: Optional[ReasoningUsageOut] = None
    duration_ms: Optional[int] = None
    idempotent_replay: bool = False
    request_id: Optional[str] = None


class ReasoningTaskViewOut(BaseModel):
    task_id: str
    status: str
    task_type: Optional[str] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    summary: Optional[str] = None
    conclusions: List[ReasoningConclusionOut] = []
    dropped_conclusions: int = 0
    llm_called: bool = False
    llm_provider: Optional[str] = None
    data_as_of: Optional[str] = None
    data_confidence: Optional[str] = None
    duration_ms: Optional[int] = None
    cancellation_requested: Optional[bool] = None


@router.post("/analyze", response_model=ResponseModel[ReasoningResultOut],
             summary="只读推理分析", description="endpoint_code: reasoning.analyze")
@register_external(
    "reasoning.analyze", "只读推理分析", method="POST", path="/reasoning/analyze",
    description="调用中台大模型对业务数据做只读分析，返回带 evidence_refs 的结构化结论；"
                "空结果/上游不可用/超时/取消分别返回 404/503/504/490 信封码",
    tags=["执行面推理"],
)
@log_external_call("reasoning.analyze")
async def reasoning_analyze(
    request: Request,
    payload: ReasoningAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    key: DataSupplyApiKey = Depends(external_auth("reasoning.analyze")),
):
    actor_capabilities = getattr(request.state, "actor_capabilities", None)
    if actor_capabilities is not None:
        allowed_types = set()
        for code in actor_capabilities:
            cap = CONFIGURABLE_CAPABILITIES.get(code)
            if cap:
                allowed_types |= set(cap.reasoning_types)
        if payload.task_type not in allowed_types:
            raise HTTPException(status_code=403, detail="当前智能体没有该推理任务类型的能力")
    if reasoning_service.running_count() >= get_settings().REASONING_MAX_CONCURRENT:
        raise HTTPException(
            status_code=429,
            detail=f"并发推理任务已达上限 {get_settings().REASONING_MAX_CONCURRENT}，请稍后重试",
            headers={"Retry-After": "10"},
        )
    task_id = payload.task_id or reasoning_service.new_task_id()
    try:
        result = await reasoning_service.run_reasoning_task(
            db,
            task_id=task_id,
            task_type=payload.task_type,
            prompt=payload.prompt,
            context=payload.context,
            constraints=payload.constraints,
            api_key_id=key.id,
            api_key_name=key.key_name,
            app_key=key.app_key,
            request_id=payload.request_id,
        )
    except reasoning_service.ReasoningError as e:
        raise ExternalEnvelopeError(e.code, e.message)
    return result


@router.post("/tasks/{task_id}/cancel", response_model=ResponseModel[ReasoningTaskViewOut],
             summary="取消推理任务", description="endpoint_code: reasoning.cancel")
@register_external(
    "reasoning.cancel", "取消推理任务", method="POST", path="/reasoning/tasks/{task_id}/cancel",
    description="取消一个进行中的推理任务（Hub 召回联动）；任务已结束则幂等返回终态",
    tags=["执行面推理"],
)
@log_external_call("reasoning.cancel", path_params=("task_id",))
async def reasoning_cancel(
    task_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    key: DataSupplyApiKey = Depends(external_auth("reasoning.cancel")),
):
    outcome = await reasoning_service.cancel_task(task_id)
    if outcome is not None:
        return {"task_id": task_id, "status": outcome, "cancellation_requested": True}
    view = await reasoning_service.get_task_view(db, task_id)
    if view is None:
        raise ExternalEnvelopeError(404, f"推理任务 {task_id} 不存在")
    return view


@router.get("/tasks/{task_id}", response_model=ResponseModel[ReasoningTaskViewOut],
            summary="推理任务状态", description="endpoint_code: reasoning.task")
@register_external(
    "reasoning.task", "推理任务状态", method="GET", path="/reasoning/tasks/{task_id}",
    description="查询推理任务状态与结果（运行中/已结束），供调用方审计与轮询",
    tags=["执行面推理"],
)
@log_external_call("reasoning.task", path_params=("task_id",))
async def reasoning_task_status(
    task_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    key: DataSupplyApiKey = Depends(external_auth("reasoning.task")),
):
    view = await reasoning_service.get_task_view(db, task_id)
    if view is None:
        raise ExternalEnvelopeError(404, f"推理任务 {task_id} 不存在")
    return view
