import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Row, Col, Table, Tag, Input, Select, Button, message, Tooltip, Card } from 'antd'
import {
  SearchOutlined, ReloadOutlined, EditOutlined,
  ShoppingCartOutlined, CheckCircleOutlined, ClockCircleOutlined,
} from '@ant-design/icons'
import { orderApi } from '../../../services/api'

interface OrderRow {
  id: number
  order_no: string
  line_no: string | null
  customer: string | null
  customer_code: string | null
  order_qty: number | null
  promised_date: string | null
  department: string | null
  status: string
  delivery_completed_date: string | null
  customer_grade: string | null
  shipping_plan: string | null
  packaging_status: string | null
  shipping_status_desc: string | null
  remark: string | null
  order_date: string | null
}

interface Filters {
  keyword: string
  shipped: string
}

interface SortInfo {
  sort_by?: string
  sort_order?: string
}


export default function DomesticShipment() {
  const navigate = useNavigate()
  const [orders, setOrders] = useState<OrderRow[]>([])
  const [loading, setLoading] = useState(false)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 50, total: 0 })
  const [filters, setFilters] = useState<Filters>({ keyword: '', shipped: '' })
  const [sortInfo, setSortInfo] = useState<SortInfo>({})
  const [summary, setSummary] = useState({ total: 0, shipped: 0, pending: 0 })

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
      if (filters.shipped === 'true') params.shipped = true
      if (filters.shipped === 'false') params.shipped = false
      const res: any = await orderApi.listDomesticShipment(params)
      const items: OrderRow[] = res.data.items || []
      setOrders(items)
      setPagination({ current: res.data.page, pageSize: res.data.page_size, total: res.data.total })
      // 使用后端返回的全局统计
      const stats = res.data.stats || {}
      setSummary({
        total: stats.total || res.data.total,
        shipped: stats.shipped_count || 0,
        pending: stats.pending_count || 0,
      })
    } catch {
      message.error('获取内销出货数据失败')
    } finally {
      setLoading(false)
    }
  }, [filters, sortInfo])

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchOrders() }, [])

  const handleTableChange = (pag: any, _tableFilters: any, sorter: any) => {
    const sortField = sorter.field
    const sortOrder = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : undefined
    const newSort = { sort_by: sortField, sort_order: sortOrder }
    setSortInfo(newSort)
    fetchOrders(pag.current, pag.pageSize, newSort)
  }

  const columns: any[] = [
    {
      title: '客户等级', dataIndex: 'customer_grade', key: 'customer_grade', width: 70, fixed: 'left' as const,
      render: (v: string) => v ? <Tag color={v === 'A' ? 'red' : v === 'B' ? 'orange' : 'blue'}>{v}</Tag> : '-', sorter: true,
    },
    {
      title: '客户', dataIndex: 'customer_code', key: 'customer_code', width: 90, fixed: 'left' as const, ellipsis: true, sorter: true,
      render: (v: string) => {
        if (!v) return '-'
        const firstDashIndex = v.indexOf('-')
        const displayValue = firstDashIndex !== -1 ? v.substring(firstDashIndex + 1) : v
        return <Tooltip title={v}>{displayValue}</Tooltip>
      },
    },
    {
      title: '单号', dataIndex: 'order_no', key: 'order_no', width: 155, fixed: 'left' as const, sorter: true,
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
      title: '数量', dataIndex: 'order_qty', key: 'order_qty', width: 75, align: 'right' as const,
      render: (v: number) => v?.toLocaleString() || '-', sorter: true,
    },
    {
      title: '下单时间', dataIndex: 'order_date', key: 'order_date', width: 95,
      render: (v: string) => v || '-', sorter: true,
    },
    {
      title: '合同交期', dataIndex: 'promised_date', key: 'promised_date', width: 100, sorter: true,
      render: (v: string) => {
        if (!v) return '-'
        const overdue = v < new Date().toISOString().slice(0, 10)
        return <span style={{ color: overdue ? '#e11d48' : undefined, fontWeight: overdue ? 600 : undefined }}>{v}</span>
      },
    },
    {
      title: '出货计划', dataIndex: 'shipping_plan', key: 'shipping_plan', width: 100, sorter: true,
      render: (v: string) => v ? <span style={{ color: '#ca8a04', fontWeight: 500 }}>{v}</span> : '-',
    },
    {
      title: '发货完成日期', dataIndex: 'delivery_completed_date', key: 'delivery_completed_date', width: 110, sorter: true,
      render: (v: string) => v ? <span style={{ color: '#16a34a', fontWeight: 600 }}>{v}</span> : <Tag color="orange">未发货</Tag>,
    },
    {
      title: '包装完成状况', dataIndex: 'packaging_status', key: 'packaging_status', width: 130,
      ellipsis: true,
      render: (v: string) => {
        if (!v) return '-'
        const isBlue = v.includes('完成') && !v.includes('入库')
        const isGreen = v.includes('入库')
        return <span style={{ color: isGreen ? '#16a34a' : isBlue ? '#2563eb' : undefined }}>{v}</span>
      },
    },
    {
      title: '发货状态即时说明', dataIndex: 'shipping_status_desc', key: 'shipping_status_desc', width: 200,
      ellipsis: true,
    },
    {
      title: '发货状态', key: 'ship_status', width: 90,
      render: (_: any, r: OrderRow) => {
        if (r.delivery_completed_date) return <Tag color="green">已发货</Tag>
        if (r.shipping_plan) return <Tag color="blue">已排计划</Tag>
        return <Tag color="default">待排计划</Tag>
      },
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

      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '总计', value: summary.total, icon: <ShoppingCartOutlined />, color: '#6366f1' },
          { title: '已发货', value: summary.shipped, icon: <CheckCircleOutlined />, color: '#16a34a' },
          { title: '待发货', value: summary.pending, icon: <ClockCircleOutlined />, color: '#f59e0b' },
        ].map((card, i) => (
          <Col span={8} key={i}>
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
            <Input placeholder="搜索订单号/客户" prefix={<SearchOutlined />} allowClear
              value={filters.keyword} onChange={e => setFilters(f => ({ ...f, keyword: e.target.value }))}
              onPressEnter={() => fetchOrders(1)} />
          </Col>
          <Col xs={12} sm={6} md={4}>
            <Select placeholder="发货状态" allowClear style={{ width: '100%' }}
              value={filters.shipped || undefined} onChange={v => setFilters(f => ({ ...f, shipped: v || '' }))}
              options={[{ value: 'true', label: '已发货' }, { value: 'false', label: '未发货' }]} />
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
            scroll={{ x: 1400, y: 'calc(100vh - 380px)' }} locale={{ emptyText: '暂无内销出货数据' }}
            onChange={handleTableChange}
            pagination={{ ...pagination, showSizeChanger: true, pageSizeOptions: ['20', '50', '100'],
              showTotal: (total) => `共 ${total} 条`,
              style: { padding: '0 16px' } }} />
        </div>
      </div>
    </div>
  )
}
