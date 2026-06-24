"""基础数据与集成中心 — 数据供给服务层"""

import hashlib
import hmac
import json
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select, func, desc, or_, inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.models.basicdata.data_supply import DataSupplyConfig, DataSupplyApiKey, DataSupplyCallLog
from app.services.basicdata.data_supply_registry import (
    DATA_TYPE_REGISTRY, DataTypeDefinition, get_data_type_definition,
)

logger = logging.getLogger(__name__)

# 签名有效期（秒），防重放攻击
SIGNATURE_TTL = 300

# 默认脱敏规则
_DEFAULT_MASK_RULES = {
    "phone": lambda v: v[:3] + "****" + v[-4:] if v and len(v) >= 7 else v,
    "email": lambda v: re.sub(r'(.{2}).*(@.*)', r'\1***\2', v) if v and "@" in v else v,
    "credit_code": lambda v: v[:6] + "********" if v and len(v) >= 14 else v,
}


def resolve_model(model_name: str) -> Optional[type]:
    """通过类名从 SQLAlchemy 注册表解析模型类"""
    for mapper in Base.registry.mappers:
        if mapper.class_.__name__ == model_name:
            return mapper.class_
    return None


def get_model_fields(model_cls: type) -> list[str]:
    """获取模型的所有列名"""
    return [c.name for c in inspect(model_cls).columns]


# ═══════════════════════════════════════════
# 数据类型查询（基于 Registry）
# ═══════════════════════════════════════════

async def get_available_data_types(db: AsyncSession) -> list[dict]:
    """获取所有已注册的数据类型（含配置状态）"""
    configs_result = await db.execute(select(DataSupplyConfig))
    configs = {c.data_type: c for c in configs_result.scalars().all()}

    result = []
    for data_type, definition in DATA_TYPE_REGISTRY.items():
        config = configs.get(data_type)
        # 配置中可覆盖 Registry 的默认值
        result.append({
            "data_type": data_type,
            "data_name": config.data_name if config else definition.data_name,
            "description": config.description if config and config.description else definition.description,
            "model_name": definition.model_name,
            "exposed_fields": definition.exposed_fields,
            "default_fields": definition.exposed_fields,
            "is_configured": config is not None,
            "is_active": config.is_active if config else False,
            "allowed_fields": json.loads(config.allowed_fields_json) if config and config.allowed_fields_json else definition.exposed_fields,
            "filter_fields": json.loads(config.filter_fields_json) if config and config.filter_fields_json else definition.filter_fields,
            "mask_fields": json.loads(config.mask_fields_json) if config and config.mask_fields_json else definition.mask_fields,
            "search_fields": definition.search_fields,
        })
    return result


async def get_data_type_options(db: AsyncSession) -> list[dict]:
    """获取已注册的数据类型选项（供前端下拉选择）"""
    configs_result = await db.execute(
        select(DataSupplyConfig).where(DataSupplyConfig.is_active == True)
    )
    configs = {c.data_type: c for c in configs_result.scalars().all()}

    result = []
    for data_type, definition in DATA_TYPE_REGISTRY.items():
        config = configs.get(data_type)
        if config:
            result.append({"value": data_type, "label": config.data_name})
        else:
            result.append({"value": data_type, "label": definition.data_name})
    return result


# ═══════════════════════════════════════════
# 认证相关
# ═══════════════════════════════════════════

async def validate_api_key(db: AsyncSession, api_key: str, data_type: str) -> Optional[DataSupplyApiKey]:
    """验证 API Key（兼容旧模式：X-API-Key 明文传输）"""
    result = await db.execute(
        select(DataSupplyApiKey).where(
            DataSupplyApiKey.api_key == api_key,
            DataSupplyApiKey.is_active == True,
        )
    )
    key_obj = result.scalar_one_or_none()
    if not key_obj:
        return None

    # 检查过期
    if key_obj.expires_at and key_obj.expires_at < datetime.now():
        return None

    # 检查数据类型权限
    if key_obj.allowed_data_types_json:
        allowed = json.loads(key_obj.allowed_data_types_json)
        if data_type not in allowed:
            return None

    return key_obj


