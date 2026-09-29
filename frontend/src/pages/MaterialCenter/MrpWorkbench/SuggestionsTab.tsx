import { useCallback, useEffect, useMemo, useState } from 'react'
import type { CSSProperties, Key, ReactNode } from 'react'
import {
  Alert, Button, Col, Input, Popconfirm, Row, Select, Space, Spin, Table, Tag, Tooltip, Typography, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DownloadOutlined, ReloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { Link } from 'react-router-dom'
import api from '@/services/api'
import { useAuthStore } from '@/store/auth'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

interface SuggestionStats {
  by_status: Record<string, number>
  by_type: Record<string, number>
  substitute_count?: number
}

interface PageData<T> {
  total: number
  page: number
  page_size: number
  items: T[]
  stats?: SuggestionStats
}

interface PeggingItem {
  sale_order_no: string
  line_no: string | null
  qty: number
}

interface RunOption {
  id: number
  run_no: string
  status: string
}

interface SuggestionRow {
  id: number
  run_id: number
  material_id: number
  material_code: string
  material_name: string | null
  bill_type: number
  suggest_qty: number
  need_date: string
  action_date: string | null
  suggested_supplier_id: number | null
  source: string
  status: string
  is_substitute?: boolean | null
  reviewed_by: string | null
  reviewed_at: string | null
  converted_target_type?: string | null
  converted_target_id?: number | null
  pegging: PeggingItem[] | null
}

interface BucketRow {
  bucket_date: string
  opening_qty: number
  gross_demand_qty: number
  supply_po_qty: number
  supply_task_qty: number
  supply_subcontract_qty: number
  supply_transfer_qty: number
  supply_requisition_qty: number
  substitute_in_qty: number
  substitute_out_qty: number
  safety_stock_qty: number
  closing_qty: number
  net_demand_qty: number
}

type TypeFilter = 'all' | 'buy' | 'make' | 'out' | 'sub'

const BILL_TYPE_MAP: Record<number, { label: string; color: string }> = {
  11010: { label: '外购', color: 'blue' },
  11011: { label: '自制', color: 'purple' },
  11012: { label: '委外', color: 'orange' },
}

const BILL_TYPE_BY_FILTER: Record<Exclude<TypeFilter, 'all'>, { bill_type?: number; is_substitute?: boolean }> = {
  buy: { bill_type: 11010, is_substitute: false },
  make: { bill_type: 11011 },
  out: { bill_type: 11012 },
  sub: { is_substitute: true },
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: '待审核', color: 'processing' },
  approved: { label: '已通过', color: 'success' },
  rejected: { label: '已驳回', color: 'error' },
  converted: { label: '已转单', color: 'default' },
}

const SOURCE_MAP: Record<string, { label: string; color: string }> = {
  demand: { label: '需求缺口', color: 'blue' },
  safety_stock: { label: '安全库存补货', color: 'gold' },
}

interface SupplyAggRow {
  key: string
  label: string
  color: string
  qty: number
}

const SUPPLY_DEFS: { key: string; label: string; color: string; pick: (b: BucketRow) => number }[] = [
  { key: 'po', label: '采购在途', color: 'cyan', pick: (b) => b.supply_po_qty },
  { key: 'task', label: '生产任务', color: 'processing', pick: (b) => b.supply_task_qty },
  { key: 'subcontract', label: '委外', color: 'purple', pick: (b) => b.supply_subcontract_qty },
  { key: 'transfer', label: '调拨', color: 'gold', pick: (b) => b.supply_transfer_qty },
  { key: 'requisition', label: '采购申请', color: 'blue', pick: (b) => b.supply_requisition_qty },
  { key: 'substitute-in', label: '替代调入', color: 'magenta', pick: (b) => b.substitute_in_qty },
  { key: 'substitute-out', label: '替代调出', color: 'orange', pick: (b) => b.substitute_out_qty },
]

const SUPPLY_AGG_COLUMNS: ColumnsType<SupplyAggRow> = [
  {
    title: '类型', dataIndex: 'label',
    render: (v: string, row) => <Tag color={row.color}>{v}</Tag>,
  },
  {
    title: '合计', dataIndex: 'qty', width: 110, align: 'right',
    render: (v: number) => (v > 0
      ? <b className="sc-mono">{fmtQty(v)}</b>
      : <span className="sc-sub">0</span>),
  },
]

