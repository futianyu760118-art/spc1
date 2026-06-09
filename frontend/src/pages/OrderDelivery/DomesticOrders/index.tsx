import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Row, Col, Table, Tag, Input, Select, Button, message, Space, Tooltip } from 'antd'
import { SearchOutlined, ReloadOutlined, EditOutlined } from '@ant-design/icons'
import RiskBadge from '../../../components/RiskBadge'
import { orderApi } from '../../../services/api'

interface OrderRow {
  id: number
  order_no: string
  line_no: string | null
  customer: string | null
  customer_code: string | null
  order_qty: number | null
  promised_date: string | null
  planned_start_date: string | null
  department: string | null
  status: string
  risk_level: string | null
  delivery_completed_date: string | null
  customer_grade: string | null
  shipping_plan: string | null
  customer_inspection_date: string | null
  inspection_result: string | null
  packaging_status: string | null
  material_ready_date: string | null
  shipping_status_desc: string | null
  procurement_status: string | null
  material_dates: Record<string, string> | null
  front_process_date: string | null
  first_article_date: string | null
  assembly_start_date: string | null
  assembly_complete_date: string | null
  remark: string | null
  order_date: string | null
}

interface Filters {
  keyword: string
  status: string
}

interface SortInfo {
  sort_by?: string
  sort_order?: string
}

const MATERIAL_KEYS = [
  '电子料', 'SMT上线', '光源', '感应器/电源/控制板',
  '结构', '结构2', '支架', '电缆线', '塑料件', '手杆',
  '彩盒', '说明书', '灯珠', '光源板', '电源板', '包材',
]

const todayStr = () => new Date().toISOString().slice(0, 10)

function DateCell({ value, overdue }: { value: string | null; overdue?: boolean }) {
  if (!value) return <span style={{ color: '#cbd5e1' }}>-</span>
  return <span style={{ color: overdue ? '#e11d48' : undefined, fontWeight: overdue ? 600 : undefined }}>{value}</span>
}

function GreenDateCell({ value }: { value: string | null }) {
  if (!value) return <span style={{ color: '#cbd5e1' }}>-</span>
  return <span style={{ color: '#16a34a', fontWeight: 500 }}>{value}</span>
}

