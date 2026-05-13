"""规则配置中心 — Schema 定义"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel


# ============ 点检规则 ============

class InspectionRuleOut(BaseModel):
    id: int
    module_code: str
    rule_type: str
    item_code: str
    item_name: str
    parent_code: Optional[str] = None
    standard_desc: Optional[str] = None
    sort_order: Optional[int] = 0
    is_active: bool = True
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class InspectionRuleCreate(BaseModel):
    module_code: str
    rule_type: str
    item_code: str
    item_name: str
    parent_code: Optional[str] = None
    standard_desc: Optional[str] = None
    sort_order: Optional[int] = 0
    is_active: bool = True


class InspectionRuleUpdate(BaseModel):
    module_code: Optional[str] = None
    rule_type: Optional[str] = None
    item_name: Optional[str] = None
    parent_code: Optional[str] = None
    standard_desc: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


# ============ 节点标准 ============

class NodeStandardOut(BaseModel):
    id: int
    node_code: str
    node_name: str
    time_value: int
    time_unit: str
    applicable_scene: str
    description: Optional[str] = None
    is_active: bool = True
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class NodeStandardCreate(BaseModel):
    node_code: str
    node_name: str
    time_value: int
    time_unit: str = "天"
    applicable_scene: str
    description: Optional[str] = None
    is_active: bool = True


class NodeStandardUpdate(BaseModel):
    node_name: Optional[str] = None
    time_value: Optional[int] = None
    time_unit: Optional[str] = None
    applicable_scene: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


# ============ 责任归属 ============

class ResponsibilityMapOut(BaseModel):
    id: int
    rule_item_code: str
    department: str
    role_name: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    escalation_level: Optional[int] = 0
    is_active: bool = True
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ResponsibilityMapCreate(BaseModel):
    rule_item_code: str
    department: str
    role_name: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    escalation_level: Optional[int] = 0
    is_active: bool = True


class ResponsibilityMapUpdate(BaseModel):
    rule_item_code: Optional[str] = None
    department: Optional[str] = None
    role_name: Optional[str] = None
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    escalation_level: Optional[int] = None
    is_active: Optional[bool] = None


# ============ 状态字典 ============

class StatusDictionaryOut(BaseModel):
    id: int
    status_type: str
    code: str
    name: str
    color_tag: str
    display_color: Optional[str] = None
    sort_order: Optional[int] = 0
    is_active: bool = True
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class StatusDictionaryCreate(BaseModel):
    status_type: str
    code: str
    name: str
    color_tag: str
    display_color: Optional[str] = None
    sort_order: Optional[int] = 0
    is_active: bool = True


class StatusDictionaryUpdate(BaseModel):
    status_type: Optional[str] = None
    code: Optional[str] = None
    name: Optional[str] = None
    color_tag: Optional[str] = None
    display_color: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
