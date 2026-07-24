import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { Table, Card, Row, Col, Input, Select, Button, Tag, Progress, Tooltip, message, Switch, Space, Popover, Checkbox, Modal, Divider } from 'antd'
import {
  SearchOutlined, ReloadOutlined, FilterOutlined, CheckCircleOutlined,
  WarningOutlined, ExclamationCircleOutlined, PieChartOutlined, ShoppingOutlined,
  SettingOutlined, ArrowLeftOutlined, HistoryOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { materialApi } from '@/services/api'
import { useUiPreferencesStore } from '@/store/uiPreferences'

interface MaterialItem {
  material_code: string
  material_name: string | null
  product_code: string | null
  product_name: string | null
  material_property: number | null
  material_property_label: string | null
  material_type: string | null
  unit_name: string | null
  supplier_name: string | null
  order_qty: number | null
  mrp_qty: number | null
  po_qty: number | null
  stock_qty: number | null
  available_stock_qty: number | null
  transit_qty: number | null
  shortage_qty: number | null
  req_date: string | null
  po_no: string | null
  po_count: number
  received_qty: number | null
  eta: string | null
  first_eta: string | null
  latest_eta: string | null
  actual_arrival_date: string | null
  inspection_date: string | null
  status: string
  status_label: string | null
  is_stagnant: boolean
  stagnant_qty: number | null
  bill_type: number | null
  bill_type_label: string | null
  bom_demand_qty: number | null
}

interface KitSummary {
  order_no: string
  total_materials: number
  received_materials: number
  partial_received_materials: number
  not_ordered_materials: number
  overdue_materials: number
  kit_rate: number
  risk_level: string
  promised_date: string | null
}

interface CheckRecord {
  id: number
  order_no: string
  checked_by: string | null
  checked_at: string
  total_materials: number | null
  kit_rate: number | null
  note: string | null
}

const RISK_COLOR: Record<string, string> = { red: '#e11d48', yellow: '#f59e0b', green: '#16a34a' }
const RISK_LABEL: Record<string, string> = { red: '缺料严重', yellow: '部分齐套', green: '齐套' }

const MATERIAL_STATUS: Record<string, { label: string; color: string }> = {
  closed: { label: '已关闭', color: 'default' },
  not_ordered: { label: '未下单', color: 'volcano' },
  self_made_unlinked: { label: '自制未排产/未关联', color: 'blue' },
  partial_received: { label: '部分到', color: 'warning' },
  fully_received: { label: '已到齐', color: 'success' },
  overdue: { label: '逾期未到', color: 'error' },
  pending: { label: '待到料', color: 'cyan' },
  in_stock: { label: '有库存', color: 'green' },
}

const MATERIAL_PROPERTY_OPTIONS = [
  { value: 1, label: '外购' },
  { value: 2, label: '自制' },
  { value: 3, label: '委外加工' },
  { value: 5, label: '虚拟件' },
  { value: 6, label: '特征类' },
  { value: 7, label: '配置类' },
  { value: 8, label: '规划类' },
  { value: 9, label: '组装件' },
]
const MATERIAL_PROPERTY_MAP = Object.fromEntries(MATERIAL_PROPERTY_OPTIONS.map(item => [item.value, item.label]))
const MATERIAL_PROPERTY_COLOR: Record<number, string> = {
  1: 'blue', 2: 'purple', 3: 'cyan', 5: 'default', 6: 'geekblue', 7: 'magenta', 8: 'gold', 9: 'orange',
}

const COLUMN_KEYS = [
  'material_code', 'material_name', 'status', 'bom_demand_qty', 'stock_qty',
  'available_stock_qty', 'transit_qty', 'received_qty', 'shortage_qty',
  'supplier_name', 'po_no', 'mrp_qty', 'po_qty', 'eta', 'latest_eta',
  'actual_arrival_date', 'inspection_date', 'req_date',
] as const

const COLUMN_LABELS: Record<string, string> = {
  material_code: '物料代码', material_name: '物料名称', status: '状态',
  bom_demand_qty: 'BOM需求量', stock_qty: '即时库存', available_stock_qty: '可用库存',
  transit_qty: '在途量', received_qty: '已收料', shortage_qty: '缺口',
  supplier_name: '供应商', po_no: '采购单号', mrp_qty: 'MRP数量',
  po_qty: '采购下单量', eta: '最早ETA', latest_eta: '最晚ETA',
  actual_arrival_date: '实际到料', inspection_date: '检验日期', req_date: '需求日期',
}

const PAGE_KEY = 'inventory_check_columns'

export default function InventoryCheck() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const urlOrderNo = searchParams.get('orderNo') || ''

  const [searchText, setSearchText] = useState(urlOrderNo)
  const [activeOrderNo, setActiveOrderNo] = useState(urlOrderNo)
  const [materials, setMaterials] = useState<MaterialItem[]>([])
  const [loading, setLoading] = useState(false)
  const [kitSummary, setKitSummary] = useState<KitSummary | null>(null)
  const [onlyShortage, setOnlyShortage] = useState(true)
  const [statusFilter, setStatusFilter] = useState<string[]>([])
  const [materialSearch, setMaterialSearch] = useState('')
  const [history, setHistory] = useState<CheckRecord[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [checkModalOpen, setCheckModalOpen] = useState(false)
  const [checkNote, setCheckNote] = useState('')
  const [checkSubmitting, setCheckSubmitting] = useState(false)
  const [recentChecks, setRecentChecks] = useState<CheckRecord[]>([])
  const [recentLoading, setRecentLoading] = useState(false)

  const getColumnVisibility = useUiPreferencesStore(s => s.getColumnVisibility)
  const setColumnVisibility = useUiPreferencesStore(s => s.setColumnVisibility)
  const [columnKeys, setColumnKeys] = useState<string[]>(
    () => getColumnVisibility(PAGE_KEY, COLUMN_KEYS as unknown as string[])
  )

  useEffect(() => {
    if (urlOrderNo) {
      setSearchText(urlOrderNo)
      setActiveOrderNo(urlOrderNo)
    }
    loadRecentChecks()
  }, [urlOrderNo])

  const loadRecentChecks = async () => {
    setRecentLoading(true)
    try {
      const res: any = await materialApi.getRecentInventoryChecks({ page_size: 10 })
      setRecentChecks(res.data || [])
    } catch { /* silent */ } finally { setRecentLoading(false) }
  }

  const handleSearch = () => {
    const trimmed = searchText.trim()
    if (!trimmed) { message.warning('请输入订单号'); return }
    setActiveOrderNo(trimmed)
    setSearchParams({ orderNo: trimmed })
  }

  const loadMaterials = useCallback(async (orderNo: string) => {
    if (!orderNo) return
    setLoading(true)
    try {
      const res: any = await materialApi.getOrderMaterials(orderNo, {})
      setMaterials(res.data || [])
      const kitRes: any = await materialApi.getKitAnalysis({ order_no: orderNo, page_size: 1 })
      if (kitRes.data?.items?.length > 0) {
        setKitSummary(kitRes.data.items[0])
      } else {
        setKitSummary(null)
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '获取物料数据失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const loadHistory = useCallback(async (orderNo: string) => {
    setHistoryLoading(true)
    try {
      const res: any = await materialApi.getInventoryCheckHistory(orderNo)
      setHistory(res.data || [])
    } catch { /* silent */ } finally { setHistoryLoading(false) }
  }, [])

  useEffect(() => {
    if (activeOrderNo) {
      loadMaterials(activeOrderNo)
      loadHistory(activeOrderNo)
    }
  }, [activeOrderNo, loadMaterials, loadHistory])

  const handleCreateCheck = async () => {
    if (!activeOrderNo) return
    setCheckSubmitting(true)
    try {
      await materialApi.createInventoryCheck(activeOrderNo, { note: checkNote })
      message.success('盘点记录已保存')
      setCheckModalOpen(false)
      setCheckNote('')
      loadHistory(activeOrderNo)
      loadRecentChecks()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || e.message || '保存失败')
    } finally {
      setCheckSubmitting(false)
    }
  }

  const filteredMaterials = useMemo(() => {
    let result = [...materials]
    if (onlyShortage) {
      result = result.filter(m => m.status !== 'fully_received')
    }
    if (statusFilter.length > 0) {
      result = result.filter(m => statusFilter.includes(m.status))
    }
    if (materialSearch) {
      const kw = materialSearch.toLowerCase()
      result = result.filter(m =>
        m.material_code.toLowerCase().includes(kw) ||
        (m.material_name && m.material_name.toLowerCase().includes(kw))
      )
    }
    return result
  }, [materials, onlyShortage, statusFilter, materialSearch])

  const goBack = () => {
    setActiveOrderNo('')
    setMaterials([])
    setKitSummary(null)
    setSearchParams({})
    loadRecentChecks()
  }

  const gapQty = (row: MaterialItem) => {
    const bom = row.bom_demand_qty ?? row.order_qty ?? 0
    const available = row.available_stock_qty ?? 0
    const transit = row.transit_qty ?? 0
    const received = row.received_qty ?? 0
    const covered = available + transit + received
    const gap = Math.max(0, bom - covered)
    return gap > 0 ? gap : 0
  }

  const columns = useMemo(() => {
    const allCols: any[] = [
      {
        title: '物料代码', dataIndex: 'material_code', width: 140, fixed: 'left' as const, sorter: true,
        render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
      },
      {
        title: '物料名称', dataIndex: 'material_name', width: 160, ellipsis: true, sorter: true,
        render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
      },
      {
        title: '状态', dataIndex: 'status', width: 110, sorter: true,
        filters: Object.entries(MATERIAL_STATUS).map(([k, v]) => ({ text: v.label, value: k })),
        filterMultiple: true,
        render: (v: string, row: MaterialItem) => {
          const s = MATERIAL_STATUS[v] || { label: v, color: 'default' }
          return <Tag color={s.color}>{row.status_label || s.label}</Tag>
        },
      },
      {
        title: 'BOM需求量', dataIndex: 'bom_demand_qty', width: 100, sorter: true, align: 'right' as const,
        render: (v: number | null) => v != null
          ? <span style={{ color: '#e11d48', fontWeight: 600 }}>{v}</span>
          : <span style={{ color: '#cbd5e1' }}>-</span>,
      },
      {
        title: '即时库存', dataIndex: 'stock_qty', width: 90, sorter: true, align: 'right' as const,
        render: (v: number | null) => v != null
          ? <span style={{ color: '#0ea5e9' }}>{v}</span>
          : <span style={{ color: '#cbd5e1' }}>-</span>,
      },
      {
        title: '可用库存', dataIndex: 'available_stock_qty', width: 100, sorter: true, align: 'right' as const,
        render: (v: number | null, row: MaterialItem) => {
          if (v == null) return <span style={{ color: '#cbd5e1' }}>-</span>
          const bom = row.bom_demand_qty ?? row.order_qty ?? 0
          const met = bom > 0 && v >= bom
          return <span style={{ color: met ? '#16a34a' : '#0ea5e9', fontWeight: met ? 600 : 400 }}>{v}</span>
        },
      },
      {
        title: '在途量', dataIndex: 'transit_qty', width: 90, sorter: true, align: 'right' as const,
        render: (v: number | null) => v != null && v > 0
          ? <span style={{ color: '#f59e0b' }}>{v}</span>
          : <span style={{ color: '#cbd5e1' }}>0</span>,
      },
      {
        title: '已收料', dataIndex: 'received_qty', width: 80, sorter: true, align: 'right' as const,
        render: (v: number | null) => v != null ? <span style={{ color: '#16a34a' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>0</span>,
      },
      {
        title: '缺口', dataIndex: 'gap', width: 80, align: 'right' as const,
        render: (_: any, row: MaterialItem) => {
          const gap = gapQty(row)
          return gap > 0
            ? <span style={{ color: '#e11d48', fontWeight: 700 }}>{gap}</span>
            : <span style={{ color: '#16a34a' }}>0</span>
        },
      },
      {
        title: '供应商', dataIndex: 'supplier_name', width: 130, ellipsis: true, sorter: true,
        render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
      },
      {
        title: '采购单号', dataIndex: 'po_no', width: 140, ellipsis: true, sorter: true,
        render: (v: string | null) => {
          if (!v) return <span style={{ color: '#cbd5e1' }}>-</span>
          return <a onClick={() => navigate(`/purchase-plan?po_no=${v}`)} style={{ fontFamily: 'monospace' }}>{v}</a>
        },
      },
      {
        title: 'MRP数量', dataIndex: 'mrp_qty', width: 90, sorter: true, align: 'right' as const,
        render: (v: number | null) => v != null ? <span style={{ color: '#6366f1' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
      },
      {
        title: '采购下单量', dataIndex: 'po_qty', width: 90, sorter: true, align: 'right' as const,
        render: (v: number | null) => v != null ? <span style={{ color: '#0ea5e9' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
      },
      {
        title: '最早ETA', dataIndex: 'eta', width: 100, sorter: true,
        render: (v: string | null) => v ? <span style={{ color: '#16a34a' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
      },
      {
        title: '最晚ETA', dataIndex: 'latest_eta', width: 100, sorter: true,
        render: (v: string | null) => v ? <span style={{ color: '#e11d48' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
      },
      {
        title: '实际到料', dataIndex: 'actual_arrival_date', width: 110, sorter: true,
        render: (v: string | null) => v ? <span style={{ color: '#16a34a' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
      },
      {
        title: '检验日期', dataIndex: 'inspection_date', width: 100, sorter: true,
        render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
      },
      {
        title: '需求日期', dataIndex: 'req_date', width: 100, sorter: true,
        render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
      },
    ]
    return allCols
      .map((col: any) => ({ ...col, key: col.key || col.dataIndex }))
      .filter((col: any) => columnKeys.includes(col.key))
  }, [columnKeys, navigate])

  if (!activeOrderNo) {
    return (
      <div>
        <div style={{ marginBottom: 24 }}>
          <h2 style={{ margin: 0, fontSize: 'calc(1.25rem * var(--font-size-scale))', fontWeight: 700, color: '#1e293b' }}>
            订单物料盘点
          </h2>
          <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: 'calc(0.875rem * var(--font-size-scale))' }}>
            选择订单，查看所有物料库存、在途、缺口一览
          </p>
        </div>

        <Card size="small" className="card-modern" style={{ marginBottom: 24 }}>
          <Space size="middle">
            <Input.Search
              placeholder="输入订单号（支持 HJ* / HJY*）"
              value={searchText}
              onChange={e => setSearchText(e.target.value)}
              onSearch={handleSearch}
              enterButton="开始盘点"
              style={{ width: 360 }}
              size="large"
            />
          </Space>
        </Card>

        {recentChecks.length > 0 && (
          <div className="card-modern" style={{ padding: '16px 20px' }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 'calc(0.9375rem * var(--font-size-scale))', color: '#475569' }}>
              <HistoryOutlined style={{ marginRight: 8 }} />最近盘点记录
            </h3>
            <Table
              rowKey="id"
              dataSource={recentChecks}
              loading={recentLoading}
              size="small"
              pagination={false}
              columns={[
                {
                  title: '订单号', dataIndex: 'order_no', width: 180,
                  render: (v: string) => <a onClick={() => { setSearchText(v); setSearchParams({ orderNo: v }); setActiveOrderNo(v) }} style={{ fontFamily: 'monospace', fontWeight: 600 }}>{v}</a>,
                },
                { title: '盘点时间', dataIndex: 'checked_at', width: 170, render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm') },
                {
                  title: '齐套率', dataIndex: 'kit_rate', width: 120,
                  render: (v: number | null) => {
                    if (v == null) return '-'
                    const pct = Math.round(v * 100)
                    const level = v >= 1 ? 'green' : v >= 0.8 ? 'yellow' : 'red'
                    return <span style={{ color: RISK_COLOR[level], fontWeight: 600 }}>{pct}%</span>
                  },
                },
                { title: '物料数', dataIndex: 'total_materials', width: 80 },
                { title: '盘点人', dataIndex: 'checked_by', width: 100 },
                { title: '备注', dataIndex: 'note', ellipsis: true, render: (v: string | null) => v || '-' },
              ]}
            />
          </div>
        )}
      </div>
    )
  }

  const shortage = filteredMaterials.filter(m => m.status !== 'fully_received').length
  const fulFilled = (kitSummary?.received_materials ?? 0)
  const partial = (kitSummary?.partial_received_materials ?? 0)
  const notOrdered = (kitSummary?.not_ordered_materials ?? 0)
  const overdue = (kitSummary?.overdue_materials ?? 0)

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={goBack}>返回</Button>
        <div>
          <h2 style={{ margin: 0, fontSize: 'calc(1.25rem * var(--font-size-scale))', fontWeight: 700, color: '#1e293b' }}>
            订单物料盘点 — <span style={{ fontFamily: 'monospace' }}>{activeOrderNo}</span>
          </h2>
          <p style={{ margin: '2px 0 0', color: '#64748b', fontSize: 'calc(0.75rem * var(--font-size-scale))' }}>
            合同交期: {kitSummary?.promised_date || '-'}
          </p>
        </div>
      </div>

      <Row gutter={12} style={{ marginBottom: 16 }}>
        {[
          { title: '物料总数', value: kitSummary?.total_materials ?? materials.length, icon: <ShoppingOutlined />, color: '#6366f1' },
          { title: '已到齐', value: `${fulFilled} - ${kitSummary ? Math.round(kitSummary.kit_rate * 100) : 0}%`, icon: <CheckCircleOutlined />, color: '#16a34a' },
          { title: '部分到', value: partial, icon: <ExclamationCircleOutlined />, color: '#f59e0b' },
          { title: '未下单', value: notOrdered, icon: <WarningOutlined />, color: '#e11d48' },
          { title: '逾期', value: overdue, icon: <WarningOutlined />, color: '#e11d48' },
        ].map((card, i) => (
          <Col flex={1} key={i}>
            <Card size="small" className="card-modern" style={{ padding: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ width: 40, height: 40, borderRadius: 8, background: `${card.color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: card.color, fontSize: 'calc(1.125rem * var(--font-size-scale))' }}>
                  {card.icon}
                </div>
                <div>
                  <div style={{ fontSize: 'calc(1.25rem * var(--font-size-scale))', fontWeight: 700 }}>{card.value}</div>
                  <div style={{ fontSize: 'calc(0.6875rem * var(--font-size-scale))', color: '#64748b' }}>{card.title}</div>
                </div>
              </div>
            </Card>
          </Col>
        ))}
        <Col flex={1}>
          <Card size="small" className="card-modern" style={{ padding: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <Progress
                type="circle"
                percent={kitSummary ? Math.round(kitSummary.kit_rate * 100) : 0}
                size={40}
                strokeColor={kitSummary ? RISK_COLOR[kitSummary.risk_level] : '#94a3b8'}
                format={() => ''}
              />
              <div>
                <div style={{ fontWeight: 700, color: kitSummary ? RISK_COLOR[kitSummary.risk_level] : '#64748b' }}>
                  {kitSummary ? RISK_LABEL[kitSummary.risk_level] : '-'}
                </div>
                <div style={{ fontSize: 'calc(0.6875rem * var(--font-size-scale))', color: '#64748b' }}>风险等级</div>
              </div>
            </div>
          </Card>
        </Col>
      </Row>

      <div className="card-modern" style={{ padding: '12px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索物料代码/名称"
              value={materialSearch}
              onChange={e => setMaterialSearch(e.target.value)}
              style={{ width: 200 }}
              allowClear
            />
          </Col>
          <Col>
            <Select
              mode="multiple"
              placeholder="状态筛选"
              value={statusFilter}
              onChange={setStatusFilter}
              style={{ minWidth: 200 }}
              options={Object.entries(MATERIAL_STATUS).map(([k, v]) => ({ value: k, label: v.label }))}
              allowClear
            />
          </Col>
          <Col>
            <Switch
              checked={onlyShortage}
              onChange={setOnlyShortage}
              checkedChildren="仅看异常"
              unCheckedChildren="全部"
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Popover
              trigger="click" placement="bottomRight"
              title="选择显示列"
              content={
                <Checkbox.Group
                  value={columnKeys}
                  onChange={(checked) => {
                    const next = checked as string[]
                    if (next.length === 0) return
                    setColumnKeys(next)
                    setColumnVisibility(PAGE_KEY, next)
                  }}
                >
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, auto)', gap: '4px 12px', maxWidth: 520 }}>
                    {COLUMN_KEYS.map(key => (
                      <Checkbox key={key} value={key}>{COLUMN_LABELS[key]}</Checkbox>
                    ))}
                  </div>
                </Checkbox.Group>
              }
            >
              <Button size="small" icon={<SettingOutlined />}>列设置</Button>
            </Popover>
          </Col>
          <Col>
            <Button icon={<ReloadOutlined />} onClick={() => loadMaterials(activeOrderNo)}>刷新</Button>
          </Col>
          <Col>
            <Button type="primary" icon={<CheckCircleOutlined />} onClick={() => setCheckModalOpen(true)}>标记盘点完成</Button>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="material_code"
          dataSource={filteredMaterials}
          columns={columns}
          loading={loading}
          size="small"
          scroll={{ x: 1800, y: 500 }}
          pagination={{
            defaultPageSize: 20,
            showTotal: t => `共 ${t} 项物料，异常 ${shortage} 项`,
            showSizeChanger: true,
          }}
          onChange={(_pagination, filters: any, sorter: any) => {
            if (filters.status?.length) {
              setStatusFilter(filters.status as string[])
            }
          }}
        />
      </div>

      <Divider />

      <div className="card-modern" style={{ padding: '16px 20px' }}>
        <h3 style={{ margin: '0 0 12px', fontSize: 'calc(0.9375rem * var(--font-size-scale))', color: '#475569' }}>
          <HistoryOutlined style={{ marginRight: 8 }} />此订单盘点历史
        </h3>
        <Table
          rowKey="id"
          dataSource={history}
          loading={historyLoading}
          size="small"
          pagination={false}
          columns={[
            { title: '盘点时间', dataIndex: 'checked_at', width: 170, render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm:ss') },
            {
              title: '齐套率', dataIndex: 'kit_rate', width: 100,
              render: (v: number | null) => {
                if (v == null) return '-'
                const pct = Math.round(v * 100)
                return <span style={{ color: v >= 1 ? '#16a34a' : v >= 0.8 ? '#f59e0b' : '#e11d48', fontWeight: 600 }}>{pct}%</span>
              },
            },
            { title: '物料数', dataIndex: 'total_materials', width: 80 },
            { title: '盘点人', dataIndex: 'checked_by', width: 100 },
            {
              title: '备注', dataIndex: 'note', ellipsis: true,
              render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
            },
          ]}
        />
      </div>

      <Modal
        title="确认盘点完成"
        open={checkModalOpen}
        onOk={handleCreateCheck}
        onCancel={() => { setCheckModalOpen(false); setCheckNote('') }}
        confirmLoading={checkSubmitting}
        okText="确认保存"
        cancelText="取消"
      >
        <div style={{ marginBottom: 8 }}>
          将为订单 <strong>{activeOrderNo}</strong> 创建一条盘点记录，
          包含当前 {materials.length} 项物料的库存状态快照。
        </div>
        <Input.TextArea
          placeholder="盘点备注（可选）"
          value={checkNote}
          onChange={e => setCheckNote(e.target.value)}
          rows={3}
        />
      </Modal>
    </div>
  )
}
