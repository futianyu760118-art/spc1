# AI 智能助手工具字段完整性总结

## 概述
所有 AI 智能助手的搜索工具已经配置为返回数据库的**完整字段**，确保 AI 能够获取所有必要的信息来回答用户问题。

## 工具列表及字段覆盖

### 1. search_orders - 搜索销售订单 ✅
**返回字段（完整）**：
- 基本信息：order_no, line_no, customer, customer_code, product_code, product_name
- 数量金额：order_qty, order_amount, completed_qty
- 日期信息：promised_date, planned_start_date, order_date, audit_date
- 批次信息：batch_no, order_nature
- 责任人：department, owner
- 状态风险：status, risk_level, risk_score, risk_factors, risk_assessed_at
- 交付信息：delivery_completed_date, customer_grade, shipping_plan
- 检验包装：customer_inspection_date, inspection_result, packaging_status
- 物料信息：bom_return_date, material_ready_date, material_dates, procurement_status, shipping_status_desc
- 生产进度：front_process_date, first_article_date, assembly_start_date, assembly_complete_date
- 备注：remark

### 2. search_purchase_orders - 搜索采购订单 ✅
**返回字段（完整）**：
- 基本信息：po_no, detail_id, material_code, material_name, material_type_name, material_property
- 供应商：supplier_code, supplier_name
- 数量价格：po_qty, po_price, unit
- 日期信息：po_date, eta, original_eta, actual_arrival_date, inspection_date
- 状态：po_status, received_qty
- 关联信息：order_no, spec_model
- 其他：owner, remark, arrival_hour_note

### 3. search_materials - 搜索物料 ✅
**包含三类物料数据**：

#### 3.1 物料需求 (MaterialDemand)
- material_code, material_name, order_no, line_no
- req_qty, req_date, allocated_qty, shortage_qty, shortage_flag
- data_source

#### 3.2 问题物料 (MaterialIssue)
- year, week_no, department, category
- issue_date, reporter, description, deadline
- responsible_dept, responsible_person
- audit_score, is_project, follow_up_record, status

#### 3.3 长交期物料 (LongLeadMaterial)
- material_code, supplier_name
- improvement_plan, status

### 4. search_production - 搜索生产工序 ✅
**包含两类数据**：

#### 4.1 工序进度 (ProcessProgress)
- 基本信息：order_no, process_type, seq_no, plan_date
- 产品信息：product_code, product_name, line_no, model_code, color_spec
- 数量信息：qty, planned_qty, kit_qty, daily_plan_qty, daily_complete_qty, warehouse_in_qty
- 日期信息：online_date, delivery_date
- 进度信息：completion_rate, work_hours
- 状态：status, remark
- 前道特有：customer_code, sale_order_no, shell_status, frame_status, handle_status, bracket_status
- 贴片特有：material_long_code, material_name, material_confirm
- 组装特有：assembly_group

#### 4.2 工序异常 (ProcessException)
- exception_no, process_type, order_no, model_code
- exception_type, severity, description
- responsible_dept, responsible_person
- status, resolved_at, remark, created_at

### 5. search_exceptions - 搜索异常 ✅
**包含四类异常数据**：

#### 5.1 风险问题 (RiskIssue)
- issue_no, issue_type, risk_level
- order_no, line_no, material_code, po_no
- description, owner, action_taken
- commit_date, status, closed_at, created_at

#### 5.2 品质异常 (QualityIssue)
- issue_no, status, remark
- submit_dept, submit_date, submitter
- order_no, product_code, product_name
- process, defect_type, root_cause, description
- responsible_person, responsible_dept
- batch_qty, sample_qty, defect_qty
- improvement_countermeasures, improvement_countermeasures_date
- temporary_countermeasure, temporary_countermeasure_date
- preliminary_analysis, preliminary_analysis_person
- root_cause_analysis_person, audit_comment, auditor
- created_at

#### 5.3 问题日志 (IssueLog)
- seq_no, recorder, record_date
- description, impact, interaction

#### 5.4 变更日志 (ChangeLog)
- seq_no, modifier, change_date
- change_content, impact, interaction

