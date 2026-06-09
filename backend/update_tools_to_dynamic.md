# 工具动态字段更新指南

## 已完成
- ✅ search_orders - 订单搜索
- ✅ search_purchase_orders - 采购订单搜索

## 待更新工具列表

### 1. search_materials.py
需要更新三个模型：
- MaterialDemand
- MaterialIssue  
- LongLeadMaterial

### 2. search_production.py
需要更新两个模型：
- ProcessProgress
- ProcessException

### 3. search_exceptions.py
需要更新四个模型：
- RiskIssue
- QualityIssue
- IssueLog
- ChangeLog

### 4. search_run_orders.py
需要更新：
- RunOrder

### 5. search_users.py
需要更新：
- SysUser（需要特殊处理 role 关联）

### 6. search_masterdata.py
需要更新三个模型：
- Customer
- Supplier
- Material

### 7. search_eta_updates.py
需要更新：
- ETAUpdate

### 8. search_invoices.py
需要更新：
- PurchaseInvoice

## 更新步骤

### 1. 导入辅助函数
```python
from app.services.assistant.tools.utils import create_search_result_item
```

### 2. 替换手动字段映射
**旧代码：**
```python
items.append({
    "type": "order",
    "title": f"订单 {o.order_no}",
    "subtitle": f"{o.customer or ''} | {o.product_name or ''}",
    "url": f"/orders",
    "tags": [o.status],
    "order_no": o.order_no,
    "customer": o.customer,
    # ... 更多字段
})
```

**新代码：**
```python
item = create_search_result_item(
    instance=o,
    item_type="order",
    title=f"订单 {o.order_no}",
    subtitle=f"{o.customer or ''} | {o.product_name or ''}",
    url=f"/orders",
    tags=[o.status] if o.status else [],
)
items.append(item)
```

## 优势

### 1. 自动获取所有字段
- 不需要手动列出每个字段
- 数据库表添加新字段时自动包含
- 减少维护工作量

### 2. 统一类型转换
- Decimal → float
- date/datetime → str
- 其他类型保持原样

### 3. 代码简洁
- 从 30+ 行减少到 8 行
- 更易读、更易维护

## 注意事项

### 1. 特殊字段处理
如果需要排除某些字段（如密码、内部ID等），使用 `exclude_fields` 参数：

```python
item = create_search_result_item(
    instance=user,
    item_type="user",
    title=user.username,
    subtitle=user.display_name,
    url="/users",
    tags=[],
    exclude_fields={'password_hash', 'internal_id'}  # 排除敏感字段
)
```

### 2. 关联字段
对于需要关联查询的字段（如 user.role_name），需要在循环前预加载：

```python
# 预加载角色信息
role_ids = {u.role_id for u in users if u.role_id}
roles_map = {}
if role_ids:
    roles = await db.execute(select(SysRole).where(SysRole.id.in_(role_ids)))
    roles_map = {r.id: r for r in roles.scalars().all()}

# 在循环中添加关联字段
for u in users:
    item = create_search_result_item(instance=u, ...)
    role = roles_map.get(u.role_id)
    if role:
        item['role_name'] = role.role_name
        item['role_code'] = role.role_code
    items.append(item)
```

### 3. JSON 字段
JSON 字段（如 material_dates, risk_factors）会自动包含，无需特殊处理。

## 测试

更新每个工具后，测试：

1. **基本查询**：确保返回正确的数据
2. **字段完整性**：检查是否包含所有数据库字段
3. **类型转换**：验证数值和日期字段的格式
4. **空值处理**：测试字段为 NULL 的情况

## 示例：完整更新一个工具

```python
# search_run_orders.py

from app.services.assistant.tools.utils import create_search_result_item

# ... 查询逻辑 ...

items = []
for r in rows:
    item = create_search_result_item(
        instance=r,
        item_type="run_order",
        title=f"跑单 {r.order_no}",
        subtitle=f"{r.customer_code or ''} | {r.order_type or ''} | 跑单日期 {r.run_date or ''}",
        url=f"/run-orders",
        tags=[t for t in [r.order_type, r.order_status] if t],
    )
    items.append(item)

return {"total": total, "items": items}
```

## 回滚方案

如果动态方式出现问题，可以回退到手动字段映射。保留原始代码的备份。
