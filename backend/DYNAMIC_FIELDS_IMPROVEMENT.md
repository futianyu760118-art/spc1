# AI 工具动态字段改进

## 问题
之前的实现中，所有工具都是**手动硬编码字段**，存在以下问题：

1. **维护困难**：每次数据库表添加新字段，需要手动更新所有相关工具
2. **容易遗漏**：可能忘记添加某些字段
3. **代码冗长**：每个工具都有 30+ 行重复的字段映射代码
4. **不一致**：不同工具的字段处理方式可能不一致

## 解决方案

### 1. 创建通用辅助函数 (`utils.py`)

```python
def model_to_dict(instance, exclude_fields=None):
    """自动将 SQLAlchemy 模型转换为字典，包含所有字段"""
    # 使用 SQLAlchemy 反射机制获取所有列
    # 自动处理类型转换（Decimal → float, date → str）
    
def create_search_result_item(instance, item_type, title, subtitle, url, tags=None, exclude_fields=None):
    """创建标准化的搜索结果项"""
    # 包含 type, title, subtitle, url, tags
    # 自动添加模型的所有字段
```

### 2. 重构工具代码

**旧代码（30+ 行）：**
```python
items.append({
    "type": "order",
    "title": f"订单 {o.order_no}",
    "subtitle": f"{o.customer or ''} | {o.product_name or ''}",
    "url": f"/orders/{o.order_no}/lines/{o.line_no}",
    "tags": [o.risk_level, o.status],
    "order_no": o.order_no,
    "line_no": o.line_no,
    "customer": o.customer,
    "customer_code": o.customer_code,
    "product_code": o.product_code,
    "product_name": o.product_name,
    "order_qty": float(o.order_qty) if o.order_qty else None,
    "order_amount": float(o.order_amount) if o.order_amount else None,
    # ... 还有 20+ 个字段
})
```

**新代码（8 行）：**
```python
item = create_search_result_item(
    instance=o,
    item_type="order",
    title=f"订单 {o.order_no}",
    subtitle=f"{o.customer or ''} | {o.product_name or ''}",
    url=f"/orders/{o.order_no}/lines/{o.line_no}",
    tags=[t for t in [o.risk_level, o.status] if t],
)
items.append(item)
```

## 优势

### 1. 自动包含所有字段
- ✅ 数据库表添加新字段时，工具自动包含
- ✅ 不需要手动更新工具代码
- ✅ 零维护成本

### 2. 统一类型转换
- ✅ Decimal → float（数值字段）
- ✅ date/datetime → str（日期字段）
- ✅ JSON 字段保持原样
- ✅ NULL 值统一处理为 None

### 3. 代码简洁
- ✅ 减少 70% 的代码量
- ✅ 更易读、更易维护
- ✅ 减少出错可能

### 4. 一致性
- ✅ 所有工具使用相同的字段处理逻辑
- ✅ 统一的数据格式
- ✅ 更好的可测试性

## 已更新的工具

- ✅ **search_orders** - 销售订单搜索
- ✅ **search_purchase_orders** - 采购订单搜索
- ✅ **search_run_orders** - 跑单管理搜索

## 待更新的工具

剩余工具可以按照相同模式更新：

1. search_materials.py（3个模型）
2. search_production.py（2个模型）
3. search_exceptions.py（4个模型）
4. search_users.py（需要特殊处理关联字段）
5. search_masterdata.py（3个模型）
6. search_eta_updates.py
7. search_invoices.py

## 特殊情况处理

### 1. 排除敏感字段
```python
item = create_search_result_item(
    instance=user,
    item_type="user",
    title=user.username,
    subtitle=user.display_name,
    url="/users",
    tags=[],
    exclude_fields={'password_hash', 'internal_token'}  # 排除敏感字段
)
```

### 2. 添加关联字段
```python
# 预加载关联数据
roles_map = {r.id: r for r in roles}

# 在循环中添加
for u in users:
    item = create_search_result_item(instance=u, ...)
    role = roles_map.get(u.role_id)
    if role:
        item['role_name'] = role.role_name  # 手动添加关联字段
    items.append(item)
```

### 3. 自定义字段处理
```python
item = create_search_result_item(instance=o, ...)
# 可以在创建后修改或添加字段
item['custom_field'] = calculate_custom_value(o)
items.append(item)
```

## 技术实现

### SQLAlchemy 反射机制
```python
from sqlalchemy.inspection import inspect

mapper = inspect(SaleOrder)
for column in mapper.columns:
    col_name = column.name
    value = getattr(instance, col_name, None)
    # 处理类型转换...
```

### 类型转换逻辑
```python
if isinstance(value, Decimal):
    result[col_name] = float(value)
elif isinstance(value, (date, datetime)):
    result[col_name] = str(value)
else:
    result[col_name] = value
```

## 测试验证

### 1. 字段完整性测试
```python
# 确保返回的字段数量与数据库表列数一致
assert len(item.keys()) >= len(mapper.columns)
```

### 2. 类型转换测试
```python
# 验证数值字段是 float 类型
assert isinstance(item['order_qty'], (float, type(None)))

# 验证日期字段是字符串类型
assert isinstance(item['promised_date'], (str, type(None)))
```

### 3. 空值处理测试
```python
# 验证 NULL 值被正确处理为 None
assert item['optional_field'] is None
```

## 性能影响

### 反射开销
- SQLAlchemy 的 `inspect()` 会缓存结果
- 首次调用后，后续调用几乎无开销
- 对查询性能影响可忽略不计

### 内存使用
- 返回完整字段会增加响应大小
- 但对于 AI 工具来说，完整信息更重要
- 可以通过 `exclude_fields` 排除不需要的字段

## 向后兼容

- ✅ 返回的数据结构完全兼容
- ✅ 所有现有字段都会包含
- ✅ 前端代码无需修改
- ✅ AI 提示词无需修改

## 未来扩展

### 1. 字段过滤
可以添加配置来控制哪些字段需要返回：

```python
# 在工具配置中指定需要的字段
FIELDS_CONFIG = {
    'search_orders': {
        'include': ['order_no', 'customer', 'status'],  # 只包含这些
        'exclude': ['internal_notes', 'debug_info'],    # 排除这些
    }
}
```

### 2. 字段别名
可以添加字段重命名功能：

```python
FIELD_ALIASES = {
    'order_no': 'orderNumber',
    'customer': 'customerName',
}
```

### 3. 嵌套对象
可以支持自动展开关联对象：

```python
# 自动包含 order.customer.* 字段
item = create_search_result_item(
    instance=order,
    expand_relations=['customer', 'lines']
)
```

## 总结

通过引入动态字段机制：

1. **减少维护成本**：数据库变更时无需更新工具代码
2. **提高代码质量**：更简洁、更一致、更易维护
3. **增强可扩展性**：易于添加新功能和优化
4. **保证完整性**：自动包含所有字段，不会遗漏

这是一个**重要的架构改进**，为 AI 工具的长期维护奠定了良好基础。
