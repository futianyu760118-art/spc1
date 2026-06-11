import { useEffect, useState, useCallback } from 'react'
import { Table, Tag, Input, Select, Button, Space, message, Row, Col, Card } from 'antd'
import {
  SearchOutlined, ReloadOutlined, ShopOutlined,
  WarningOutlined, ExclamationCircleOutlined,
  ClockCircleOutlined, FieldTimeOutlined,
} from '@ant-design/icons'
import { materialApi } from '../../../services/api'
import { useAuthStore } from '../../../store/auth'

interface OrderItem {
  po_no: string | null
  material_code: string
  material_name: string | null
  order_no: string | null
  eta: string | null
  actual_arrival_date: string | null
  inspection_date: string | null
  po_status: string | null
  po_qty: number | null
  received_qty: number | null
}

interface SupplierRiskRow {
  supplier_name: string
  total_orders: number
  delayed_count: number
  issue_count: number
  avg_delay_days: number
  risk_level: string
  orders: OrderItem[]
}

const RISK_COLOR: Record<string, string> = { red: '#e11d48', yellow: '#f59e0b', green: '#16a34a' }
const RISK_LABEL: Record<string, string> = { red: '高风险', yellow: '中风险', green: '低风险' }

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  inspected: { label: '已检验', color: 'success' },
  arrived: { label: '已到料', color: 'processing' },
  overdue: { label: '逾期未到', color: 'error' },
  pending: { label: '待到料', color: 'default' },
}

