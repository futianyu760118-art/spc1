import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import {
  Table, Tag, Input, Select, Button, Space, message, Modal, Form,
  DatePicker, Upload, Tooltip, Row, Col, Card,
} from 'antd'
import {
  SearchOutlined, ReloadOutlined, UploadOutlined, PlusOutlined, EditOutlined,
  ShoppingOutlined, ClockCircleOutlined, CheckCircleOutlined,
  WarningOutlined, ExclamationCircleOutlined, StopOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { materialApi, orderApi } from '../../../services/api'
import { formatDate } from '../../../utils'

interface PlanRow {
  id: number
  po_no: string
  supplier_name: string | null
  material_code: string
  material_name: string | null
  spec_model: string | null
  unit: string | null
  po_qty: number | null
  received_qty: number | null
  eta: string | null
  order_no: string | null
  actual_arrival_date: string | null
  arrival_hour_note: string | null
  inspection_date: string | null
  po_status: string
  is_stagnant: boolean
  stagnant_qty: number | null
  owner: string | null
  po_date: string | null
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  inspected: { label: '已检验', color: 'success' },
  arrived: { label: '已到料', color: 'processing' },
  overdue: { label: '逾期未到', color: 'error' },
  pending: { label: '待到料', color: 'default' },
  stagnant: { label: '呆滞物料', color: 'warning' },
}

export default function PurchasePlan() {
  const today = useMemo(() => new Date().toISOString().slice(0, 10), [])
  const [data, setData] = useState<PlanRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState({ keyword: '', po_status: [] as string[] })
  const [sortBy, setSortBy] = useState<string>('')
  const [sortOrder, setSortOrder] = useState<string>('')
  const [editModal, setEditModal] = useState(false)
  const [editRecord, setEditRecord] = useState<PlanRow | null>(null)
  const [addModal, setAddModal] = useState(false)
  const [orderList, setOrderList] = useState<any[]>([])
  const [orderLoading, setOrderLoading] = useState(false)
  const [form] = Form.useForm()
  const uploadRef = useRef<any>(null)
  const [stats, setStats] = useState({ total: 0, pending: 0, arrived: 0, inspected: 0, overdue: 0, stagnant: 0 })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await materialApi.listPurchasePlan({
        page, page_size: pageSize,
        ...(filters.keyword ? { keyword: filters.keyword } : {}),
        ...(filters.po_status.length ? { po_status: filters.po_status.join(',') } : {}),
        ...(sortBy ? { sort_by: sortBy, sort_order: sortOrder || 'asc' } : {}),
      })
      setData(res.data.items)
      setTotal(res.data.total)
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, filters, sortBy, sortOrder])

  const loadOrders = useCallback(async (keyword = '') => {
    setOrderLoading(true)
    try {
      const res: any = await orderApi.list({ page: 1, page_size: 100, keyword })
      setOrderList(res.data.items || [])
    } catch (e: any) {
      message.error('加载订单列表失败')
    } finally {
      setOrderLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const loadStats = useCallback(async () => {
    try {
      const res: any = await materialApi.getPurchasePlanStats({})
      setStats(res.data)
    } catch (e: any) {
      console.error('加载统计数据失败', e)
    }
  }, [])

  useEffect(() => { loadStats() }, [loadStats])

  const openEdit = (row: PlanRow) => {
    setEditRecord(row)
    loadOrders()
    form.setFieldsValue({
      supplier_name: row.supplier_name,
      material_code: row.material_code,
      material_name: row.material_name,
      spec_model: row.spec_model,
      unit: row.unit,
      po_qty: row.po_qty,
      received_qty: row.received_qty,
      eta: row.eta ? dayjs(row.eta) : null,
      order_no: row.order_no,
      actual_arrival_date: row.actual_arrival_date ? dayjs(row.actual_arrival_date) : null,
      arrival_hour_note: row.arrival_hour_note,
      inspection_date: row.inspection_date ? dayjs(row.inspection_date) : null,
      owner: row.owner,
    })
    setEditModal(true)
  }

  const handleEditSubmit = async (values: any) => {
    try {
      if (!editRecord) return
      const payload: Record<string, any> = {
        supplier_name: values.supplier_name,
        material_name: values.material_name,
        spec_model: values.spec_model,
        unit: values.unit,
        po_qty: values.po_qty,
        received_qty: values.received_qty,
        eta: values.eta ? dayjs(values.eta).format('YYYY-MM-DD') : null,
        order_no: values.order_no,
        actual_arrival_date: values.actual_arrival_date ? dayjs(values.actual_arrival_date).format('YYYY-MM-DD') : null,
        arrival_hour_note: values.arrival_hour_note,
        inspection_date: values.inspection_date ? dayjs(values.inspection_date).format('YYYY-MM-DD') : null,
        owner: values.owner || null,
      }
      await materialApi.updatePurchasePlan(editRecord.id, payload)
      message.success('保存成功')
      setEditModal(false)
      load()
      loadStats()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const handleAdd = async (values: any) => {
    try {
      const payload = {
        po_no: `CSV-MANUAL-${Date.now()}`,
        material_code: values.material_code,
        supplier_name: values.supplier_name,
        material_name: values.material_name,
        spec_model: values.spec_model,
        unit: values.unit,
        po_qty: values.po_qty,
        received_qty: values.received_qty,
        eta: values.eta ? dayjs(values.eta).format('YYYY-MM-DD') : null,
        order_no: values.order_no,
        owner: values.owner || null,
        po_status: 'pending',
        data_source: 'csv_plan',
      }
      await materialApi.createPurchasePlan(payload)
      message.success('新增成功')
      setAddModal(false)
      form.resetFields()
      load()
      loadStats()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const handleImport = async (file: File) => {
    try {
      const res: any = await materialApi.importPurchasePlan(file)
      message.success(`导入完成：新增 ${res.data.created}，更新 ${res.data.updated}，跳过 ${res.data.skipped}`)
      load()
      loadStats()
    } catch (e: any) {
      message.error(`导入失败：${e.message}`)
    }
    return false
  }

  const columns = [
    {
      title: '供应商', dataIndex: 'supplier_name', maxWidth: 100, ellipsis: true, fixed: 'left' as const, sorter: true,
      onCell: () => ({ style: { maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }),
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '物料长代码', dataIndex: 'material_code', maxWidth: 100, ellipsis: true, fixed: 'left' as const, sorter: true,
      onCell: () => ({ style: { maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }),
      render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    {
      title: '物料名称', dataIndex: 'material_name', maxWidth: 100, ellipsis: true, fixed: 'left' as const, sorter: true,
      onCell: () => ({ style: { maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }),
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    { title: '规格型号', dataIndex: 'spec_model', maxWidth: 150, ellipsis: true, sorter: true,
      onCell: () => ({ style: { maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }),
    },
    { title: '单位', dataIndex: 'unit', width: 60 },
    {
      title: '下单日期', dataIndex: 'po_date', width: 100, sorter: true,
      render: (v: string | null) => v ? formatDate(v) : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '数量', dataIndex: 'po_qty', width: 80,
      render: (v: number | null) => v ?? '-',
      sorter: true,
    },
    {
      title: <Tooltip title="实际入库数量">收料数量</Tooltip>, dataIndex: 'received_qty', width: 90,
      render: (v: number | null) => v ?? <span style={{ color: '#cbd5e1' }}>0</span>,
      sorter: true,
    },
    {
      title: <Tooltip title="供应商承诺交货日期">交货日期</Tooltip>, dataIndex: 'eta', width: 100,
      render: (v: string | null) => {
        if (!v) return <span style={{ color: '#cbd5e1' }}>-</span>
        const isOverdue = v < today
        return <span style={{ color: isOverdue ? '#e11d48' : undefined }}>{formatDate(v)}</span>
      },
      sorter: true,
    },
    {
      title: <Tooltip title="关联生产订单号">订单号</Tooltip>, dataIndex: 'order_no', width: 80,
      render: (v: string | null) => {
        if (!v) return <span style={{ color: '#cbd5e1' }}>-</span>
        const lastDashIndex = v.lastIndexOf('-')
        const afterDash = lastDashIndex !== -1 ? v.substring(lastDashIndex + 1) : v
        const displayValue = afterDash.replace(/^0+/, '').padStart(3, '0')
        return <Tooltip title={v}>{displayValue}</Tooltip>
      },
      sorter: true,
    },
    {
      title: <Tooltip title="实际入库日期">到料时间</Tooltip>, dataIndex: 'actual_arrival_date', width: 110,
      render: (v: string | null) => v ? <span style={{ color: '#16a34a' }}>{formatDate(v)}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
      sorter: true,
    },
    {
      title: '小时节点', dataIndex: 'arrival_hour_note', ellipsis: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '责任人', dataIndex: 'owner', width: 80, fixed: 'right' as const, sorter: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: <Tooltip title="检验单日期">检验日期</Tooltip>, dataIndex: 'inspection_date', width: 110,
      render: (v: string | null) => v ? <span style={{ color: '#6366f1' }}>{formatDate(v)}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
      sorter: true,
    },
    {
      title: <Tooltip title="呆滞物料：收料数量超过下单数量">呆滞</Tooltip>, dataIndex: 'is_stagnant', width: 80, fixed: 'right' as const,
      filters: [{ text: '呆滞物料', value: 'stagnant' }],
      filteredValue: filters.po_status.includes('stagnant') ? ['stagnant'] as (string | number | boolean)[] : null,
      render: (v: boolean, row: PlanRow) => {
        if (!v) return <span style={{ color: '#cbd5e1' }}>-</span>
        return <Tooltip title={`超量 ${row.stagnant_qty}，收料${row.received_qty} > 下单${row.po_qty}`}><Tag color="warning">呆滞 +{row.stagnant_qty}</Tag></Tooltip>
      },
    },
    {
      title: <Tooltip title="待到料 / 已到料 / 已检验 / 逾期未到 / 呆滞物料，依据到料时间与检验日期自动计算">状态</Tooltip>, dataIndex: 'po_status', width: 90, fixed: 'right' as const,
      filters: Object.entries(STATUS_MAP).filter(([key]) => key !== 'stagnant').map(([key, val]) => ({ text: val.label, value: key })),
      filteredValue: filters.po_status.filter(s => s !== 'stagnant').length ? filters.po_status.filter(s => s !== 'stagnant') as (string | number | boolean)[] : null,
      render: (v: string) => {
        const s = STATUS_MAP[v] || { label: v, color: 'default' }
        return <Tag color={s.color}>{s.label}</Tag>
      },
    },
    {
      title: '操作', width: 50, fixed: 'right' as const,
      render: (_: any, row: PlanRow) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
      ),
    },
  ]

  return (
    <div>
      {/* 统计卡 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '计划总数', value: stats.total, icon: <ShoppingOutlined />, color: '#6366f1' },
          { title: '待到料', value: stats.pending, icon: <ClockCircleOutlined />, color: '#f59e0b' },
          { title: '已到料', value: stats.arrived, icon: <ExclamationCircleOutlined />, color: '#3b82f6' },
          { title: '已检验', value: stats.inspected, icon: <CheckCircleOutlined />, color: '#16a34a' },
          { title: '逾期未到', value: stats.overdue, icon: <WarningOutlined />, color: '#e11d48' },
          { title: '呆滞物料', value: stats.stagnant, icon: <StopOutlined />, color: '#d97706' },
        ].map((card, i) => (
          <Col flex={1} key={i}>
            <Card
              size="small"
              className="card-modern"
              style={{ padding: 0 }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ width: 44, height: 44, borderRadius: 10, background: `${card.color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, color: card.color }}>
                  {card.icon}
                </div>
                <div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>{card.value}</div>
                  <div style={{ fontSize: 12, color: '#64748b' }}>{card.title}</div>
                </div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <div className="card-modern" style={{ padding: '14px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索物料/供应商/订单号"
              value={filters.keyword}
              onChange={e => { setFilters(f => ({ ...f, keyword: e.target.value })); setPage(1) }}
              style={{ width: 240 }}
              allowClear
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
              <Upload beforeUpload={(f) => { handleImport(f); return false }} showUploadList={false} accept=".csv">
                <Button icon={<UploadOutlined />}>导入CSV</Button>
              </Upload>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddModal(true)}>新增</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '2px 0 0' }}>
        <div className="table-modern">
          <Table
          rowKey="id"
          dataSource={data}
          columns={columns}
          loading={loading}
          scroll={{ x: 'max-content', y: 'calc(100vh - 380px)' }}
          size="small"
          tableLayout="fixed"
          pagination={{
            total, current: page, pageSize,
            showSizeChanger: true, showTotal: t => `共 ${t} 条`,
            pageSizeOptions: ['20', '50', '100'],
            style: { padding: '0 16px' },
          }}
          onChange={(pagination, tableFilters, sorter: any) => {
            // 分页
            setPage(pagination.current || 1)
            setPageSize(pagination.pageSize || 20)
            // 状态筛选 → 服务端筛选（合并 po_status 和 is_stagnant 列的筛选）
            const statusFilter = (tableFilters?.po_status as string[] | undefined) || []
            const stagnantFilter = (tableFilters?.is_stagnant as string[] | undefined) || []
            setFilters(prev => ({ ...prev, po_status: [...statusFilter, ...stagnantFilter] }))
            // 排序
            const sortField = sorter.field as string | undefined
            const sortDir = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : ''
            setSortBy(sortField || '')
            setSortOrder(sortDir)
          }}
        />
        </div>
      </div>

      <Modal
        title="新增采购到料计划"
        open={addModal}
        onCancel={() => { setAddModal(false); form.resetFields() }}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleAdd}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="supplier_name" label="供应商" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="material_code" label="物料长代码" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="material_name" label="物料名称">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="spec_model" label="规格型号">
                <Input />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="unit" label="单位">
                <Input />
              </Form.Item>
            </Col>
            <Col span={9}>
              <Form.Item name="po_qty" label="数量">
                <Input type="number" />
              </Form.Item>
            </Col>
            <Col span={9}>
              <Form.Item name="received_qty" label="收料数量">
                <Input type="number" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="eta" label="交货日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="order_no" label="订单号">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="owner" label="责任人">
                <Input />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        title="编辑采购到料计划"
        open={editModal}
        onCancel={() => { setEditModal(false); form.resetFields() }}
        onOk={() => form.submit()}
        width={600}
        style={{ top: 32 }}
      >
        <Form form={form} layout="vertical" size="small" onFinish={handleEditSubmit}>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="supplier_name" label="供应商">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="material_code" label="物料长代码">
                <Input disabled />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="material_name" label="物料名称">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="spec_model" label="规格型号">
                <Input />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="unit" label="单位">
                <Input />
              </Form.Item>
            </Col>
            <Col span={9}>
              <Form.Item name="po_qty" label="数量">
                <Input type="number" />
              </Form.Item>
            </Col>
            <Col span={9}>
              <Form.Item name="received_qty" label="收料数量">
                <Input type="number" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="eta" label="交货日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="order_no" label="订单号">
                <Select
                  showSearch
                  placeholder="选择或搜索订单"
                  optionFilterProp="children"
                  loading={orderLoading}
                  onSearch={(value) => loadOrders(value)}
                  filterOption={false}
                  allowClear
                >
                  {orderList.map((order: any) => (
                    <Select.Option key={order.order_no} value={order.order_no}>
                      {order.order_no}
                    </Select.Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="actual_arrival_date" label="到料时间">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="inspection_date" label="检验日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="arrival_hour_note" label="小时节点">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="owner" label="责任人">
                <Input />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </div>
  )
}
