import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Row, Col, Table, Tag, Input, Button, message, Tooltip, Card, Progress } from 'antd'
import {
  SearchOutlined, ReloadOutlined, WarningOutlined, ExclamationCircleOutlined,
  AlertOutlined, ClockCircleOutlined, SafetyCertificateOutlined,
} from '@ant-design/icons'
import RiskBadge from '../../../components/RiskBadge'
import { orderApi, riskApi } from '../../../services/api'
import { formatDate, formatDateTime } from '../../../utils'

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
  risk_score: number | null
  risk_factors: Record<string, number> | null
  risk_assessed_at: string | null
  delivery_completed_date: string | null
  customer_grade: string | null
  shipping_plan: string | null
  inspection_result: string | null
  packaging_status: string | null
  material_ready_date: string | null
  shipping_status_desc: string | null
  remark: string | null
  order_date: string | null
}

interface Filters {
  keyword: string
  risk_level: string[]
}

const FACTOR_LABELS: Record<string, string> = {
  delivery_delay: '交期延期',
  shortage: '欠料风险',
  process_lag: '工序滞后',
  quality: '品质异常',
  eta_delay: 'ETA延期',
  inspection_ng: '客检NG',
}

const FACTOR_MAX: Record<string, number> = {
  delivery_delay: 25,
  shortage: 30,
  process_lag: 15,
  quality: 15,
  eta_delay: 20,
  inspection_ng: 15,
}