const PEGGING_COLUMNS: ColumnsType<PeggingItem> = [
  {
    title: '订单', dataIndex: 'sale_order_no',
    render: (v: string) => <span className="sc-mono" style={{ fontSize: 12 }}>{v || '—'}</span>,
  },
  { title: '行', dataIndex: 'line_no', width: 64, render: (v: string | null) => v || '—' },
  {
    title: '数量', dataIndex: 'qty', width: 96, align: 'right',
    render: (v: number) => <span className="sc-mono">{fmtQty(v)}</span>,
  },
]

const PANEL_STYLE: CSSProperties = {
  border: '1px solid #e2e8f0',
  borderRadius: 9,
  background: '#fff',
  padding: '10px 12px',
  height: '100%',
}

const DRILL_LABEL_STYLE: CSSProperties = { color: '#0f172a', marginRight: 6, fontWeight: 600 }

function fmtQty(v: number | null | undefined): string {
  if (v == null) return '—'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

function duePill(dateStr: string) {
  const days = dayjs(dateStr).startOf('day').diff(dayjs().startOf('day'), 'day')
  const level = days <= 3 ? 'urgent' : days <= 7 ? 'soon' : 'ok'
  const text = days < 0 ? `逾期${-days}天` : days === 0 ? '今天' : `${days}天`
  return <span className={`ac-due-pill ${level}`} title={`需求日 ${dateStr}`}>{dateStr.slice(5)} · {text}</span>
}

function isActionUrgent(dateStr: string | null): boolean {
  if (!dateStr) return false
  return dayjs(dateStr).startOf('day').diff(dayjs().startOf('day'), 'day') < 0
}

function SectionHeader({ n, title }: { n: string; title: string }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 700, marginBottom: 8 }}>
      <span style={{
        width: 16, height: 16, borderRadius: '50%', background: '#eef0fe', color: '#4c4dc2',
        fontSize: 10.5, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>{n}</span>
      {title}
    </div>
  )
}

function WhyPanel({ row }: { row: SuggestionRow }) {
  const pegging = row.pegging || []
  return (
    <>
      <SectionHeader n="1" title="为什么缺" />
      {pegging.length === 0 ? (
        <div className="sc-sub" style={{ lineHeight: 1.8 }}>
          {row.source === 'safety_stock' ? '来源：安全库存水位补货' : '无关联销售订单明细'}
        </div>
      ) : (
        <>
          <Table<PeggingItem>
            rowKey={(_, index) => index ?? 0}
            dataSource={pegging}
            columns={PEGGING_COLUMNS}
            size="small"
            pagination={false}
          />
          <div className="sc-sub" style={{ marginTop: 6 }}>需求由 {pegging.length} 条订单行产生</div>
        </>
      )}
    </>
  )
}

function SupplyPanel({ row }: { row: SuggestionRow }) {
  const [buckets, setBuckets] = useState<BucketRow[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoaded(false)
    const loadBuckets = async () => {
      try {
        const res = (await api.get(`/mrp/runs/${row.run_id}/buckets`, {
          params: { material_code: row.material_code },
          skipErrorToast: true,
        })) as unknown as ApiResponse<BucketRow[]>
        if (!cancelled) setBuckets(res.data || [])
      } catch {
        if (!cancelled) setBuckets([])
      } finally {
        if (!cancelled) setLoaded(true)
      }
    }
    loadBuckets()
    return () => { cancelled = true }
  }, [row.run_id, row.material_code])

  const rows = useMemo<SupplyAggRow[]>(() => {
    const sum = (pick: (b: BucketRow) => number) =>
      buckets.reduce((acc, b) => acc + (Number(pick(b)) || 0), 0)
    const max = (pick: (b: BucketRow) => number) =>
      buckets.reduce((acc, b) => Math.max(acc, Number(pick(b)) || 0), 0)
    return [
      ...SUPPLY_DEFS.map((def) => ({ key: def.key, label: def.label, color: def.color, qty: sum(def.pick) })),
      { key: 'safety-stock', label: '安全库存水位', color: 'red', qty: max((b) => b.safety_stock_qty) },
    ]
  }, [buckets])

  return (
    <>
      <SectionHeader n="2" title="有什么可用" />
      {!loaded ? (
        <Spin size="small" />
      ) : buckets.length === 0 ? (
        <div className="sc-sub">本物料本批次无供需活动</div>
      ) : (
        <>
          <Table<SupplyAggRow>
            rowKey="key"
            dataSource={rows}
            columns={SUPPLY_AGG_COLUMNS}
            size="small"
            pagination={false}
          />
          <div className="sc-sub" style={{ marginTop: 6 }}>跨 {buckets.length} 个日桶汇总，安全库存取水位值</div>
        </>
      )}
    </>
  )
}

