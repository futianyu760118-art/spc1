# 修复 get_order_details 工具

## 问题

用户反馈 AI 助手查询订单详情时只显示很少的字段，并且物料齐套查询报错。

### 问题 1：字段显示不全
**现象**：
```
订单 HJ202604-0022-0090 的详细信息如下：
客户：HJ006.46 - 354PR
订单数量：2500.0
订单金额：106519.38
承诺交期：2026-07-01
订单状态：open
风险等级：blue
订单性质：返单
```

只显示了 7 个字段，但数据库表有 30+ 个字段。

**原因**：
- `get_order_details` 工具使用硬编码字段
- AI 在生成回复时只选择了部分字段展示

### 问题 2：物料齐套查询报错
**错误信息**：
```
物料齐套情况查询异常，具体错误为：
物料齐套查询失败: The "whens" argument to case(), when referring to a 
sequence of items, is now passed as a series of positional elements, 
rather than as a list.
```

**原因**：
- SQLAlchemy 2.0 改变了 `case()` 函数的语法
- 旧语法：`case([(condition, value)], else_=default)`
- 新语法：`case((condition, value), else_=default)`

## 解决方案

### 1. 改为动态获取所有字段

**修改前（硬编码 30+ 个字段）：**
```python
order_data = {
    "order_no": order.order_no,
    "line_no": order.line_no,
    "customer": order.customer,
    "customer_code": order.customer_code,
    # ... 还有 26 个字段
    "created_at": str(order.created_at) if order.created_at else None,
    "updated_at": str(order.updated_at) if order.updated_at else None,
    "material_completeness": material_completeness,
}
```

**修改后（动态获取）：**
```python
# 使用动态方式获取所有字段
order_data = model_to_dict(order)

# 添加物料齐套信息
order_data["material_completeness"] = material_completeness
```

### 2. 修复 case() 语法

**修改前（SQLAlchemy 1.x 语法）：**
```python
func.sum(case([(MaterialDemand.shortage_flag == True, 1)], else_=0))
```

**修改后（SQLAlchemy 2.0 语法）：**
```python
func.sum(case((MaterialDemand.shortage_flag == True, 1), else_=0))
```

**关键变化**：
- 去掉外层的方括号 `[]`
- 直接传递元组 `(condition, value)` 作为位置参数

## 效果

### 1. 字段完整性
现在 `get_order_details` 会返回订单表的**所有字段**：
- 基本信息：order_no, line_no, customer, customer_code, product_code, product_name
- 数量金额：order_qty, order_amount, completed_qty
- 日期信息：promised_date, planned_start_date, order_date, audit_date, delivery_completed_date
- 批次信息：batch_no, order_nature
- 责任人：department, owner
- 状态风险：status, risk_level, risk_score, risk_factors, risk_assessed_at
- 交付信息：customer_grade, shipping_plan
- 检验包装：customer_inspection_date, inspection_result, packaging_status
- 物料信息：bom_return_date, material_ready_date, material_dates, procurement_status, shipping_status_desc
- 生产进度：front_process_date, first_article_date, assembly_start_date, assembly_complete_date
- 备注：remark
- 时间戳：created_at, updated_at
- **物料齐套信息**：material_completeness（包含齐套率、欠料数量等）

### 2. 物料齐套查询正常
修复 `case()` 语法后，物料齐套查询可以正常执行，返回：
- total_materials: 物料总数
- total_req_qty: 需求总量
- total_allocated_qty: 已分配总量
- total_shortage_qty: 欠料总量
- shortage_count: 欠料物料数
- issue_count: 问题物料数
- completeness_rate: 齐套率（百分比）
- is_complete: 是否齐套
- status: 齐套状态（"齐套" 或 "欠料"）

## SQLAlchemy 2.0 语法变更

### case() 函数
**旧语法（1.x）：**
```python
case(
    [
        (condition1, value1),
        (condition2, value2),
    ],
    else_=default_value
)
```

**新语法（2.0）：**
```python
case(
    (condition1, value1),
    (condition2, value2),
    else_=default_value
)
```

### 其他常见变更
1. **select() 语法**：
   - 旧：`select([table.c.column])`
   - 新：`select(table.c.column)`

2. **join() 语法**：
   - 旧：`query.join(table, condition)`
   - 新：`select().join(table).where(condition)`

3. **execute() 返回值**：
   - 旧：`result.fetchall()`
   - 新：`result.all()` 或 `result.scalars().all()`

## 测试验证

### 1. 测试字段完整性
```python
# 查询订单详情
result = await get_order_details(db, {"order_no": "HJ202604-0022-0090"})

# 验证字段数量
order_data = result["order"]
assert len(order_data) > 30  # 应该包含 30+ 个字段

# 验证关键字段存在
assert "order_no" in order_data
assert "customer" in order_data
assert "material_completeness" in order_data
```

### 2. 测试物料齐套查询
```python
# 查询订单详情
result = await get_order_details(db, {"order_no": "HJ202604-0022-0090"})

# 验证物料齐套信息
mc = result["order"]["material_completeness"]
assert "total_materials" in mc
assert "completeness_rate" in mc
assert "status" in mc
assert "error" not in mc  # 不应该有错误
```

### 3. 测试字段过滤
```python
# 只查询特定字段
result = await get_order_details(db, {
    "order_no": "HJ202604-0022-0090",
    "fields": ["status", "promised_date", "risk_level"]
})

# 验证只返回指定字段（加上 material_completeness）
order_data = result["order"]
assert "status" in order_data
assert "promised_date" in order_data
assert "risk_level" in order_data
assert "material_completeness" in order_data  # 总是包含
```

## 相关文件

- `backend/app/services/assistant/tools/get_order_details.py` - 订单详情工具
- `backend/app/services/assistant/tools/utils.py` - 通用辅助函数
- `backend/app/models/order/sale_order.py` - 订单模型
- `backend/app/models/material/material_demand.py` - 物料需求模型

## 注意事项

1. **向后兼容**：修改后的代码完全向后兼容，不影响现有功能
2. **性能影响**：动态获取字段的性能开销可忽略不计
3. **错误处理**：物料齐套查询失败时会返回默认值，不影响订单信息查询
4. **字段过滤**：支持通过 `fields` 参数只返回特定字段，但 `material_completeness` 总是包含

## 后续优化

1. **缓存反射结果**：可以缓存 SQLAlchemy 的反射结果，进一步提升性能
2. **字段分组**：可以将字段分组（基本信息、日期信息、生产信息等），方便 AI 理解
3. **字段说明**：可以为每个字段添加中文说明，帮助 AI 更好地解释数据
4. **关联查询优化**：可以优化物料齐套查询，减少数据库查询次数