async def validate_signature(
    db: AsyncSession,
    app_key: str,
    signature: str,
    timestamp: str,
    data_type: str,
    request_query_string: str = "",
) -> Optional[DataSupplyApiKey]:
    """验证 HMAC-SHA256 签名认证（推荐模式）"""
    try:
        ts = int(timestamp)
    except (ValueError, TypeError):
        return None

    now = int(time.time())
    if abs(now - ts) > SIGNATURE_TTL:
        return None

    result = await db.execute(
        select(DataSupplyApiKey).where(
            DataSupplyApiKey.app_key == app_key,
            DataSupplyApiKey.is_active == True,
        )
    )
    key_obj = result.scalar_one_or_none()
    if not key_obj or not key_obj.app_secret:
        return None

    if key_obj.expires_at and key_obj.expires_at < datetime.now():
        return None

    if key_obj.allowed_data_types_json:
        allowed = json.loads(key_obj.allowed_data_types_json)
        if data_type not in allowed:
            return None

    string_to_sign = f"{timestamp}{app_key}{data_type}{request_query_string}"
    expected_sig = hmac.new(
        key_obj.app_secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_sig):
        return None

    return key_obj


def check_ip_whitelist(key_obj: DataSupplyApiKey, client_ip: str) -> bool:
    """检查请求 IP 是否在白名单内"""
    if not key_obj.ip_whitelist_json:
        return True
    try:
        whitelist = json.loads(key_obj.ip_whitelist_json)
    except (json.JSONDecodeError, TypeError):
        return True
    if not whitelist:
        return True
    return client_ip in whitelist


# ═══════════════════════════════════════════
# 数据查询（基于 Registry 定义 + 可选业务 Service）
# ═══════════════════════════════════════════

def mask_field_value(field_name: str, value) -> any:
    """对字段值进行脱敏处理"""
    if value is None:
        return value
    str_val = str(value)
    fn_lower = field_name.lower()
    if "phone" in fn_lower or "mobile" in fn_lower or fn_lower == "tel":
        return _DEFAULT_MASK_RULES["phone"](str_val)
    if "email" in fn_lower or "mail" in fn_lower:
        return _DEFAULT_MASK_RULES["email"](str_val)
    if "credit_code" in fn_lower or "credit" in fn_lower:
        return _DEFAULT_MASK_RULES["credit_code"](str_val)
    if "id_card" in fn_lower or "idcard" in fn_lower or "identity" in fn_lower:
        if len(str_val) >= 15:
            return str_val[:3] + "***********" + str_val[-4:]
    return value


def apply_masking(items: list[dict], mask_fields: list[str]) -> list[dict]:
    """对结果集中的指定字段进行脱敏"""
    if not mask_fields:
        return items
    for item in items:
        for field_name in mask_fields:
            if field_name in item and item[field_name] is not None:
                item[field_name] = mask_field_value(field_name, item[field_name])
    return items


async def query_data(
    db: AsyncSession,
    data_type: str,
    config: DataSupplyConfig,
    page: int = 1,
    page_size: int = 20,
    keyword: Optional[str] = None,
    filters: Optional[dict] = None,
    updated_after: Optional[datetime] = None,
) -> dict:
    """通用数据查询

    优先使用 Registry 中定义的 service_fn（业务 Service），
    如果没有则回退到直接查表（基于 Registry 中定义的 exposed_fields）。
    """
    definition = get_data_type_definition(data_type)
    if not definition:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    # 优先使用业务 Service
    if definition.service_fn:
        try:
            result = await definition.service_fn(
                db=db, page=page, page_size=page_size,
                keyword=keyword, filters=filters, updated_after=updated_after,
            )
            return result
        except Exception as e:
            logger.error(f"业务 Service 调用失败 data_type={data_type}: {e}")
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

    # 回退到直接查表
    model_cls = resolve_model(definition.model_name)
    if not model_cls:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    # 使用配置覆盖或 Registry 默认值
    allowed_fields = json.loads(config.allowed_fields_json) if config and config.allowed_fields_json else definition.exposed_fields
    filter_fields = json.loads(config.filter_fields_json) if config and config.filter_fields_json else definition.filter_fields
    mask_fields = json.loads(config.mask_fields_json) if config and config.mask_fields_json else definition.mask_fields
    search_fields = definition.search_fields

    query = select(model_cls)

    # 关键字搜索
    if keyword and search_fields:
        conditions = []
        for field_name in search_fields:
            col = getattr(model_cls, field_name, None)
            if col is not None:
                conditions.append(col.ilike(f"%{keyword}%"))
        if conditions:
            query = query.where(or_(*conditions))

    # 自定义筛选
    if filters:
        for field_name, value in filters.items():
            col = getattr(model_cls, field_name, None)
            if col is not None and field_name in filter_fields:
                query = query.where(col == value)

    # 增量同步
    if updated_after:
        updated_at_col = getattr(model_cls, "updated_at", None)
        if updated_at_col is not None:
            query = query.where(updated_at_col >= updated_after)

    # 计数
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    rows = result.scalars().all()

    # 字段过滤 + 脱敏
    items = []
    for row in rows:
        row_dict = {}
        for field_name in allowed_fields:
            val = getattr(row, field_name, None)
            if isinstance(val, datetime):
                val = val.isoformat()
            row_dict[field_name] = val
        items.append(row_dict)

    items = apply_masking(items, mask_fields)
    return {"items": items, "total": total, "page": page, "page_size": page_size}