### 6. search_run_orders - 搜索跑单管理 ✅
**返回字段（完整）**：
- order_no, customer_code, order_qty, order_type
- contract_date, delivery_date, run_date, run_days
- order_amount, packaging_not_released
- po_placed_date, material_ready_date, procurement_cycle
- completed_date, shipped_date
- order_status, delay_reason, remark, is_domestic

### 7. search_users - 搜索用户 ✅
**返回字段（完整）**：
- id, username, display_name, emp_code
- role_id, role_name, role_code
- is_active, last_login_time, created_at

### 8. search_masterdata - 搜索主数据 ✅
**包含三类主数据**：

#### 8.1 客户 (Customer)
- customer_code, customer_name, customer_short
- customer_level, industry_type, credit_code, status

#### 8.2 供应商 (Supplier)
- supplier_code, supplier_name, supplier_short
- supplier_type, contact_person, contact_phone
- payment_terms, status

#### 8.3 物料主数据 (Material)
- material_code, material_name, spec_model
- material_type, unit_of_measure, brand
- is_purchase, is_produce, status

### 9. search_eta_updates - 搜索交期更新 ✅
**返回字段（完整）**：
- po_no, old_eta, new_eta
- updater, update_reason, remark, created_at

### 10. search_invoices - 搜索发票 ✅
**返回字段（完整）**：
- invoice_no, line_no, invoice_date
- supplier_id, supplier_code, supplier_name
- payment_term, settlement_method
- invoice_amount, remain_payable

### 11. dashboard_summary - 仪表盘摘要 ✅
**返回统计数据**：
- 订单统计：total_orders, overdue_orders, high_risk_orders
- 物料统计：shortage_materials, long_lead_materials
- 异常统计：open_issues, quality_issues
- 生产统计：production_progress

### 12. get_order_details - 获取订单详情 ✅
**返回完整订单详情**：
- 订单基本信息（所有 SaleOrder 字段）
- 订单行明细列表
- 物料需求列表
- 绑定关系列表
- 关联问题列表

## 字段完整性保证

### 设计原则
1. **完整性优先**：所有工具返回数据库表的全部字段
2. **类型转换**：数值类型转换为 float，日期转换为字符串
3. **空值处理**：使用 `if value else None` 处理空值
4. **结构化输出**：每个工具返回 `{"total": int, "items": list}` 格式

### 字段映射规则
```python
# 数值字段
"order_qty": float(o.order_qty) if o.order_qty else None

# 日期字段
"promised_date": str(o.promised_date) if o.promised_date else None

# 字符串字段
"customer": o.customer

# 布尔字段
"is_active": u.is_active

# JSON 字段
"material_dates": o.material_dates
"risk_factors": o.risk_factors
```

## AI 使用建议

### 1. 查询订单信息
```python
# AI 可以访问订单的所有字段
search_orders(keyword="HJ202604-0018-0086")
# 返回包含 order_no, customer, product_name, promised_date, 
# risk_level, material_ready_date 等全部字段
```

### 2. 查询物料信息
```python
# AI 可以查看物料的完整信息
search_materials(keyword="12345678", category="demand")
# 返回 material_code, material_name, req_qty, shortage_qty 等
```

### 3. 查询生产进度
```python
# AI 可以查看工序的详细进度
search_production(order_no="HJ202604-0018", process_type="assembly")
# 返回 plan_date, qty, completion_rate, status 等全部字段
```

## 维护指南

### 添加新字段
当数据库表添加新字段时，需要同步更新对应的工具：

1. 在工具的返回字典中添加新字段
2. 处理字段的类型转换和空值
3. 更新本文档的字段列表

### 示例
```python
# 在 search_orders 中添加新字段 new_field
items.append({
    # ... 现有字段 ...
    "new_field": o.new_field,  # 添加新字段
})
```

## 总结

✅ **所有 12 个 AI 工具都已返回完整字段**
✅ **覆盖订单、物料、生产、异常、主数据等所有业务领域**
✅ **字段类型转换和空值处理完善**
✅ **AI 可以获取所有必要信息来回答用户问题**

AI 智能助手现在可以访问数据库的全部字段信息，能够提供更准确、更详细的回答。