function PlanPanel({ row }: { row: SuggestionRow }) {
  const typeInfo = row.is_substitute
    ? { label: '替代', color: 'magenta' }
    : (BILL_TYPE_MAP[row.bill_type] || { label: String(row.bill_type), color: 'default' })
  const sourceInfo = SOURCE_MAP[row.source] || { label: row.source, color: 'default' }
  const leadDays = row.action_date ? dayjs(row.need_date).diff(dayjs(row.action_date), 'day') : null
  const urgent = isActionUrgent(row.action_date)
  return (
    <>
      <SectionHeader n="3" title="怎么补" />
      <div style={{ border: '1px solid #c7d2fe', borderRadius: 8, background: '#fcfcff', padding: '10px 12px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
          <Tag color={typeInfo.color}>{typeInfo.label}</Tag>
          <span style={{ fontSize: 12.5 }}>
            建议 <b className="sc-mono" style={{ color: '#dc2626', fontSize: 16 }}>{fmtQty(row.suggest_qty)}</b> 件
          </span>
        </div>
        <div style={{ fontSize: 12, color: '#475569', lineHeight: 1.9 }}>
          <div><b style={DRILL_LABEL_STYLE}>需求日</b><span className="sc-mono">{row.need_date}</span></div>
          <div>
            <b style={DRILL_LABEL_STYLE}>下单日</b>
            <span className="sc-mono" style={urgent ? { color: '#dc2626', fontWeight: 700 } : undefined}>
              {row.action_date || '—'}
            </span>
            {urgent && <span style={{ color: '#dc2626' }}> · 紧急</span>}
          </div>
          <div><b style={DRILL_LABEL_STYLE}>提前期</b>{leadDays != null ? `${leadDays} 天` : '—'}</div>
          <div>
            <b style={DRILL_LABEL_STYLE}>供应商</b>
            {row.suggested_supplier_id != null ? <span className="sc-mono">#{row.suggested_supplier_id}</span> : '—'}
          </div>
          <div><b style={DRILL_LABEL_STYLE}>来源</b>{sourceInfo.label}</div>
        </div>
        <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 8, borderTop: '1px dashed #e2e8f0', paddingTop: 6 }}>
          数量已按最小起订量/批量策略取整
        </div>
      </div>
    </>
  )
}

function SuggestionDrill({ row }: { row: SuggestionRow }) {
  return (
    <div style={{ background: '#fbfcfe', borderTop: '1px dashed #e2e8f0', padding: '12px 16px' }}>
      <Row gutter={[12, 12]}>
        <Col xs={24} xl={8}><div style={PANEL_STYLE}><WhyPanel row={row} /></div></Col>
        <Col xs={24} xl={9}><div style={PANEL_STYLE}><SupplyPanel row={row} /></div></Col>
        <Col xs={24} xl={7}><div style={PANEL_STYLE}><PlanPanel row={row} /></div></Col>
      </Row>
    </div>
  )
}

export default function SuggestionsTab({ runId }: { runId: number | null }) {
  const hasPermission = useAuthStore((s) => s.hasPermission) as (resource: string, action: string) => boolean
  const canReview = hasPermission('materials.mrp', 'review')
  const canConvert = hasPermission('materials.mrp', 'convert')

  const [runOptions, setRunOptions] = useState<RunOption[]>([])
  const [selectedRunId, setSelectedRunId] = useState<number | null>(runId)
  const [status, setStatus] = useState<string>('')
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')
  const [keyword, setKeyword] = useState('')
  const [data, setData] = useState<SuggestionRow[]>([])
  const [stats, setStats] = useState<SuggestionStats | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])
  const [selectedRows, setSelectedRows] = useState<SuggestionRow[]>([])
  const [reviewing, setReviewing] = useState(false)
  const [converting, setConverting] = useState(false)

  useEffect(() => {
    if (runId != null) setSelectedRunId(runId)
  }, [runId])

  useEffect(() => {
    const loadRuns = async () => {
      try {
        const res = (await api.get('/mrp/runs', { params: { page: 1, page_size: 100 } })) as unknown as ApiResponse<PageData<RunOption>>
        const items = res.data.items || []
        setRunOptions(items)
        const firstSuccess = items.find((r) => r.status === 'success')
        setSelectedRunId((prev) => prev ?? (firstSuccess ? firstSuccess.id : null))
      } catch {
        // 全局拦截器已提示
      }
    }
    loadRuns()
  }, [])

  const load = useCallback(async () => {
    if (selectedRunId == null) return
    setLoading(true)
    try {
      const filterParams = typeFilter === 'all' ? {} : BILL_TYPE_BY_FILTER[typeFilter]
      const res = (await api.get('/mrp/suggestions', {
        params: {
          run_id: selectedRunId,
          ...(status ? { status } : {}),
          ...filterParams,
          ...(keyword ? { keyword } : {}),
          page,
          page_size: pageSize,
        },
      })) as unknown as ApiResponse<PageData<SuggestionRow>>
      setData(res.data.items || [])
      setStats(res.data.stats || null)
      setTotal(res.data.total || 0)
    } catch {
      // 全局拦截器已提示
    } finally {
      setLoading(false)
    }
  }, [selectedRunId, status, typeFilter, keyword, page, pageSize])

  useEffect(() => { load() }, [load])

  const runReview = async (ids: number[], action: 'approve' | 'reject', clearSelection: boolean) => {
    setReviewing(true)
    try {
      const res = (await api.post('/mrp/suggestions/batch-review', {
        suggestion_ids: ids,
        action,
      })) as unknown as ApiResponse<{ updated: number; status: string }>
      message.success(`已${action === 'approve' ? '通过' : '驳回'} ${res.data.updated} 条建议`)
      if (clearSelection) {
        setSelectedRowKeys([])
        setSelectedRows([])
      }
      await load()
    } catch {
      // 全局拦截器已提示
    } finally {
      setReviewing(false)
    }
  }

  const batchReview = (action: 'approve' | 'reject') => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先勾选建议')
      return
    }
    runReview(selectedRowKeys.map(Number), action, true)
  }

  const canSelectRow = (row: SuggestionRow) =>
    (canReview && row.status === 'pending') ||
    (canConvert && row.bill_type === 11010 && row.status === 'approved')

  const convertibleSelection =
    selectedRows.length > 0 && selectedRows.every((r) => r.bill_type === 11010 && r.status === 'approved')

  const convertHint = selectedRows.length === 0
    ? '请先勾选建议'
    : '仅「已通过」的「外购」建议可转为采购申请单'

  const runConvert = async (ids: number[], clearSelection: boolean) => {
    setConverting(true)
    try {
      const res = (await api.post(
        '/mrp/suggestions/convert',
        { suggestion_ids: ids },
        { skipErrorToast: true },
      )) as unknown as ApiResponse<{ requisition_id: number; req_no: string; line_count: number }>
      message.success(`已生成 ${res.data.req_no}`)
      if (clearSelection) {
        setSelectedRowKeys([])
        setSelectedRows([])
      }
      await load()
    } catch (err) {
      const response = (err as { response?: { status?: number; data?: { detail?: string } } })?.response
      if (response?.status === 409) {
        message.error('状态已变化，请刷新')
      } else {
        message.error(response?.data?.detail || (err as Error)?.message || '转换为采购申请单失败')
      }
    } finally {
      setConverting(false)
    }
  }

  const batchConvert = () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先勾选建议')
      return
    }
    runConvert(selectedRowKeys.map(Number), true)
  }

  const statusCounts = stats?.by_status || {}
  const typeCounts = stats?.by_type || {}
  const substituteCount = Number(stats?.substitute_count) || 0
  const statusTotal = Object.values(statusCounts).reduce((acc, n) => acc + (Number(n) || 0), 0)

  const statusChips: { key: string; label: string; count: number }[] = [
    { key: '', label: '全部', count: statusTotal },
    { key: 'pending', label: '待审核', count: statusCounts.pending || 0 },
    { key: 'approved', label: '已通过', count: statusCounts.approved || 0 },
    { key: 'converted', label: '已转单', count: statusCounts.converted || 0 },
  ]
  if (statusCounts.rejected) {
    statusChips.push({ key: 'rejected', label: '已驳回', count: statusCounts.rejected })
  }

  const typeChips: { key: TypeFilter; label: string; count: number }[] = [
    { key: 'buy', label: '外购', count: Math.max(0, (Number(typeCounts['11010']) || 0) - substituteCount) },
    { key: 'make', label: '自制', count: Number(typeCounts['11011']) || 0 },
    { key: 'out', label: '委外', count: Number(typeCounts['11012']) || 0 },
    { key: 'sub', label: '替代', count: substituteCount },
  ]

  const runNo = runOptions.find((r) => r.id === selectedRunId)?.run_no

  const columns: ColumnsType<SuggestionRow> = [
    {
      title: '物料', dataIndex: 'material_code', width: 260,
      render: (_: string, row: SuggestionRow) => (
        <div>
          <div className="sc-mono" style={{ fontSize: 12.5, fontWeight: 600 }}>{row.material_code}</div>
          <div className="sc-sub">{row.material_name || '—'}</div>
        </div>
      ),
    },
    {
      title: <Tooltip title="外购=需要买；自制=自己做；委外=发外加工；替代=用替代料供货">类型</Tooltip>,
      dataIndex: 'bill_type', width: 80,
      render: (v: number, row: SuggestionRow) => {
        if (row.is_substitute) return <Tag color="magenta">替代</Tag>
        const m = BILL_TYPE_MAP[v] || { label: String(v), color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: <Tooltip title="缺口数量，已按最小起订量与批量策略取整">缺口数量</Tooltip>,
      dataIndex: 'suggest_qty', width: 110, align: 'right',
      render: (v: number) => <b className="sc-mono" style={{ color: '#dc2626' }}>{fmtQty(v)}</b>,
    },
    {
      title: '需求日', dataIndex: 'need_date', width: 130,
      render: (v: string) => duePill(v),
    },
    {
      title: <Tooltip title="按提前期倒推：需求日 − 提前期＝该动手的日期，早于今天的需加急">下单日</Tooltip>,
      dataIndex: 'action_date', width: 130,
      render: (v: string | null) => {
        if (!v) return <span className="sc-sub">—</span>
        const urgent = isActionUrgent(v)
        return (
          <span className="sc-mono" style={urgent ? { color: '#dc2626', fontWeight: 700 } : undefined}>
            {v}{urgent ? ' · 紧急' : ''}
          </span>
        )
      },
    },
    {
      title: '供应商', dataIndex: 'suggested_supplier_id', width: 110,
      render: (v: number | null) => (v != null
        ? <span className="sc-mono">#{v}</span>
        : <span className="sc-sub">—</span>),
    },
    {
      title: '来源', dataIndex: 'source', width: 120,
      render: (v: string) => {
        const m = SOURCE_MAP[v] || { label: v, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (v: string) => {
        const m = STATUS_MAP[v] || { label: v, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '操作', key: 'action', width: 150, fixed: 'right',
      render: (_: unknown, row: SuggestionRow) => {
        const actions: ReactNode[] = []
        if (row.status === 'pending' && canReview) {
          actions.push(<a key="approve" onClick={() => runReview([row.id], 'approve', false)}>通过</a>)
          actions.push(<a key="reject" onClick={() => runReview([row.id], 'reject', false)}>驳回</a>)
        } else if (row.status === 'approved' && canConvert && row.bill_type === 11010) {
          actions.push(<a key="convert" onClick={() => runConvert([row.id], false)}>转申请单</a>)
        } else if (row.status === 'converted' && row.converted_target_id != null) {
          actions.push(
            <Link key="view" to={`/purchase-requisitions/${row.converted_target_id}`}>查看申请单</Link>,
          )
        }
        return actions.length ? <Space size={10}>{actions}</Space> : <span className="sc-sub">—</span>
      },
    },
  ]

  const chipSeparator = <span style={{ width: 1, height: 18, background: '#e2e8f0', margin: '0 3px' }} />

  return (
    <div>
      <Alert
        type="info"
        showIcon
        message={<><b>怎么看：</b>每一行就是一条缺口：点开看『为什么缺 / 有什么可用 / 怎么补』三段依据。建议需先审核通过，外购可转采购申请单。</>}
        style={{ marginBottom: 12 }}
      />

      <div className="sc-card" style={{ padding: '14px 16px', marginBottom: 12 }}>
        <Row gutter={[12, 12]} align="middle">
          <Col>
            <Input.Search
              placeholder="搜索物料编码/名称"
              style={{ width: 220 }}
              allowClear
              onSearch={(v) => { setKeyword(v.trim()); setPage(1) }}
            />
          </Col>
          <Col>
            <Select
              placeholder="运算批次"
              value={selectedRunId ?? undefined}
              onChange={(v) => { setSelectedRunId(v ?? null); setPage(1) }}
              style={{ width: 260 }}
              options={runOptions.map((r) => ({
                value: r.id,
                label: `${r.run_no}${r.status === 'success' ? '' : `（${r.status}）`}`,
              }))}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space wrap>
              {canReview && (
                <>
                  <Popconfirm
                    title={`确认批量通过已勾选的 ${selectedRowKeys.length} 条建议？`}
                    onConfirm={() => batchReview('approve')}
                    disabled={selectedRowKeys.length === 0}
                  >
                    <Button type="primary" disabled={selectedRowKeys.length === 0} loading={reviewing}>批量通过</Button>
                  </Popconfirm>
                  <Popconfirm
                    title={`确认批量驳回已勾选的 ${selectedRowKeys.length} 条建议？`}
                    onConfirm={() => batchReview('reject')}
                    disabled={selectedRowKeys.length === 0}
                  >
                    <Button danger disabled={selectedRowKeys.length === 0} loading={reviewing}>批量驳回</Button>
                  </Popconfirm>
                </>
              )}
              {canConvert && (
                <Tooltip title={convertibleSelection ? undefined : convertHint}>
                  <span style={{ display: 'inline-block' }}>
                    <Button disabled={!convertibleSelection} loading={converting} onClick={batchConvert}>
                      转采购申请单
                    </Button>
                  </span>
                </Tooltip>
              )}
              <Button icon={<DownloadOutlined />} onClick={() => message.info('导出功能规划中，暂未接入')}>导出</Button>
              <Button icon={<ReloadOutlined />} onClick={() => load()} loading={loading}>刷新</Button>
            </Space>
          </Col>
        </Row>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 12 }}>
          {statusChips.map((c) => (
            <span
              key={c.key || 'all'}
              className={`sc-chip${status === c.key ? ' on' : ''}`}
              onClick={() => { setStatus(c.key); setPage(1) }}
            >
              {c.label} <span className="n">{c.count.toLocaleString('zh-CN')}</span>
            </span>
          ))}
          {chipSeparator}
          {typeChips.map((c) => (
            <span
              key={c.key}
              className={`sc-chip${typeFilter === c.key ? ' on' : ''}`}
              onClick={() => { setTypeFilter((prev) => (prev === c.key ? 'all' : c.key)); setPage(1) }}
            >
              {c.label} <span className="n">{c.count.toLocaleString('zh-CN')}</span>
            </span>
          ))}
          <span className="sc-sub" style={{ marginLeft: 'auto', fontSize: 11.5 }}>状态 × 类型可叠加，支持搜索</span>
        </div>
      </div>

      {selectedRunId == null ? (
        <div className="sc-card" style={{ padding: 40, textAlign: 'center' }}>
          <Typography.Text type="secondary">暂无成功的运算批次，请先在「运算批次」触发一次运算</Typography.Text>
        </div>
      ) : (
        <div className="sc-card" style={{ padding: '0 0 4px' }}>
          <div className="sc-card-head">
            <h3>缺口与建议清单</h3>
            <span className="sc-hint">
              {runNo ? `批次 ${runNo}` : ''}{total > 0 ? `${runNo ? ' · ' : ''}共 ${total.toLocaleString('zh-CN')} 条` : ''}
            </span>
            <span className="sc-sub" style={{ marginLeft: 'auto' }}>
              待审核 {statusCounts.pending || 0} · 已通过 {statusCounts.approved || 0} · 已转单 {statusCounts.converted || 0}
            </span>
          </div>
          <Table<SuggestionRow>
            rowKey="id"
            dataSource={data}
            columns={columns}
            loading={loading}
            size="small"
            scroll={{ x: 1320 }}
            rowSelection={(canReview || canConvert) ? {
              selectedRowKeys,
              onChange: (keys, rows) => { setSelectedRowKeys(keys); setSelectedRows(rows) },
              getCheckboxProps: (row) => ({ disabled: !canSelectRow(row) }),
            } : undefined}
            expandable={{ expandedRowRender: (row) => <SuggestionDrill row={row} /> }}
            pagination={{
              total, current: page, pageSize,
              showSizeChanger: true, showTotal: (t) => `共 ${t} 条`,
            }}
            locale={{
              emptyText: '本批次无建议：所有需求已被库存/在途单据覆盖。可到「订单覆盖」查看具体覆盖过程。',
            }}
            onChange={(pagination) => {
              setPage(pagination.current || 1)
              setPageSize(pagination.pageSize || 20)
            }}
          />
        </div>
      )}
    </div>
  )
}