export default function DomesticOrders() {
  const navigate = useNavigate()
  const [orders, setOrders] = useState<OrderRow[]>([])
  const [loading, setLoading] = useState(false)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 50, total: 0 })
  const [filters, setFilters] = useState<Filters>({ keyword: '', status: '' })
  const [sortInfo, setSortInfo] = useState<SortInfo>({})

  const fetchOrders = useCallback(async (
    page = 1,
    pageSize = 50,
    overrideSort?: SortInfo,
  ) => {
    setLoading(true)
    try {
      const s = overrideSort ?? sortInfo
      const params: Record<string, any> = { page, page_size: pageSize }
      if (s.sort_by) params.sort_by = s.sort_by
      if (s.sort_order) params.sort_order = s.sort_order
      if (filters.keyword) params.keyword = filters.keyword
      if (filters.status) params.status = filters.status
      const res: any = await orderApi.listDomestic(params)
      setOrders(res.data.items || [])
      setPagination({ current: res.data.page, pageSize: res.data.page_size, total: res.data.total })
    } catch {
      message.error('获取内销订单失败')
    } finally {
      setLoading(false)
    }
  }, [filters, sortInfo])

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchOrders() }, [])

  const handleTableChange = (pag: any, _tableFilters: any, sorter: any) => {
    let sortField = sorter.field
    const sortOrder = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : undefined
    if (sortField === 'risk_level') sortField = 'risk_score'
    const newSort = { sort_by: sortField, sort_order: sortOrder }
    setSortInfo(newSort)
    fetchOrders(pag.current, pag.pageSize, newSort)
  }

  const columns: any[] = [
    { title: '销售部门', dataIndex: 'department', key: 'department', width: 80, fixed: 'left' as const, sorter: true },
    {
      title: '发货完成', dataIndex: 'delivery_completed_date', key: 'delivery_completed_date', width: 95, fixed: 'left' as const,
      render: (v: string) => <GreenDateCell value={v} />, sorter: true,
    },
    {
      title: '客户等级', dataIndex: 'customer_grade', key: 'customer_grade', width: 70,
      render: (v: string) => v ? <Tag color={v === 'A' ? 'red' : v === 'B' ? 'orange' : 'blue'}>{v}</Tag> : '-', sorter: true,
    },
    {
      title: '客户', dataIndex: 'customer_code', key: 'customer_code', width: 80, ellipsis: true, sorter: true,
      render: (v: string) => {
        if (!v) return '-'
        const firstDashIndex = v.indexOf('-')
        const displayValue = firstDashIndex !== -1 ? v.substring(firstDashIndex + 1) : v
        return <Tooltip title={v}>{displayValue}</Tooltip>
      },
    },
    {
      title: '单号', dataIndex: 'order_no', key: 'order_no', width: 145, fixed: 'left' as const, sorter: true,
      render: (v: string, r: OrderRow) => {
        if (!v) return '-'
        const lastDashIndex = v.lastIndexOf('-')
        const afterDash = lastDashIndex !== -1 ? v.substring(lastDashIndex + 1) : v
        // 去除前导零，但至少保留3位
        const displayValue = afterDash.replace(/^0+/, '').padStart(3, '0')
        return (
          <Tooltip title={v}>
            <a onClick={() => navigate(`/orders/${v}/lines/${r.line_no || '10'}`)} style={{ fontWeight: 600, fontSize: 'calc(0.75rem * var(--font-size-scale))' }}>{displayValue}</a>
          </Tooltip>
        )
      },
    },
    {
      title: '数量', dataIndex: 'order_qty', key: 'order_qty', width: 70, align: 'right' as const,
      render: (v: number) => v?.toLocaleString() || '-', sorter: true,
    },
    {
      title: '下单时间', dataIndex: 'order_date', key: 'order_date', width: 95,
      render: (v: string) => <DateCell value={v} />, sorter: true,
    },
    {
      title: '合同交期', dataIndex: 'promised_date', key: 'promised_date', width: 95,
      render: (v: string, r: OrderRow) => <DateCell value={v} overdue={!!(v && v < todayStr() && r.status !== 'closed')} />, sorter: true,
    },
    { title: '出货计划', dataIndex: 'shipping_plan', key: 'shipping_plan', width: 95, sorter: true },
    { title: '客户验货时间', dataIndex: 'customer_inspection_date', key: 'customer_inspection_date', width: 105, sorter: true },
    { title: '上线时间', dataIndex: 'planned_start_date', key: 'planned_start_date', width: 95, sorter: true },
    {
      title: '客检结果', dataIndex: 'inspection_result', key: 'inspection_result', width: 80,
      render: (v: string) => {
        if (!v) return '-'
        const color = v === 'OK' || v === '通过' ? '#16a34a' : v === 'NG' ? '#e11d48' : undefined
        return <span style={{ color, fontWeight: 600 }}>{v}</span>
      },
    },
    { title: '包装完成状况', dataIndex: 'packaging_status', key: 'packaging_status', width: 110, ellipsis: true },
    { title: '料齐套时间', dataIndex: 'material_ready_date', key: 'material_ready_date', width: 95, render: (v: string) => <GreenDateCell value={v} />, sorter: true },
    { title: '发货状态即时说明', dataIndex: 'shipping_status_desc', key: 'shipping_status_desc', width: 150, ellipsis: true },
    { title: '采购物料齐套', dataIndex: 'procurement_status', key: 'procurement_status', width: 120, ellipsis: true },
    ...MATERIAL_KEYS.map(key => ({
      title: key, key: `mat_${key}`, width: key.length > 6 ? 120 : 80,
      render: (_: any, r: OrderRow) => {
        const val = r.material_dates?.[key]
        return val ? <span style={{ fontSize: 12 }}>{val}</span> : <span style={{ color: '#cbd5e1' }}>-</span>
      },
    })),
    { title: '前道', dataIndex: 'front_process_date', key: 'front_process_date', width: 90, sorter: true },
    { title: '首件检验日期', dataIndex: 'first_article_date', key: 'first_article_date', width: 105, sorter: true },
    { title: '组装上线日期', dataIndex: 'assembly_start_date', key: 'assembly_start_date', width: 105, sorter: true },
    { title: '组装完成日期', dataIndex: 'assembly_complete_date', key: 'assembly_complete_date', width: 105, render: (v: string) => <GreenDateCell value={v} />, sorter: true },
    {
      title: '风险', dataIndex: 'risk_level', key: 'risk_level', width: 70,
      render: (level: string) => <RiskBadge level={level} />,
    },
    { title: '备注', dataIndex: 'remark', key: 'remark', width: 150, fixed: 'right' as const, ellipsis: true },
    {
      title: '', key: 'action', width: 60, fixed: 'right' as const,
      render: (_: any, r: OrderRow) => (
        <Button type="link" size="small" icon={<EditOutlined />}
          onClick={() => navigate(`/orders/${r.order_no}/lines/${r.line_no || '10'}`)}
        />
      ),
    },
  ]

  return (
    <div>

      <div className="card-modern" style={{ padding: '14px 20px', marginBottom: 16 }}>
        <Row gutter={[12, 12]} align="middle">
          <Col xs={24} sm={12} md={6}>
            <Input placeholder="搜索订单号/客户" prefix={<SearchOutlined />} allowClear
              value={filters.keyword} onChange={e => setFilters(f => ({ ...f, keyword: e.target.value }))}
              onPressEnter={() => fetchOrders(1)} />
          </Col>
          <Col xs={12} sm={6} md={4}>
            <Select placeholder="订单状态" allowClear style={{ width: '100%' }}
              value={filters.status || undefined} onChange={v => setFilters(f => ({ ...f, status: v || '' }))}
              options={[{ value: 'open', label: '待处理' }, { value: 'in_progress', label: '处理中' }, { value: 'closed', label: '已关闭' }]} />
          </Col>
          <Col xs={12} sm={6} md={2}>
            <Button type="primary" icon={<SearchOutlined />} onClick={() => fetchOrders(1)} block>查询</Button>
          </Col>
          <Col flex="auto" />
          <Col>
            <Button icon={<ReloadOutlined />} onClick={() => fetchOrders()}>刷新</Button>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '2px 0 0' }}>
        <div className="table-modern">
          <Table columns={columns} dataSource={orders} rowKey="id" loading={loading} size="small"
            scroll={{ x: 4200, y: 'calc(100vh - 340px)' }} locale={{ emptyText: '暂无内销订单' }}
            onChange={handleTableChange}
            pagination={{ ...pagination, showSizeChanger: true, pageSizeOptions: ['20', '50', '100'],
              showTotal: (total) => `共 ${total} 条`,
              style: { padding: '0 16px' } }} />
        </div>
      </div>
    </div>
  )
}