export default function SupplierRisk() {
  const isSupplierUser = useAuthStore((s) => s.isSupplierUser)
  const supplierReadOnly = isSupplierUser()
  const [data, setData] = useState<SupplierRiskRow[]>([])
  const [loading, setLoading] = useState(false)
  const [supplier, setSupplier] = useState('')
  const [riskFilter, setRiskFilter] = useState('')
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const [sortBy, setSortBy] = useState<string>('')
  const [sortOrder, setSortOrder] = useState<string>('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await materialApi.getSupplierRisk({
        ...(supplier ? { supplier } : {}),
        ...(riskFilter ? { risk_level: riskFilter } : {}),
        ...(sortBy ? { sort_by: sortBy, sort_order: sortOrder || 'asc' } : {}),
      })
      setData(res.data)
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [supplier, riskFilter, sortBy, sortOrder])

  useEffect(() => { load() }, [load])

  const redCount = data.filter(d => d.risk_level === 'red').length
  const yellowCount = data.filter(d => d.risk_level === 'yellow').length
  const totalDelayed = data.reduce((s, d) => s + d.delayed_count, 0)
  const avgDelay = data.length
    ? (data.reduce((s, d) => s + d.avg_delay_days, 0) / data.length).toFixed(1)
    : '0'

  const orderColumns = [
    {
      title: '物料代码', dataIndex: 'material_code', width: 140, ellipsis: true,
      render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    { title: '物料名称', dataIndex: 'material_name', width: 150, ellipsis: true },
    { title: '订单号', dataIndex: 'order_no', width: 100, ellipsis: true },
    { title: 'PO号', dataIndex: 'po_no', width: 120, ellipsis: true },
    {
      title: '交货日期', dataIndex: 'eta', width: 100,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '到料时间', dataIndex: 'actual_arrival_date', width: 100,
      render: (v: string | null) => v ? <span style={{ color: '#16a34a' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '检验日期', dataIndex: 'inspection_date', width: 100,
      render: (v: string | null) => v ? <span style={{ color: '#6366f1' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '数量', dataIndex: 'po_qty', width: 70,
      render: (v: number | null) => v ?? '-',
    },
    {
      title: '收料量', dataIndex: 'received_qty', width: 70,
      render: (v: number | null) => v != null ? <span style={{ color: '#16a34a' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>0</span>,
    },
    {
      title: '状态', dataIndex: 'po_status', width: 90,
      render: (v: string | null) => {
        if (!v) return <span style={{ color: '#cbd5e1' }}>-</span>
        const s = STATUS_MAP[v] || { label: v, color: 'default' }
        return <Tag color={s.color}>{s.label}</Tag>
      },
    },
  ]

  const columns = [
    {
      title: '供应商', dataIndex: 'supplier_name', width: 180, ellipsis: true, sorter: true,
      render: (v: string) => <strong>{v}</strong>,
    },
    {
      title: '涉及订单数', dataIndex: 'total_orders', width: 100, sorter: true,
    },
    {
      title: '延期次数', dataIndex: 'delayed_count', width: 90, sorter: true,
      render: (v: number) => v > 0
        ? <span style={{ color: '#e11d48', fontWeight: 600 }}>{v}</span>
        : <span style={{ color: '#94a3b8' }}>0</span>,
    },
    {
      title: '平均延期(天)', dataIndex: 'avg_delay_days', width: 110, sorter: true,
      render: (v: number) => {
        if (!v) return <span style={{ color: '#94a3b8' }}>0</span>
        const color = v >= 7 ? '#e11d48' : v >= 3 ? '#f59e0b' : '#16a34a'
        return <span style={{ color, fontWeight: 600 }}>{v}</span>
      },
    },
    {
      title: '质量问题数', dataIndex: 'issue_count', width: 100, sorter: true,
      render: (v: number) => v > 0
        ? <span style={{ color: '#f59e0b', fontWeight: 600 }}>{v}</span>
        : <span style={{ color: '#94a3b8' }}>0</span>,
    },
    {
      title: '风险等级', dataIndex: 'risk_level', width: 100, fixed: 'right' as const, sorter: true,
      render: (v: string) => (
        <Tag
          color={v === 'red' ? 'error' : v === 'yellow' ? 'warning' : 'success'}
          style={{ fontWeight: 600 }}
        >
          {RISK_LABEL[v] || v}
        </Tag>
      ),
      filters: [
        { text: '高风险', value: 'red' },
        { text: '中风险', value: 'yellow' },
        { text: '低风险', value: 'green' },
      ],
      onFilter: (value: any, record: SupplierRiskRow) => record.risk_level === value,
    },
  ]

  return (
    <div>
      {/* 统计卡 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '供应商总数', value: data.length, icon: <ShopOutlined />, color: '#6366f1' },
          { title: '高风险供应商', value: redCount, icon: <WarningOutlined />, color: '#e11d48' },
          { title: '中风险供应商', value: yellowCount, icon: <ExclamationCircleOutlined />, color: '#f59e0b' },
          { title: '延期总次数', value: totalDelayed, icon: <ClockCircleOutlined />, color: '#e11d48' },
          { title: '平均延期(天)', value: avgDelay, icon: <FieldTimeOutlined />, color: '#f59e0b' },
        ].map((card, i) => (
          <Col flex={1} key={i}>
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

      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          {!supplierReadOnly && <Col>
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索供应商"
              value={supplier}
              onChange={e => setSupplier(e.target.value)}
              style={{ width: 200 }}
              allowClear
            />
          </Col>}
          <Col>
            <Select
              placeholder="风险等级"
              value={riskFilter || undefined}
              onChange={v => setRiskFilter(v || '')}
              allowClear
              style={{ width: 120 }}
            >
              <Select.Option value="red">高风险</Select.Option>
              <Select.Option value="yellow">中风险</Select.Option>
              <Select.Option value="green">低风险</Select.Option>
            </Select>
          </Col>
          <Col flex="auto" />
          <Col>
            <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="supplier_name"
          dataSource={data}
          columns={columns}
          loading={loading}
          size="small"
          scroll={{ x: 700 }}
          pagination={{ showTotal: t => `共 ${t} 家供应商`, showSizeChanger: true }}
          onChange={(_pagination, _tableFilters, sorter: any) => {
            const sortField = sorter.field as string | undefined
            const sortDir = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : ''
            setSortBy(sortField || '')
            setSortOrder(sortDir)
          }}
          expandable={{
            expandedRowKeys: expandedKeys,
            onExpandedRowsChange: (keys) => setExpandedKeys(keys as string[]),
            expandedRowRender: (row: SupplierRiskRow) => (
              <div style={{ padding: '8px 0' }}>
                <Table
                  rowKey="po_no"
                  dataSource={row.orders}
                  columns={orderColumns}
                  pagination={false}
                  size="small"
                  scroll={{ x: 1100 }}
                />
              </div>
            ),
          }}
          rowClassName={(row) => {
            if (row.risk_level === 'red') return 'ant-table-row-danger'
            return ''
          }}
        />
      </div>
    </div>
  )
}