export default function OrderRiskPool() {
  const navigate = useNavigate()
  const [orders, setOrders] = useState<OrderRow[]>([])
  const [loading, setLoading] = useState(false)
  const [assessing, setAssessing] = useState(false)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 50, total: 0 })
  const [filters, setFilters] = useState<Filters>({ keyword: '', risk_level: [] })
  const [sortInfo, setSortInfo] = useState<{ sort_by?: string; sort_order?: string }>({})
  const [summary, setSummary] = useState({ total: 0, red: 0, yellow: 0, blue: 0, green: 0, overdue: 0, avgScore: 0 })

  const fetchOrders = useCallback(async (page = 1, pageSize = 50) => {
    setLoading(true)
    try {
      const params: Record<string, any> = { page, page_size: pageSize }
      if (sortInfo.sort_by) params.sort_by = sortInfo.sort_by
      if (sortInfo.sort_order) params.sort_order = sortInfo.sort_order
      if (filters.keyword) params.keyword = filters.keyword
      if (filters.risk_level.length > 0) params.risk_level = filters.risk_level.join(',')
      const res: any = await orderApi.listRiskPool(params)
      const items: OrderRow[] = res.data.items || []
      setOrders(items)
      setPagination({ current: res.data.page, pageSize: res.data.page_size, total: res.data.total })
      const todayStr = new Date().toISOString().slice(0, 10)
      const scored = items.filter(o => o.risk_score != null)
      const avgScore = scored.length > 0 ? Math.round(scored.reduce((s, o) => s + (o.risk_score || 0), 0) / scored.length) : 0
      // 使用后端返回的全局统计
      const stats = res.data.stats || {}
      setSummary({
        total: stats.total || res.data.total,
        red: stats.red_count || 0,
        yellow: stats.yellow_count || 0,
        blue: stats.blue_count || 0,
        green: stats.green_count || 0,
        overdue: stats.overdue_count || 0,
        avgScore,
      })
    } catch {
      message.error('获取风险池数据失败')
    } finally {
      setLoading(false)
    }
  }, [filters, sortInfo])

  useEffect(() => { fetchOrders() }, [fetchOrders])

  const handleTableChange = (pagination: any, tableFilters: any, sorter: any) => {
    let sortField = sorter.field
    const sortOrder = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : undefined
    if (sortField === 'risk_level') sortField = 'risk_score'
    const riskLevelFilter = tableFilters.risk_level?.length > 0 ? tableFilters.risk_level : []
    setSortInfo({ sort_by: sortField, sort_order: sortOrder })
    setFilters(f => ({ ...f, risk_level: riskLevelFilter }))
  }

  const handleAssess = async () => {
    setAssessing(true)
    try {
      const res: any = await riskApi.assess()
      message.success(`风险评估完成: 红${res.data.red_count}/黄${res.data.yellow_count}/蓝${res.data.blue_count || 0}/绿${res.data.green_count}`)
      fetchOrders()
    } catch {
      message.error('风险评估失败')
    } finally {
      setAssessing(false)
    }
  }

  const todayStr = new Date().toISOString().slice(0, 10)

  const getTopFactors = (factors: Record<string, number> | null) => {
    if (!factors) return []
    return Object.entries(factors)
      .filter(([, v]) => v > 0)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 2)
      .map(([k]) => FACTOR_LABELS[k] || k)
  }

  const columns: any[] = [
    {
      title: '风险', dataIndex: 'risk_level', key: 'risk_level', width: 70, fixed: 'left' as const, sorter: true,
      render: (level: string) => <RiskBadge level={level} />,
      filters: [
        { text: '高风险', value: 'red' },
        { text: '中风险', value: 'yellow' },
        { text: '低风险', value: 'blue' },
        { text: '正常', value: 'green' },
      ],
      filterMultiple: true,
    },
    {
      title: '风险评分', dataIndex: 'risk_score', key: 'risk_score', width: 120, fixed: 'left' as const, sorter: true,
      render: (score: number | null) => {
        if (score == null) return <span style={{ color: '#94a3b8' }}>未评估</span>
        const color = score >= 60 ? '#e11d48' : score >= 30 ? '#f59e0b' : score > 0 ? '#3b82f6' : '#10b981'
        return (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Progress percent={score} size="small" strokeColor={color} showInfo={false} style={{ width: 60, marginBottom: 0 }} />
            <span style={{ fontSize: 12, fontWeight: 600, color }}>{score}</span>
          </div>
        )
      },
    },
    {
      title: '主要风险因子', key: 'risk_factors_summary', width: 130,
      render: (_: any, r: OrderRow) => {
        const top = getTopFactors(r.risk_factors)
        if (top.length === 0) return <span style={{ color: '#94a3b8' }}>-</span>
        return <span style={{ fontSize: 12 }}>{top.join(' + ')}</span>
      },
    },
    {
      title: '销售部门', dataIndex: 'department', key: 'department', width: 80, sorter: true },
    {
      title: '客户等级', dataIndex: 'customer_grade', key: 'customer_grade', width: 70, sorter: true,
      render: (v: string) => v ? <Tag color={v === 'A' ? 'red' : v === 'B' ? 'orange' : 'blue'}>{v}</Tag> : '-',
    },
    {
      title: '客户', dataIndex: 'customer_code', key: 'customer_code', width: 90, ellipsis: true, sorter: true,
      render: (v: string) => {
        if (!v) return '-'
        const firstDashIndex = v.indexOf('-')
        const displayValue = firstDashIndex !== -1 ? v.substring(firstDashIndex + 1) : v
        return <Tooltip title={v}>{displayValue}</Tooltip>
      },
    },
    {
      title: '单号', dataIndex: 'order_no', key: 'order_no', width: 155, sorter: true,
      render: (v: string, r: OrderRow) => {
        if (!v) return '-'
        const lastDashIndex = v.lastIndexOf('-')
        const afterDash = lastDashIndex !== -1 ? v.substring(lastDashIndex + 1) : v
        const displayValue = afterDash.replace(/^0+/, '').padStart(3, '0')
        return (
          <Tooltip title={v}>
            <a onClick={() => navigate(`/orders/${v}`)} style={{ fontWeight: 600, fontSize: 'calc(0.75rem * var(--font-size-scale))' }}>{displayValue}</a>
          </Tooltip>
        )
      },
    },
    {
      title: '数量', dataIndex: 'order_qty', key: 'order_qty', width: 75, align: 'right' as const, sorter: true,
      render: (v: number) => v?.toLocaleString() || '-',
    },
    {
      title: '下单时间', dataIndex: 'order_date', key: 'order_date', width: 95, sorter: true,
      render: (v: string) => formatDate(v) || <span style={{ color: '#94a3b8' }}>-</span>,
    },
    {
      title: '合同交期', dataIndex: 'promised_date', key: 'promised_date', width: 100, sorter: true,
      render: (v: string, r: OrderRow) => {
        const overdue = v && v < todayStr && r.status !== 'closed'
        return <span style={{ color: overdue ? '#e11d48' : undefined, fontWeight: overdue ? 600 : undefined }}>{formatDate(v) || '-'}</span>
      },
    },
    {
      title: '出货计划', dataIndex: 'shipping_plan', key: 'shipping_plan', width: 100, sorter: true,
      render: (v: string) => v ? <span style={{ color: '#ca8a04' }}>{formatDate(v)}</span> : '-',
    },
    { title: '上线时间', dataIndex: 'planned_start_date', key: 'planned_start_date', width: 100, sorter: true,
      render: (v: string) => formatDate(v),
    },
    {
      title: '客检结果', dataIndex: 'inspection_result', key: 'inspection_result', width: 80,
      render: (v: string) => {
        if (!v) return '-'
        return <span style={{ color: v === 'OK' || v === '通过' ? '#16a34a' : '#e11d48', fontWeight: 600 }}>{v}</span>
      },
    },
    { title: '包装完成状况', dataIndex: 'packaging_status', key: 'packaging_status', width: 110, ellipsis: true },
    {
      title: '料齐套时间', dataIndex: 'material_ready_date', key: 'material_ready_date', width: 100, sorter: true,
      render: (v: string) => v ? <span style={{ color: '#16a34a' }}>{formatDate(v)}</span> : '-',
    },
    { title: '发货状态即时说明', dataIndex: 'shipping_status_desc', key: 'shipping_status_desc', width: 180, ellipsis: true, fixed: 'right' as const },
  ]

  const expandedRowRender = (r: OrderRow) => {
    const factors = r.risk_factors
    if (!factors) return <div style={{ padding: '8px 16px', color: '#94a3b8' }}>暂无评估数据</div>
    return (
      <div style={{ padding: '8px 16px' }}>
        <Row gutter={[12, 8]}>
          {Object.entries(FACTOR_LABELS).map(([key, label]) => {
            const val = factors[key] || 0
            const max = FACTOR_MAX[key] || 1
            const pct = Math.round(val / max * 100)
            const color = val >= max * 0.6 ? '#e11d48' : val >= max * 0.3 ? '#f59e0b' : '#10b981'
            return (
              <Col xs={12} sm={8} md={4} key={key}>
                <div style={{ fontSize: 'calc(0.6875rem * var(--font-size-scale))', color: '#64748b', marginBottom: 2 }}>{label}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Progress percent={pct} size="small" strokeColor={color} showInfo={false} style={{ width: 50, marginBottom: 0 }} />
                  <span style={{ fontSize: 12, fontWeight: 600, color }}>{val}/{max}</span>
                </div>
              </Col>
            )
          })}
          {r.risk_assessed_at && (
            <Col xs={24} style={{ marginTop: 4 }}>
              <span style={{ fontSize: 'calc(0.6875rem * var(--font-size-scale))', color: '#94a3b8' }}>评估时间: {formatDateTime(r.risk_assessed_at)}</span>
            </Col>
          )}
        </Row>
      </div>
    )
  }

  return (
    <div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '风险订单总数', value: summary.total, icon: <AlertOutlined />, color: '#6366f1' },
          { title: '高风险', value: summary.red, icon: <WarningOutlined />, color: '#e11d48' },
          { title: '中风险', value: summary.yellow, icon: <ExclamationCircleOutlined />, color: '#f59e0b' },
          { title: '低风险', value: summary.blue, icon: <ClockCircleOutlined />, color: '#3b82f6' },
          { title: '正常', value: summary.green, icon: <SafetyCertificateOutlined />, color: '#10b981' },
        ].map((card, i) => (
          <Col xs={12} sm={8} md={4} key={i}>
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
          <Col flex="auto" />
          <Col>
            <Button icon={<SafetyCertificateOutlined />} loading={assessing} onClick={handleAssess}
              style={{ background: '#8b5cf6', borderColor: '#8b5cf6', color: '#fff' }}>
              风险评估
            </Button>
          </Col>
          <Col>
            <Button icon={<ReloadOutlined />} onClick={() => fetchOrders()}>刷新</Button>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '2px 0 0' }}>
        <div className="table-modern">
          <Table columns={columns} dataSource={orders} rowKey="id" loading={loading} size="small"
            expandable={{ expandedRowRender, rowExpandable: (r: OrderRow) => !!r.risk_factors }}
            scroll={{ x: 2000, y: 'calc(100vh - 380px)' }} locale={{ emptyText: '暂无风险订单' }}
            onChange={handleTableChange}
            pagination={{ ...pagination, showSizeChanger: true, pageSizeOptions: ['20', '50', '100'],
              showTotal: (total) => `共 ${total} 条`, style: { padding: '0 16px' } }} />
        </div>
      </div>
    </div>
  )
}
