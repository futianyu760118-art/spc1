# Design: 委外订单页面对齐项目风格

**Date:** 2026-07-21
**Status:** Approved, pending implementation
**Scope:** 把 `frontend/src/pages/MaterialCenter/SubcontractOrders/index.tsx` 的视觉与交互层重写，对齐 LongLeadMaterials / MaterialIssues 的 card-modern 模式。后端做最小改动支持 stats 和 sort。

---

## 1. 背景

当前页面（commit `e5387c9` + `287a23c`）功能完整但样式与其他 MaterialCenter 页面不一致：
- 用 `<Card><Statistic>` 而非 card-modern + 自定义 flex 统计卡
- 用 `<Space>` 而非 card-modern + Row 包裹的筛选条
- 表格无 card-modern 包裹，无 `size="small"`
- 列不可排序
- 同时存在「明细 Modal」和「行展开」两套重复 UI
- 图标按钮无 Tooltip
- 表单 `onOk` 直接调函数而非 `form.submit() + onFinish`

---

## 2. 改动范围

### 2.1 后端（极小）

**文件：** `backend/app/api/v1/material/subcontract_orders.py`

list endpoint 加：
1. `sort_by: Optional[str] = Query(None)` —— 允许的列：`bill_date / detail_count / total_qty / created_at`
2. `sort_order: Optional[str] = Query(None)` —— `asc` / `desc`
3. 返回 `PageResult(..., stats={...})`，stats 包含：
   ```python
   {
     "total": int,        # 不含 voided，与列表一致
     "audited": int,      # status == '1'（已审核）
     "pending": int,      # status in ('0', None)（未审核）
     "closed": int,       # closed_flag == 1
     "voided": int,       # voided_flag == 1（全部，不受 include_voided 影响）
   }
   ```

stats 用 4 个独立 COUNT(*) 查询，base 条件与列表一致（除 voided 计数始终包含 voided）。可接受 4 次额外往返，列表本身已涉及 JOIN，性能可忽略。

**排序实现：** 在 `order_by(...)` 前根据 sort_by 选择列；明细数/总数量需用 outerjoin 子查询的列排序（已有 detail_subq）。无 sort_by 时维持默认 `bill_date DESC NULLS LAST, id DESC`。

### 2.2 前端（重写展示层）

**文件：** `frontend/src/pages/MaterialCenter/SubcontractOrders/index.tsx`

完整对齐 LongLeadMaterials 模式：

```tsx
return (
  <div>
    {/* 1. 统计卡区 */}
    <Row gutter={16} style={{ marginBottom: 16 }}>
      {[
        { title: '委外订单总数', value: stats.total, icon: <FileTextOutlined />, color: '#6366f1' },
        { title: '已审核', value: stats.audited, icon: <CheckCircleOutlined />, color: '#059669' },
        { title: '待审核', value: stats.pending, icon: <ClockCircleOutlined />, color: '#d97706' },
        { title: '已作废', value: stats.voided, icon: <StopOutlined />, color: '#e11d48' },
      ].map((card, i) => (
        <Col span={6} key={i}>
          <Card size="small" className="card-modern" style={{ padding: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 44, height: 44, borderRadius: 10, background: `${card.color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 'calc(1.25rem * var(--font-size-scale))', color: card.color }}>
                {card.icon}
              </div>
              <div>
                <div style={{ fontSize: 'calc(1.375rem * var(--font-size-scale))', fontWeight: 700, color: '#1e293b' }}>{card.value}</div>
                <div style={{ fontSize: 'calc(0.75rem * var(--font-size-scale))', color: '#64748b' }}>{card.title}</div>
              </div>
            </div>
          </Card>
        </Col>
      ))}
    </Row>

    {/* 2. 筛选条 */}
    <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
      <Row gutter={12} align="middle">
        <Col>
          <Input prefix={<SearchOutlined />} placeholder="搜索单据编号" value={keyword}
            onChange={e => { setKeyword(e.target.value); setPage(1) }}
            style={{ width: 240 }} allowClear />
        </Col>
        <Col>
          <Select value={includeVoided ? 'yes' : 'no'} onChange={v => { setIncludeVoided(v === 'yes'); setPage(1) }} style={{ width: 130 }}>
            <Select.Option value="no">隐藏作废</Select.Option>
            <Select.Option value="yes">包含作废</Select.Option>
          </Select>
        </Col>
        <Col flex="auto" />
        <Col>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
            <Button icon={<DownloadOutlined />} onClick={onExport}>导出</Button>
            <Upload beforeUpload={onImport} showUploadList={false} accept=".csv">
              <Button icon={<UploadOutlined />}>导入 CSV</Button>
            </Upload>
            <Button disabled={selectedIds.length === 0} onClick={() => setBatchOpen(true)}>
              批量更新 {selectedIds.length > 0 ? `(${selectedIds.length})` : ''}
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增</Button>
          </Space>
        </Col>
      </Row>
    </div>

    {/* 3. 表格 */}
    <div className="card-modern" style={{ padding: '0 0 4px' }}>
      <Table<HeadRow>
        rowKey="id"
        dataSource={data}
        columns={columns}
        loading={loading}
        scroll={{ x: 1400 }}
        size="small"
        rowSelection={{ selectedRowKeys: selectedIds, onChange: keys => setSelectedIds(keys as number[]) }}
        pagination={{ total, current: page, pageSize, showSizeChanger: true, showTotal: t => `共 ${t} 条` }}
        onChange={(pagination, _filters, sorter: any) => {
          setPage(pagination.current || 1)
          setPageSize(pagination.pageSize || 20)
          const f = sorter.field as string | undefined
          setSortBy(f || '')
          setSortOrder(sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : '')
        }}
        expandable={{
          rowExpandable: r => (r.detail_count ?? 0) > 0,
          expandedRowRender: r => <SubcontractDetailInline headId={r.id} />,
        }}
      />
    </div>

    {/* Modals：batch / head edit. 删除 detail Modal */}
  </div>
)
```

#### 列定义（带 sorter）

```ts
const columns = [
  { title: '单据编号', dataIndex: 'bill_no', width: 180, fixed: 'left' as const },
  { title: '日期', dataIndex: 'bill_date', width: 110, sorter: true,
    render: (v: string) => formatDate(v) },
  { title: '类型', dataIndex: 'bill_type', width: 120 },
  { title: '供应商ID', dataIndex: 'supplier_id', width: 90 },
  { title: '状态', dataIndex: 'status', width: 100,
    render: (v: string) => v ? <Tag color={STATUS_COLOR[v] || 'default'}>{STATUS_LABEL[v] || v}</Tag> : null },
  { title: '明细数', dataIndex: 'detail_count', width: 90, align: 'right' as const, sorter: true },
  { title: '总数量', dataIndex: 'total_qty', width: 110, align: 'right' as const, sorter: true,
    render: (v: any) => v != null ? Number(v).toFixed(2) : '-' },
  { title: '来源', dataIndex: 'data_source', width: 90,
    render: (v: string) => v === 'erp' ? <Tag color="blue">ERP</Tag> : (v ? <Tag>{v}</Tag> : null) },
  { title: '摘要', dataIndex: 'remark', ellipsis: true },
  { title: '操作', key: 'op', width: 200, fixed: 'right' as const,
    render: (_: any, r: HeadRow) => (
      <Space>
        <Tooltip title={r.data_source === 'erp' ? 'ERP 数据请在 ERP 系统修改' : '编辑'}>
          <Button size="small" icon={<EditOutlined />} disabled={r.data_source === 'erp'} onClick={() => openEdit(r)} />
        </Tooltip>
        <Tooltip title={r.data_source === 'erp' ? 'ERP 数据不可删除' : '删除'}>
          <Popconfirm title="确认删除？" onConfirm={() => remove(r.id)} disabled={r.data_source === 'erp'}>
            <Button size="small" danger icon={<DeleteOutlined />} disabled={r.data_source === 'erp'} />
          </Popconfirm>
        </Tooltip>
      </Space>
    ) },
]
```

#### STATUS 标签中文化

```ts
const STATUS_COLOR: Record<string, string> = {
  '0': 'default', '1': 'success', '2': 'warning', '3': 'error',
}
const STATUS_LABEL: Record<string, string> = {
  '0': '未审核', '1': '已审核', '2': '审核中', '3': '已关闭',
}
```

> 上述 status 值来自实际 ERP 数据观察（ww2717 status=1=已审核，ww2711 status=3=已关闭）。如果实际业务有更多状态码，未识别的会显示原值。

#### 删除的内容
- `detailOpen` / `details` / `detailsLoading` / `detailForm` state
- `openDetails` / `addDetail` / `removeDetail` 函数
- 整个「明细 - XXX」Modal JSX
- `detailColumns` 数组（合并到 `SubcontractDetailInline` 子组件内）
- 不再用到的 import：`Tag` 仍用，移除 `ExpandOutlined`

#### `SubcontractDetailInline` 子组件增强
加入「添加明细」按钮（仅当 head.data_source != 'erp'），改为受控表单：

```tsx
function SubcontractDetailInline({ head }: { head: HeadRow }) {
  // ... fetch + state
  // 加一个 + 按钮，弹出小 modal 或 inline form 添加明细
  // 删除按钮带 Popconfirm
}
```

接收整个 head 对象（不只是 headId），用来判断 data_source 和 refetch 触发。

---

## 3. 不在范围

- supplier_id → supplier_name 解析（仍显示 ID）
- 状态/日期多筛选（只保留 includeVoided 切换）
- 后端 CSV 导入/导出逻辑改动
- ERP 同步逻辑改动

---

## 4. 验证

| 项 | 方法 |
|---|---|
| 后端 list 返回 stats | curl `/materials/subcontract-orders?page=1` 看 `data.stats` 字段 |
| 后端 sort 生效 | `?sort_by=detail_count&sort_order=desc` 返回按明细数降序 |
| 前端 build 0 错 | `npm run build` |
| 视觉对齐 | 启动 dev，与 LongLeadMaterials 截图对比：3 区块布局一致 |
| 行展开可加明细 | 展开 ERP 行无「+」按钮；展开手动行可加 |
| 排序点击 | 点 bill_date 列头能升降序切换 |
| 批量更新保留 | 仍能勾选 → 点批量更新 → 提交 |
| ERP guard 保留 | 编辑/删除 ERP 行按钮仍 disabled |

---

## 5. 关键文件清单

**修改：**
- `backend/app/api/v1/material/subcontract_orders.py` — list endpoint 加 stats + sort
- `frontend/src/pages/MaterialCenter/SubcontractOrders/index.tsx` — 展示层重写

**不动：**
- 后端 schemas、其他 endpoint
- 前端 services/api.ts、MainLayout、permission 等
