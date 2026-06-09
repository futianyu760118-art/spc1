import { useEffect, useState, useCallback } from 'react'
import { Row, Col, Table, Tag, Input, Select, Button, message, Space, Tooltip, Modal, Form, DatePicker, InputNumber, Card, Spin } from 'antd'
import {
  SearchOutlined, ReloadOutlined, PlusOutlined,
  OrderedListOutlined, CheckCircleOutlined, SendOutlined,
  FieldTimeOutlined, EditOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { runOrderApi } from '../../../services/api'

interface RunOrderRow {
  id: number | null
  customer_code: string | null
  order_no: string
  order_qty: number | null
  order_type: string | null
  contract_date: string | null
  delivery_date: string | null
  run_date: string | null
  run_days: number | null
  order_amount: number | null
  packaging_not_released: string | null
  po_placed_date: string | null
  material_ready_date: string | null
  procurement_cycle: number | null
  completed_date: string | null
  shipped_date: string | null
  order_status: string | null
  delay_reason: string | null
  remark: string | null
  is_domestic: boolean
  is_synced: boolean
}

interface Filters {
  keyword: string
  order_type: string[]
  order_status: string[]
  is_domestic: string[]
}

const ORDER_TYPES = [
  { value: '返单', label: '返单' },
  { value: '新订单', label: '新订单' },
  { value: '补单', label: '补单' },
  { value: '配件', label: '配件' },
]


export default function RunOrderList() {
  const [orders, setOrders] = useState<RunOrderRow[]>([])
  const [loading, setLoading] = useState(false)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 50, total: 0 })
  const [filters, setFilters] = useState<Filters>({ keyword: '', order_type: [], order_status: [], is_domestic: [] })
  const [sortInfo, setSortInfo] = useState<{ sort_by?: string; sort_order?: string }>({})
  const [summary, setSummary] = useState({ total: 0, completed: 0, shipped: 0, avgDays: 0 })
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [createForm] = Form.useForm()
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editForm] = Form.useForm()
  const [editingRecord, setEditingRecord] = useState<RunOrderRow | null>(null)
  const [syncingOrderNo, setSyncingOrderNo] = useState<string | null>(null)
  const [savingCell, setSavingCell] = useState<string | null>(null)
  const [editingCell, setEditingCell] = useState<string | null>(null)

  const fetchOrders = useCallback(async (page = 1, pageSize = 50) => {
    setLoading(true)
    try {
      const params: Record<string, any> = { page, page_size: pageSize }
      if (sortInfo.sort_by) params.sort_by = sortInfo.sort_by
      if (sortInfo.sort_order) params.sort_order = sortInfo.sort_order
      if (filters.keyword) params.keyword = filters.keyword
      if (filters.order_type.length > 0) params.order_type = filters.order_type.join(',')
      if (filters.order_status.length > 0) params.order_status = filters.order_status.join(',')
      if (filters.is_domestic.length > 0) params.is_domestic = filters.is_domestic[0] === 'true'
      const res: any = await runOrderApi.list(params)
      const items: RunOrderRow[] = res.data.items || []
      setOrders(items)
      setPagination({ current: res.data.page, pageSize: res.data.page_size, total: res.data.total })
      // 使用后端返回的全局统计
      const stats = res.data.stats || {}
      setSummary({
        total: stats.total || res.data.total,
        completed: stats.completed_count || 0,
        shipped: stats.shipped_count || 0,
        avgDays: stats.avg_days ? Math.round(stats.avg_days) : 0,
      })
    } catch {
      message.error('获取跑单列表失败')
    } finally {
      setLoading(false)
    }
  }, [filters, sortInfo])

  useEffect(() => { fetchOrders() }, [fetchOrders])

  const handleTableChange = (pagination: any, tableFilters: any, sorter: any) => {
    let sortField = sorter.field
    const sortOrder = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : undefined
    const orderTypeFilter = tableFilters.order_type?.length > 0 ? tableFilters.order_type : []
    const orderStatusFilter = tableFilters.order_status?.length > 0 ? tableFilters.order_status : []
    const isDomesticFilter = tableFilters.is_domestic?.length > 0 ? tableFilters.is_domestic : []
    setSortInfo({ sort_by: sortField, sort_order: sortOrder })
    setFilters(f => ({ ...f, order_type: orderTypeFilter, order_status: orderStatusFilter, is_domestic: isDomesticFilter }))
  }

  const handleCreate = async () => {
    try {
      const values = await createForm.validateFields()
      const dateFields = ['contract_date', 'delivery_date', 'run_date', 'po_placed_date', 'material_ready_date', 'completed_date', 'shipped_date']
      const payload: Record<string, any> = {}
      for (const [k, v] of Object.entries(values)) {
        if (dateFields.includes(k) && v) {
          payload[k] = dayjs(v as any).format('YYYY-MM-DD')
        } else {
          payload[k] = v ?? null
        }
      }
      await runOrderApi.create(payload)
      message.success('跑单创建成功')
      setCreateModalOpen(false)
      createForm.resetFields()
      fetchOrders(1)
    } catch {
      // validateFields 失败时自动提示
    }
  }

  const handleEdit = async (record: RunOrderRow) => {
    if (!record.is_synced) {
      // 未同步，先调用同步API
      setSyncingOrderNo(record.order_no)
      try {
        await runOrderApi.syncFromOrder(record.order_no)
        message.success('订单已同步到跑单表')
        // 重新获取数据
        await fetchOrders(pagination.current, pagination.pageSize)
        // 查找同步后的记录
        const updatedOrders = await runOrderApi.list({ page: pagination.current, page_size: pagination.pageSize })
        const syncedRecord = updatedOrders.data.items.find((item: RunOrderRow) => item.order_no === record.order_no)
        if (syncedRecord) {
          setEditingRecord(syncedRecord)
          editForm.setFieldsValue({
            order_no: syncedRecord.order_no,
            customer_code: syncedRecord.customer_code,
            order_qty: syncedRecord.order_qty,
            order_type: syncedRecord.order_type,
            contract_date: syncedRecord.contract_date ? dayjs(syncedRecord.contract_date) : null,
            delivery_date: syncedRecord.delivery_date ? dayjs(syncedRecord.delivery_date) : null,
            run_date: syncedRecord.run_date ? dayjs(syncedRecord.run_date) : null,
            run_days: syncedRecord.run_days,
            order_amount: syncedRecord.order_amount,
            packaging_not_released: syncedRecord.packaging_not_released,
            po_placed_date: syncedRecord.po_placed_date ? dayjs(syncedRecord.po_placed_date) : null,
            material_ready_date: syncedRecord.material_ready_date ? dayjs(syncedRecord.material_ready_date) : null,
            procurement_cycle: syncedRecord.procurement_cycle,
            completed_date: syncedRecord.completed_date ? dayjs(syncedRecord.completed_date) : null,
            shipped_date: syncedRecord.shipped_date ? dayjs(syncedRecord.shipped_date) : null,
            order_status: syncedRecord.order_status,
            delay_reason: syncedRecord.delay_reason,
            remark: syncedRecord.remark,
            is_domestic: syncedRecord.is_domestic,
          })
          setEditModalOpen(true)
        }
      } catch {
        message.error('同步失败')
      } finally {
        setSyncingOrderNo(null)
      }
    } else {
      // 已同步，直接编辑
      if (!record.id) {
        message.error('跑单记录ID不存在')
        return
      }
      setEditingRecord(record)
      editForm.setFieldsValue({
        order_no: record.order_no,
        customer_code: record.customer_code,
        order_qty: record.order_qty,
        order_type: record.order_type,
        contract_date: record.contract_date ? dayjs(record.contract_date) : null,
        delivery_date: record.delivery_date ? dayjs(record.delivery_date) : null,
        run_date: record.run_date ? dayjs(record.run_date) : null,
        run_days: record.run_days,
        order_amount: record.order_amount,
        packaging_not_released: record.packaging_not_released,
        po_placed_date: record.po_placed_date ? dayjs(record.po_placed_date) : null,
        material_ready_date: record.material_ready_date ? dayjs(record.material_ready_date) : null,
        procurement_cycle: record.procurement_cycle,
        completed_date: record.completed_date ? dayjs(record.completed_date) : null,
        shipped_date: record.shipped_date ? dayjs(record.shipped_date) : null,
        order_status: record.order_status,
        delay_reason: record.delay_reason,
        remark: record.remark,
        is_domestic: record.is_domestic,
      })
      setEditModalOpen(true)
    }
  }

  const handleUpdate = async () => {
    if (!editingRecord?.id) {
      message.error('跑单记录ID不存在')
      return
    }
    try {
      const values = await editForm.validateFields()
      const dateFields = ['contract_date', 'delivery_date', 'run_date', 'po_placed_date', 'material_ready_date', 'completed_date', 'shipped_date']
      const payload: Record<string, any> = {}
      for (const [k, v] of Object.entries(values)) {
        if (dateFields.includes(k) && v) {
          payload[k] = dayjs(v as any).format('YYYY-MM-DD')
        } else {
          payload[k] = v ?? null
        }
      }
      await runOrderApi.update(editingRecord.id, payload)
      message.success('跑单更新成功')
      setEditModalOpen(false)
      editForm.resetFields()
      setEditingRecord(null)
      fetchOrders(pagination.current, pagination.pageSize)
    } catch {
      // validateFields 失败时自动提示
    }
  }

  const syncRecord = async (record: RunOrderRow) => {
    if (record.id) return record
    const res: any = await runOrderApi.syncFromOrder(record.order_no)
    return { ...record, ...res.data, is_synced: true }
  }

  const handleCellSave = async (record: RunOrderRow, field: keyof RunOrderRow, value: any) => {
    const cellKey = `${record.order_no}-${String(field)}`
    if (savingCell) return
    setSavingCell(cellKey)
    try {
      const target = await syncRecord(record)
      if (!target.id) throw new Error('missing id')
      const payload = { [field]: value ?? null }
      const res: any = await runOrderApi.update(target.id, payload)
      setOrders(prev => prev.map(item => (
        item.order_no === record.order_no ? { ...item, ...target, ...res.data, is_synced: true } : item
      )))
      message.success('保存成功')
    } catch {
      message.error('保存失败')
    } finally {
      setSavingCell(null)
    }
  }

  const editableText = (field: keyof RunOrderRow) => (value: string | null, record: RunOrderRow) => {
    const cellKey = `${record.order_no}-${String(field)}`
    const isEditing = editingCell === cellKey
    return (
      <Spin spinning={savingCell === cellKey} size="small">
        {isEditing ? (
          <Input
            size="small"
            defaultValue={value || ''}
            autoFocus
            onBlur={e => {
              const next = e.target.value.trim()
              if ((value || '') !== next) handleCellSave(record, field, next || null)
              setEditingCell(null)
            }}
            onPressEnter={e => e.currentTarget.blur()}
          />
        ) : (
          <div
            onClick={() => setEditingCell(cellKey)}
            style={{ cursor: 'pointer', padding: '4px 8px', minHeight: '24px' }}
          >
            {value || <span style={{ color: '#cbd5e1' }}>-</span>}
          </div>
        )}
      </Spin>
    )
  }

  const editableNumber = (field: keyof RunOrderRow, min = 0) => (value: number | null, record: RunOrderRow) => {
    const cellKey = `${record.order_no}-${String(field)}`
    const isEditing = editingCell === cellKey
    return (
      <Spin spinning={savingCell === cellKey} size="small">
        {isEditing ? (
          <InputNumber
            size="small"
            min={min}
            defaultValue={value ?? undefined}
            style={{ width: '100%' }}
            autoFocus
            onBlur={e => {
              const raw = e.target.value
              const next = raw === '' ? null : Number(raw)
              if ((value ?? null) !== next && (next == null || !Number.isNaN(next))) handleCellSave(record, field, next)
              setEditingCell(null)
            }}
            onPressEnter={e => e.currentTarget.blur()}
          />
        ) : (
          <div
            onClick={() => setEditingCell(cellKey)}
            style={{ cursor: 'pointer', padding: '4px 8px', textAlign: 'right' }}
          >
            {value != null ? value : <span style={{ color: '#cbd5e1' }}>-</span>}
          </div>
        )}
      </Spin>
    )
  }

  const editableDate = (field: keyof RunOrderRow, green = false) => (value: string | null, record: RunOrderRow) => {
    const cellKey = `${record.order_no}-${String(field)}`
    const isEditing = editingCell === cellKey
    return (
      <Spin spinning={savingCell === cellKey} size="small">
        {isEditing ? (
          <DatePicker
            size="small"
            value={value ? dayjs(value) : null}
            style={{ width: '100%', color: green ? '#16a34a' : undefined }}
            autoFocus
            onChange={(d) => {
              handleCellSave(record, field, d ? d.format('YYYY-MM-DD') : null)
              setEditingCell(null)
            }}
            onOpenChange={(open) => {
              if (!open) setEditingCell(null)
            }}
          />
        ) : (
          <div
            onClick={() => setEditingCell(cellKey)}
            style={{ cursor: 'pointer', padding: '4px 8px' }}
          >
            {value ? dayjs(value).format('YYYY-MM-DD') : <span style={{ color: '#cbd5e1' }}>-</span>}
          </div>
        )}
      </Spin>
    )
  }

  const columns: any[] = [
    {
      title: '同步状态', dataIndex: 'is_synced', key: 'is_synced', width: 90, fixed: 'left' as const,
      render: (v: boolean) => {
        return v ? <Tag color="green">已同步</Tag> : <Tag color="orange">未同步</Tag>
      },
    },
    {
      title: '客户代码', dataIndex: 'customer_code', key: 'customer_code', width: 90, fixed: 'left' as const, sorter: true,
      render: (v: string, record: RunOrderRow) => {
        if (!v) return '-'
        const firstDashIndex = v.indexOf('-')
        const displayValue = firstDashIndex !== -1 ? v.substring(firstDashIndex + 1) : v
        return <Tooltip title={v}>{displayValue}</Tooltip>
      },
    },
    {
      title: '订单号', dataIndex: 'order_no', key: 'order_no', width: 155, fixed: 'left' as const, sorter: true,
      render: (v: string, record: RunOrderRow) => {
        if (!v) return '-'
        const lastDashIndex = v.lastIndexOf('-')
        const afterDash = lastDashIndex !== -1 ? v.substring(lastDashIndex + 1) : v
        // 去除前导零，但至少保留3位
        const displayValue = afterDash.replace(/^0+/, '').padStart(3, '0')
        const shipped = record.order_status === '已发货' || !!record.shipped_date
        return (
          <Tooltip title={v}>
            <span style={{ fontWeight: 600, fontSize: 'calc(0.75rem * var(--font-size-scale))', color: shipped ? '#16a34a' : undefined }}>{displayValue}</span>
          </Tooltip>
        )
      },
    },
    {
      title: '数量', dataIndex: 'order_qty', key: 'order_qty', width: 75, align: 'right' as const,
      render: editableNumber('order_qty'), sorter: true,
    },
    {
      title: '订单性质', dataIndex: 'order_type', key: 'order_type', width: 80,
      render: (v: string) => {
        if (!v) return '-'
        const color = v === '返单' ? 'blue' : v === '新订单' ? 'green' : v === '补单' ? 'orange' : 'default'
        return <Tag color={color}>{v}</Tag>
      },
      filters: ORDER_TYPES.map(o => ({ text: o.label, value: o.value })),
      filterMultiple: true,
    },
    { title: '合同日期', dataIndex: 'contract_date', key: 'contract_date', width: 100, sorter: true,
      render: editableDate('contract_date'),
    },
    {
      title: '交付日期', dataIndex: 'delivery_date', key: 'delivery_date', width: 100, sorter: true,
      render: editableDate('delivery_date'),
    },
    { title: '跑单日期', dataIndex: 'run_date', key: 'run_date', width: 100, sorter: true,
      render: editableDate('run_date'),
    },
    {
      title: '跑单时间(天)', dataIndex: 'run_days', key: 'run_days', width: 95, align: 'right' as const, sorter: true,
      render: editableNumber('run_days'),
    },
    {
      title: '订单金额', dataIndex: 'order_amount', key: 'order_amount', width: 100, align: 'right' as const, sorter: true,
      render: editableNumber('order_amount'),
    },
    {
      title: '包材未投放', dataIndex: 'packaging_not_released', key: 'packaging_not_released', width: 100,
      ellipsis: true,
      render: editableText('packaging_not_released'),
    },
    { title: '下单时间', dataIndex: 'po_placed_date', key: 'po_placed_date', width: 100, sorter: true,
      render: editableDate('po_placed_date'),
    },
    {
      title: '齐套时间', dataIndex: 'material_ready_date', key: 'material_ready_date', width: 100, sorter: true,
      render: editableDate('material_ready_date', true),
    },
    {
      title: '采购周期(天)', dataIndex: 'procurement_cycle', key: 'procurement_cycle', width: 95, align: 'right' as const, sorter: true,
      render: editableNumber('procurement_cycle'),
    },
    {
      title: '完成', dataIndex: 'completed_date', key: 'completed_date', width: 100, sorter: true,
      render: editableDate('completed_date', true),
    },
    {
      title: '发货', dataIndex: 'shipped_date', key: 'shipped_date', width: 100, sorter: true,
      render: editableDate('shipped_date', true),
    },
    {
      title: '未及时原因分析', dataIndex: 'delay_reason', key: 'delay_reason', width: 180,
      ellipsis: true,
      render: editableText('delay_reason'),
    },
    {
      title: '备注', dataIndex: 'remark', key: 'remark', width: 150,
      ellipsis: true,
      render: editableText('remark'),
    },
    {
      title: '订单状态', dataIndex: 'order_status', key: 'order_status', width: 90, fixed: 'right' as const,
      render: (v: string) => {
        if (!v) return '-'
        const color = v === '已完成' ? 'green' : v === '已发货' ? 'blue' : v === '进行中' ? 'orange' : 'default'
        return <Tag color={color}>{v}</Tag>
      },
      filters: [
        { text: '进行中', value: '进行中' },
        { text: '已完成', value: '已完成' },
        { text: '已发货（绿色）', value: '已发货' },
      ],
      filterMultiple: true,
    },
    {
      title: '操作', key: 'action', width: 70, fixed: 'right' as const,
      render: (_: any, record: RunOrderRow) => (
        <Button
          type="text"
          size="small"
          icon={<EditOutlined />}
          onClick={() => handleEdit(record)}
          loading={syncingOrderNo === record.order_no}
          disabled={syncingOrderNo === record.order_no}
        />
      ),
    },
  ]

  return (
    <div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '总跑单', value: summary.total, icon: <OrderedListOutlined />, color: '#6366f1' },
          { title: '已完成', value: summary.completed, icon: <CheckCircleOutlined />, color: '#16a34a' },
          { title: '已发货', value: summary.shipped, icon: <SendOutlined />, color: '#2563eb' },
          { title: '平均跑单天数', value: summary.avgDays, icon: <FieldTimeOutlined />, color: '#ca8a04' },
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

      <div className="card-modern" style={{ padding: '14px 20px', marginBottom: 16 }}>
        <Row gutter={[12, 12]} align="middle">
          <Col xs={24} sm={12} md={6}>
            <Input
              placeholder="搜索订单号/客户代码"
              prefix={<SearchOutlined />}
              allowClear
              value={filters.keyword}
              onChange={e => setFilters(f => ({ ...f, keyword: e.target.value }))}
              onPressEnter={() => fetchOrders(1)}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => { createForm.resetFields(); setCreateModalOpen(true) }}>新增跑单</Button>
              <Button icon={<ReloadOutlined />} onClick={() => fetchOrders()}>刷新</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '2px 0 0' }}>
        <div className="table-modern">
          <Table
            columns={columns}
            dataSource={orders}
            rowKey="id"
            loading={loading}
            size="small"
            scroll={{ x: 2200, y: 'calc(100vh - 380px)' }}
            locale={{ emptyText: '暂无跑单数据' }}
            onChange={handleTableChange}
            pagination={{
              ...pagination,
              showSizeChanger: true,
              pageSizeOptions: ['20', '50', '100'],
              showTotal: (total) => `共 ${total} 条`,
              onChange: (page, pageSize) => fetchOrders(page, pageSize),
              style: { padding: '0 16px' },
            }}
          />
        </div>
      </div>

      <Modal
        title="新增跑单"
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => setCreateModalOpen(false)}
        okText="创建"
        cancelText="取消"
        width={680}
        destroyOnClose
      >
        <Form form={createForm} layout="vertical" style={{ maxHeight: '60vh', overflowY: 'auto', paddingRight: 8 }}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="order_no" label="订单号" rules={[{ required: true, message: '请输入订单号' }]}>
                <Input placeholder="必填" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="customer_code" label="客户代码">
                <Input placeholder="选填" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="order_qty" label="数量">
                <InputNumber min={0} style={{ width: '100%' }} placeholder="选填" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="order_type" label="订单性质">
                <Select allowClear placeholder="选填" options={ORDER_TYPES} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contract_date" label="合同日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="delivery_date" label="交付日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="run_date" label="跑单日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="run_days" label="跑单时间(天)">
                <InputNumber min={0} style={{ width: '100%' }} placeholder="选填" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="order_amount" label="订单金额">
                <InputNumber min={0} style={{ width: '100%' }} placeholder="选填" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="order_status" label="订单状态">
                <Select allowClear placeholder="选填" options={[
                  { value: '进行中', label: '进行中' },
                  { value: '已完成', label: '已完成' },
                  { value: '已发货', label: '已发货' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="po_placed_date" label="下单时间">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="material_ready_date" label="齐套时间">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="procurement_cycle" label="采购周期(天)">
                <InputNumber min={0} style={{ width: '100%' }} placeholder="选填" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="completed_date" label="完成日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="shipped_date" label="发货日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="is_domestic" label="是否内销">
                <Select options={[{ value: false, label: '外销' }, { value: true, label: '内销' }]} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="packaging_not_released" label="包材未投放">
                <Input placeholder="选填" />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="delay_reason" label="未及时原因分析">
                <Input.TextArea rows={2} placeholder="选填" />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="remark" label="备注">
                <Input.TextArea rows={2} placeholder="选填" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        title="编辑跑单"
        open={editModalOpen}
        onOk={handleUpdate}
        onCancel={() => {
          setEditModalOpen(false)
          editForm.resetFields()
          setEditingRecord(null)
        }}
        okText="保存"
        cancelText="取消"
        width={680}
        destroyOnClose
      >
        <Form form={editForm} layout="vertical" style={{ maxHeight: '60vh', overflowY: 'auto', paddingRight: 8 }}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="order_no" label="订单号">
                <Input disabled />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="customer_code" label="客户代码">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="order_qty" label="数量">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="order_type" label="订单性质">
                <Select allowClear options={ORDER_TYPES} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="contract_date" label="合同日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="delivery_date" label="交付日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="run_date" label="跑单日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="run_days" label="跑单时间(天)">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="order_amount" label="订单金额">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="order_status" label="订单状态">
                <Select allowClear options={[
                  { value: '进行中', label: '进行中' },
                  { value: '已完成', label: '已完成' },
                  { value: '已发货', label: '已发货' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="po_placed_date" label="下单时间">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="material_ready_date" label="齐套时间">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="procurement_cycle" label="采购周期(天)">
                <InputNumber min={0} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="completed_date" label="完成日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="shipped_date" label="发货日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="is_domestic" label="是否内销">
                <Select options={[{ value: false, label: '外销' }, { value: true, label: '内销' }]} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="packaging_not_released" label="包材未投放">
                <Input />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="delay_reason" label="未及时原因分析">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="remark" label="备注">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </div>
  )
}