async def query_single_record(
    db: AsyncSession,
    data_type: str,
    config: DataSupplyConfig,
    record_id: int,
) -> Optional[dict]:
    """查询单条数据"""
    definition = get_data_type_definition(data_type)
    if not definition:
        return None

    model_cls = resolve_model(definition.model_name)
    if not model_cls:
        return None

    allowed_fields = json.loads(config.allowed_fields_json) if config and config.allowed_fields_json else definition.exposed_fields
    mask_fields = json.loads(config.mask_fields_json) if config and config.mask_fields_json else definition.mask_fields

    result = await db.execute(select(model_cls).where(model_cls.id == record_id))
    row = result.scalar_one_or_none()
    if not row:
        return None

    row_dict = {}
    for field_name in allowed_fields:
        val = getattr(row, field_name, None)
        if isinstance(val, datetime):
            val = val.isoformat()
        row_dict[field_name] = val

    row_dict = apply_masking([row_dict], mask_fields)[0]
    return row_dict


# ═══════════════════════════════════════════
# 日志与统计
# ═══════════════════════════════════════════

async def log_call(
    db: AsyncSession,
    api_key_id: Optional[int],
    api_key_name: Optional[str],
    data_type: str,
    request_params: Optional[dict],
    response_status: int,
    response_count: int,
    ip_address: Optional[str],
    user_agent: Optional[str],
    duration_ms: float,
):
    """记录调用日志"""
    log = DataSupplyCallLog(
        api_key_id=api_key_id,
        api_key_name=api_key_name,
        data_type=data_type,
        request_params_json=json.dumps(request_params, ensure_ascii=False, default=str) if request_params else None,
        response_status=response_status,
        response_count=response_count,
        ip_address=ip_address,
        user_agent=user_agent,
        duration_ms=duration_ms,
    )
    db.add(log)
    await db.commit()


async def get_call_statistics(
    db: AsyncSession,
    api_key_id: Optional[int] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> dict:
    """获取调用统计"""
    base_q = select(DataSupplyCallLog)
    if api_key_id:
        base_q = base_q.where(DataSupplyCallLog.api_key_id == api_key_id)
    if start_date:
        base_q = base_q.where(DataSupplyCallLog.called_at >= start_date)
    if end_date:
        base_q = base_q.where(DataSupplyCallLog.called_at <= end_date)

    total_result = await db.execute(select(func.count()).select_from(base_q.subquery()))
    total = total_result.scalar() or 0

    success_result = await db.execute(
        select(func.count()).select_from(
            base_q.where(DataSupplyCallLog.response_status == 200).subquery()
        )
    )
    success = success_result.scalar() or 0

    avg_result = await db.execute(
        select(func.avg(DataSupplyCallLog.duration_ms)).select_from(base_q.subquery())
    )
    avg_duration = avg_result.scalar()

    by_type_result = await db.execute(
        select(DataSupplyCallLog.data_type, func.count())
        .select_from(base_q.subquery())
        .group_by(DataSupplyCallLog.data_type)
    )
    by_data_type = {row[0]: row[1] for row in by_type_result.all()}

    by_date_result = await db.execute(
        select(func.date(DataSupplyCallLog.called_at), func.count())
        .select_from(base_q.subquery())
        .group_by(func.date(DataSupplyCallLog.called_at))
        .order_by(desc(func.date(DataSupplyCallLog.called_at)))
        .limit(30)
    )
    by_date = {str(row[0]): row[1] for row in by_date_result.all()}

    by_key_result = await db.execute(
        select(DataSupplyCallLog.api_key_name, func.count())
        .select_from(base_q.subquery())
        .group_by(DataSupplyCallLog.api_key_name)
    )
    by_api_key = {row[0] or "未知": row[1] for row in by_key_result.all()}

    return {
        "total_calls": total,
        "success_calls": success,
        "failed_calls": total - success,
        "avg_duration_ms": float(avg_duration) if avg_duration else None,
        "by_data_type": by_data_type,
        "by_date": by_date,
        "by_api_key": by_api_key,
    }


# ═══════════════════════════════════════════
# Key 生成
# ═══════════════════════════════════════════

def generate_api_key() -> str:
    return f"spc_{uuid.uuid4().hex[:32]}"


def generate_app_key() -> str:
    return f"ak_{uuid.uuid4().hex[:16]}"


def generate_app_secret() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex
