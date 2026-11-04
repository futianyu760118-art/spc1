import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Alert, Button, Descriptions, Input, Select, Space, Spin, Table, Tag, Tooltip, Typography, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckCircleOutlined, PlayCircleOutlined, ReloadOutlined, UnorderedListOutlined, WarningOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import api from '@/services/api'
import ApprovalStatsCards from '@/components/ApprovalStatsCards'
import type { StatCard } from '@/components/ApprovalStatsCards'
import { useAuthStore } from '@/store/auth'

interface PageData<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

interface ComparisonSummary {
  run_id?: number
  total_suggestions?: number
  match?: number
  diff_qty?: number
  diff_date?: number
  spc_only?: number
  k3_only?: number
  match_rate?: number
  error?: string
}

interface ComparisonItem {
  id: number
  material_id: number
  material_code: string
  material_name: string | null
  bill_type: number
  suggest_qty: number
  need_date: string | null
  compare_status: string | null
  k3_qty: number | null
  k3_need_date: string | null
}

interface K3OnlyItem {
  material_id: number
  need_date: string
  qty: number
}

interface ComparisonData {
  summary: ComparisonSummary
  k3_only: K3OnlyItem[]
  items: ComparisonItem[]
}

interface RunStats {
  demand_lines?: number
  materials_processed?: number
  buckets?: number
  suggestions?: number
  exceptions?: number
  duration_sec?: number
  data_issues?: Record<string, unknown> | null
  comparison?: ComparisonSummary | null
}

interface RunDetailState {
  loading: boolean
  loaded: boolean
  stats: RunStats | null
}

interface RunRow {
  id: number
  run_no: string
  run_type: string
  triggered_by: string | null
  status: string
  horizon_days: number
  stats: RunStats | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

type ScopeType = 'all' | 'sale_order_no' | 'material_codes'

const RUN_TYPE_MAP: Record<string, { label: string; color: string }> = {
  scheduled: { label: '定时', color: 'geekblue' },
  manual: { label: '手动', color: 'purple' },
}

const RUN_STATUS_MAP: Record<string, { label: string; color: string }> = {
  running: { label: '运算中', color: 'processing' },
  success: { label: '成功', color: 'success' },
  failed: { label: '失败', color: 'error' },
}

const SCOPE_OPTIONS: { value: ScopeType; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'sale_order_no', label: '按订单号' },
  { value: 'material_codes', label: '按物料编码' },
]

const K3_STATUS_ORDER = ['match', 'diff_qty', 'diff_date', 'spc_only', 'k3_only'] as const
type K3Status = typeof K3_STATUS_ORDER[number]

const COMPARE_META: Record<K3Status, { label: string; color: string; bg: string; hint: string }> = {
  match: { label: 'match', color: '#16a34a', bg: '#f0fdf4', hint: '一致：量差 ≤5% 且需求日 ±3 天内' },
  diff_qty: { label: 'diff_qty', color: '#ea580c', bg: '#fff7ed', hint: '数量差 > 5%' },
  diff_date: { label: 'diff_date', color: '#d97706', bg: '#fffbeb', hint: '需求日差 > 3 天' },
  spc_only: { label: 'spc_only', color: '#8b5cf6', bg: '#f5f3ff', hint: 'SPC 有建议 · K3 无计划' },
  k3_only: { label: 'k3_only', color: '#64748b', bg: '#f1f5f9', hint: 'K3 有计划 · SPC 无建议' },
}

const NOTE_BOLD_STYLE = { color: '#475569' }

function fmtQty(v: number | null | undefined): string {
  if (v == null) return '—'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

function fmtTime(v: string | null): string {
  return v ? dayjs(v).format('MM-DD HH:mm') : '—'
}

function isK3Status(v: string | null): v is K3Status {
  return v != null && (K3_STATUS_ORDER as readonly string[]).includes(v)
}

function CompareTag({ status }: { status: string | null }) {
  if (!status) return <>{'—'}</>
  if (!isK3Status(status)) return <>{status}</>
  const meta = COMPARE_META[status]
  return (
    <span className="sc-tag" style={{ color: meta.color, background: meta.bg }} title={meta.hint}>
      {meta.label}
    </span>
  )
}

function K3MiniCard({
  kind, value, desc, compact,
}: {
  kind: K3Status
  value?: number
  desc?: string
  compact?: boolean
}) {
  const meta = COMPARE_META[kind]
  return (
    <div
      style={{
        border: '1px solid #e2e8f0', borderRadius: 9, background: '#fff', minWidth: 0,
        padding: compact ? '8px 10px' : '10px 12px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: compact ? 10.5 : 11.5, fontWeight: 600, color: meta.color }}>
        <i style={{ width: 8, height: 8, borderRadius: 2, background: 'currentColor', display: 'inline-block' }} />
        {meta.label}
      </div>
      <div className="sc-mono" style={{ fontSize: compact ? 16 : 20, fontWeight: 700, lineHeight: 1.2, marginTop: compact ? 2 : 4, color: meta.color }}>
        {fmtQty(value)}
      </div>
      {desc ? <div className="sc-sub" style={{ marginTop: 2 }}>{desc}</div> : null}
    </div>
  )
}

function renderStats(stats: RunStats | null): string {
  if (!stats) return '-'
  const parts: string[] = []
  if (stats.suggestions != null) parts.push(`建议 ${stats.suggestions} 条`)
  if (stats.duration_sec != null) parts.push(`耗时 ${stats.duration_sec}s`)
  return parts.length ? parts.join(' · ') : '-'
}

const DATA_ISSUE_LABELS: Record<string, string> = {
  demand_without_bom: '需求行缺BOM',
  no_bom: '无有效BOM',
  material_property_missing: '物料属性缺失',
  bom_parent_property_missing: 'BOM父件属性缺失',
  bom_cycle: 'BOM环路',
  subcontract_date_approx: '委外日期近似',
  param_fallback: '参数回退统计',
  stale_supply_excluded: '历史供给未计入',
  sync_stale: 'K3 同步过期',
}

const SUPPLY_TYPE_LABELS: Record<string, string> = {
  task: '任务',
  po: '采购',
  subcontract: '委外',
  transfer: '调拨',
  requisition: '申请',
}

function issueLabel(key: string): string {
  return DATA_ISSUE_LABELS[key] || key
}

function fmtIssueValue(value: unknown): string {
  if (value == null) return '-'
  if (typeof value === 'number') return String(value)
  if (Array.isArray(value)) return `${value.length} 项`
  if (typeof value === 'object') return `${Object.keys(value as Record<string, unknown>).length} 项`
  return String(value)
}

function fmtDataIssue(key: string, value: unknown): string {
  if (key === 'param_fallback' && value != null && typeof value === 'object' && !Array.isArray(value)) {
    const stat = value as Record<string, unknown>
    return `参数回退：共 ${stat.total ?? '-'} / 已配置 ${stat.configured ?? '-'} / 历史推导 ${stat.derived ?? '-'} / 默认 ${stat.default ?? '-'}`
  }
  if (key === 'stale_supply_excluded' && value != null && typeof value === 'object' && !Array.isArray(value)) {
    const payload = value as { cutoff?: string; by_type?: Record<string, { count?: number; qty?: number }> }
    const parts = Object.entries(payload.by_type ?? {}).map(
      ([type, v]) => `${SUPPLY_TYPE_LABELS[type] || type} ${v.count ?? 0} 张/${v.qty ?? 0} 件`
    )
    return `历史供给未计入（早于 ${payload.cutoff ?? '-'}）：${parts.join('、') || '-'}`
  }
  return `${issueLabel(key)}：${fmtIssueValue(value)}`
}

export default function RunsTab({ onOpenRun }: { onOpenRun: (runId: number) => void }) {
  const hasPermission = useAuthStore((s) => s.hasPermission) as (resource: string, action: string) => boolean
  const canRun = hasPermission('materials.mrp', 'run')

  const [data, setData] = useState<RunRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [lastSuccess, setLastSuccess] = useState<RunRow | null>(null)

  const [scope, setScope] = useState<ScopeType>('all')
  const [scopeValue, setScopeValue] = useState('')
  const [triggering, setTriggering] = useState(false)

  const [comparison, setComparison] = useState<ComparisonData | null>(null)
  const [comparisonLoading, setComparisonLoading] = useState(false)
  const [comparisonError, setComparisonError] = useState(false)

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const res = (await api.get('/mrp/runs', { params: { page, page_size: pageSize } })) as unknown as ApiResponse<PageData<RunRow>>
      const items = res.data.items || []
      setData(items)
      setTotal(res.data.total || 0)
      if (page === 1) setLastSuccess(items.find((row) => row.status === 'success') ?? null)
    } catch {
      // 全局拦截器已提示
    } finally {
      if (!silent) setLoading(false)
    }
  }, [page, pageSize])

  const loadComparison = useCallback(async (silent = false) => {
    if (!silent) setComparisonLoading(true)
    try {
      const res = (await api.get('/mrp/comparison', { skipErrorToast: true })) as unknown as ApiResponse<ComparisonData>
      setComparison(res.data)
      setComparisonError(false)
    } catch {
      setComparison(null)
      setComparisonError(true)
    } finally {
      if (!silent) setComparisonLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => { loadComparison() }, [loadComparison])

  const hasRunning = data.some((row) => row.status === 'running')
  useEffect(() => {
    if (!hasRunning) return
    const timer = setInterval(() => {
      void load(true)
      void loadComparison(true)
    }, 5000)
    return () => clearInterval(timer)
  }, [hasRunning, load, loadComparison])

  const [runDetails, setRunDetails] = useState<Record<number, RunDetailState>>({})
  const requestedRunIds = useRef<Set<number>>(new Set())

  const fetchRunDetail = useCallback(async (runId: number) => {
    if (requestedRunIds.current.has(runId)) return
    requestedRunIds.current.add(runId)
    setRunDetails((prev) => ({ ...prev, [runId]: { loading: true, loaded: false, stats: prev[runId]?.stats ?? null } }))
    try {
      const res = (await api.get(`/mrp/runs/${runId}`)) as unknown as ApiResponse<RunRow>
      setRunDetails((prev) => ({ ...prev, [runId]: { loading: false, loaded: true, stats: res.data.stats ?? null } }))
    } catch {
      requestedRunIds.current.delete(runId)
      setRunDetails((prev) => ({ ...prev, [runId]: { loading: false, loaded: false, stats: null } }))
    }
  }, [])

  const submitTrigger = async () => {
    const key = scopeValue.trim()
    if (scope === 'sale_order_no' && !key) {
      message.warning('请先填写订单号')
      return
    }
    if (scope === 'material_codes' && !key) {
      message.warning('请先填写物料编码')
      return
    }
    setTriggering(true)
    try {
      const payload: Record<string, unknown> = { scope }
      if (scope === 'sale_order_no') payload.sale_order_no = key
      if (scope === 'material_codes') payload.material_codes = key.split(/[,，\s]+/).filter(Boolean)
      const res = (await api.post('/mrp/runs', payload)) as unknown as ApiResponse<{ run_id: number; run_no: string; status: string }>
      message.success(`已触发运算：${res.data.run_no}`)
      setScopeValue('')
      await load()
    } catch (e) {
      const status = (e as { response?: { status?: number } })?.response?.status
      if (status === 409) message.error('MRP 正在运算中')
      // 其余错误由全局拦截器提示
    } finally {
      setTriggering(false)
    }
  }

  const scrollToK3Card = () => {
    document.getElementById('mrp-k3-card')?.scrollIntoView({ behavior: 'smooth' })
  }

  const comparisonSummary = comparison?.summary
  const k3Union = comparisonSummary
    ? (comparisonSummary.total_suggestions ?? 0) + (comparisonSummary.k3_only ?? 0)
    : 0

  const runStatusMeta = lastSuccess
    ? (RUN_STATUS_MAP[lastSuccess.status] ?? { label: lastSuccess.status, color: 'default' })
    : null
  const lastDuration = lastSuccess?.stats?.duration_sec

  const statCards: StatCard[] = [
    {
      key: 'last-run', label: '上次运算',
      value: lastDuration != null ? `${lastDuration}s` : (runStatusMeta?.label ?? '—'),
      unit: lastDuration != null ? runStatusMeta?.label : undefined,
      icon: <PlayCircleOutlined />, tone: 'success',
      hint: lastSuccess
        ? `${lastSuccess.run_no} · ${fmtTime(lastSuccess.started_at || lastSuccess.created_at)}`
        : '暂无成功的运算批次',
    },
    {
      key: 'suggestions', label: '本批建议',
      value: fmtQty(lastSuccess?.stats?.suggestions), unit: '条',
      icon: <UnorderedListOutlined />, tone: 'default',
      hint: lastSuccess ? `批次 ${lastSuccess.run_no} 生成` : '暂无成功的运算批次',
    },
    {
      key: 'exceptions', label: '本批例外',
      value: fmtQty(lastSuccess?.stats?.exceptions), unit: '条',
      icon: <WarningOutlined />, tone: 'warning',
      hint: lastSuccess ? '现有单据的问题提醒 · 明细见「例外」' : '暂无成功的运算批次',
    },
    {
      key: 'k3-match', label: 'K3 match',
      value: fmtQty(comparisonSummary?.match), unit: '项',
      icon: <CheckCircleOutlined />, tone: 'success',
      hint: comparisonSummary
        ? `近 7 天并集 ${fmtQty(k3Union)} 项 · 差异 ${fmtQty(k3Union - (comparisonSummary.match ?? 0))} 项`
        : '暂无对比数据',
      onClick: scrollToK3Card,
    },
  ]

  const scopePlaceholder = scope === 'all'
    ? '全部订单（无需填写）'
    : scope === 'sale_order_no'
      ? '订单号，如 HJ202609-0025-0215'
      : '物料编码，如 1.6.3.E2835-18V-4000K-1W（多个用逗号分隔）'

  const handleTroubleshoot = (code: string) => {
    message.info(`排查 ${code}：并排核对 SPC 建议与 K3 计划（排查面板规划中，暂未接入）`)
  }

  const itemColumns: ColumnsType<ComparisonItem> = [
    {
      title: '物料', dataIndex: 'material_code', width: 300,
      render: (_: unknown, row: ComparisonItem) => (
        <div>
          <div className="sc-mono" style={{ fontSize: 12.5, fontWeight: 600 }}>{row.material_code}</div>
          <div className="sc-sub">{row.material_name || '—'}</div>
        </div>
      ),
    },
    {
      title: 'SPC 量', dataIndex: 'suggest_qty', width: 100, align: 'right',
      render: (v: number) => fmtQty(v),
    },
    {
      title: 'SPC 需求日', dataIndex: 'need_date', width: 110,
      render: (v: string | null) => v || '—',
    },
    {
      title: 'K3 量', dataIndex: 'k3_qty', width: 100, align: 'right',
      render: (v: number | null) => fmtQty(v),
    },
    {
      title: 'K3 需求日', dataIndex: 'k3_need_date', width: 110,
      render: (v: string | null) => v || '—',
    },
    {
      title: '差异类型', dataIndex: 'compare_status', width: 110,
      render: (v: string | null) => <CompareTag status={v} />,
    },
    {
      title: '操作', width: 80,
      render: (_: unknown, row: ComparisonItem) => (
        <Button type="link" size="small" onClick={() => handleTroubleshoot(row.material_code)}>排查</Button>
      ),
    },
  ]

  const k3OnlyColumns: ColumnsType<K3OnlyItem> = [
    {
      title: '物料 ID', dataIndex: 'material_id', width: 140,
      render: (v: number) => <span className="sc-mono" style={{ fontSize: 12 }}>{v}</span>,
    },
    { title: '需求日', dataIndex: 'need_date', width: 120 },
    {
      title: 'K3 量', dataIndex: 'qty', width: 120, align: 'right',
      render: (v: number) => fmtQty(v),
    },
    {
      title: '差异类型', width: 110,
      render: () => <CompareTag status="k3_only" />,
    },
    {
      title: '操作', width: 80,
      render: (_: unknown, row: K3OnlyItem) => (
        <Button type="link" size="small" onClick={() => handleTroubleshoot(`#${row.material_id}`)}>排查</Button>
      ),
    },
  ]

  const renderExpandedRow = (row: RunRow) => {
    const detail = runDetails[row.id]
    const stats = detail?.loaded ? (detail.stats ?? row.stats) : null
    const issueEntries = stats?.data_issues ? Object.entries(stats.data_issues) : []
    const runComparison = stats?.comparison ?? null

    return (
      <div>
        {row.error_message && (
          <Typography.Paragraph style={{ margin: '0 0 12px', whiteSpace: 'pre-wrap' }}>
            {row.error_message}
          </Typography.Paragraph>
        )}
        {detail?.loading && <Spin size="small" />}
        {!detail?.loading && !detail?.loaded && (
          <Space>
            <Typography.Text type="secondary">统计数据加载失败</Typography.Text>
            <Button type="link" size="small" onClick={() => { void fetchRunDetail(row.id) }}>重试</Button>
          </Space>
        )}
        {detail?.loaded && !stats && <Typography.Text type="secondary">暂无统计数据</Typography.Text>}
        {detail?.loaded && stats && (
          <>
            <Descriptions size="small" column={6} title="统计" style={{ marginBottom: 8 }}>
              <Descriptions.Item label={<Tooltip title="缺口需要新增的计划条数，0 = 无缺口">建议数</Tooltip>}>{stats.suggestions ?? '-'}</Descriptions.Item>
              <Descriptions.Item label={<Tooltip title="现有单据的问题提醒条数，与未来缺口无关">例外数</Tooltip>}>{stats.exceptions ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="桶数">{stats.buckets ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="需求行数">{stats.demand_lines ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="物料数">{stats.materials_processed ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="耗时">{stats.duration_sec != null ? `${stats.duration_sec}s` : '-'}</Descriptions.Item>
            </Descriptions>
            <div style={{ marginBottom: runComparison ? 12 : 0 }}>
              <Typography.Text strong>数据体检</Typography.Text>
              <div style={{ marginTop: 6 }}>
                {issueEntries.length ? (
                  <Space size={[8, 8]} wrap>
                    {issueEntries.map(([key, value]) => (
                      <Tag key={key}>{fmtDataIssue(key, value)}</Tag>
                    ))}
                  </Space>
                ) : (
                  <Typography.Text type="secondary">无体检项</Typography.Text>
                )}
              </div>
            </div>
            {runComparison && (
              runComparison.error ? (
                <Typography.Text type="secondary">K3 对比失败：{runComparison.error}</Typography.Text>
              ) : (
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                    <Typography.Text strong>K3 对比摘要</Typography.Text>
                    <span className="sc-sub">影子校验 · 本批口径</span>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(132px, 1fr))', gap: 8 }}>
                    {K3_STATUS_ORDER.map((kind) => (
                      <K3MiniCard key={kind} kind={kind} value={runComparison[kind]} compact />
                    ))}
                  </div>
                  <Button type="link" size="small" style={{ paddingLeft: 0, marginTop: 4 }} onClick={scrollToK3Card}>
                    查看完整差异清单 →
                  </Button>
                </div>
              )
            )}
          </>
        )}
      </div>
    )
  }

  const columns: ColumnsType<RunRow> = [
    {
      title: '批次号', dataIndex: 'run_no', width: 190,
      render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    {
      title: '类型', dataIndex: 'run_type', width: 80,
      render: (v: string) => {
        const m = RUN_TYPE_MAP[v] || { label: v, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: string) => {
        const m = RUN_STATUS_MAP[v] || { label: v, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '触发人', dataIndex: 'triggered_by', width: 100,
      render: (v: string | null) => v || '-',
    },
    {
      title: '展望期', dataIndex: 'horizon_days', width: 90,
      render: (v: number) => `${v} 天`,
    },
    {
      title: '统计摘要', dataIndex: 'stats', width: 180,
      render: (v: RunStats | null) => renderStats(v),
    },
    {
      title: '开始时间', dataIndex: 'started_at', width: 170,
      render: (v: string | null) => fmtTime(v),
    },
    {
      title: '结束时间', dataIndex: 'finished_at', width: 170,
      render: (v: string | null) => fmtTime(v),
    },
    {
      title: '操作', width: 100, fixed: 'right',
      render: (_, row) => (
        <Button type="link" size="small" onClick={() => onOpenRun(row.id)}>查看建议</Button>
      ),
    },
  ]

  return (
    <div>
      <Alert
        type="info"
        showIcon
        message={<><b>怎么看：</b>批次＝每次运算的记录（每晚 02:00 自动 + 可手动）。K3 对比＝影子校验：把 SPC 建议与 K3 计划订单并排比。</>}
        style={{ marginBottom: 12 }}
      />

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'flex-start', marginBottom: 12 }}>
        <div style={{ flex: '4 1 780px', minWidth: 0 }}>
          <ApprovalStatsCards cards={statCards} />
        </div>
        <div className="sc-card" style={{ flex: '1.5 1 320px', minWidth: 0, padding: '13px 14px', display: 'flex', flexDirection: 'column', gap: 9 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <b style={{ fontSize: 13.5 }}>立即运算</b>
            <span className="sc-sub" style={{ marginLeft: 'auto', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 999, padding: '2px 9px', whiteSpace: 'nowrap' }}>
              下次自动运算 今晚 02:00
            </span>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <Select<ScopeType>
              value={scope}
              onChange={(v) => { setScope(v); setScopeValue('') }}
              options={SCOPE_OPTIONS}
              disabled={!canRun}
              style={{ width: 118, flexShrink: 0 }}
            />
            <Input
              value={scopeValue}
              onChange={(e) => setScopeValue(e.target.value)}
              onPressEnter={() => { if (canRun) void submitTrigger() }}
              placeholder={scopePlaceholder}
              disabled={scope === 'all' || !canRun}
              allowClear
              style={{ flex: 1, minWidth: 0 }}
            />
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={triggering}
              disabled={!canRun}
              onClick={submitTrigger}
            >
              立即运算
            </Button>
          </div>
          <div className="sc-sub" style={{ lineHeight: 1.6, marginTop: 'auto' }}>
            影子模式：只生成建议与例外，不自动投放任务单；按订单 / 按物料适合改单后快速重算。
          </div>
        </div>
      </div>

      <div className="sc-card" style={{ marginBottom: 12, padding: '0 0 4px' }}>
        <div className="sc-card-head" style={{ padding: '10px 16px' }}>
          <h3>运算批次</h3>
          <span className="sc-hint">共 {fmtQty(total)} 条{lastSuccess ? ` · 最新成功批次 ${lastSuccess.run_no}` : ''}</span>
          <span className="sc-sub" style={{ marginLeft: 'auto' }}>点击行首箭头展开「数据体检 + K3 对比摘要」</span>
          {hasRunning && <span className="sc-sub">存在运算中的批次，每 5 秒自动刷新</span>}
          <Button
            size="small"
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={() => { void load(); void loadComparison() }}
          >
            刷新
          </Button>
        </div>
        <Table<RunRow>
          rowKey="id"
          dataSource={data}
          columns={columns}
          loading={loading}
          size="small"
          scroll={{ x: 1200 }}
          pagination={{
            total, current: page, pageSize,
            showSizeChanger: true, showTotal: (t) => `共 ${t} 条`,
          }}
          locale={{
            emptyText: '还没有运算批次：点「立即运算」跑一次，或等待每晚 02:00 自动运算。',
          }}
          onChange={(pagination) => {
            setPage(pagination.current || 1)
            setPageSize(pagination.pageSize || 20)
          }}
          expandable={{
            onExpand: (expanded, row) => {
              if (expanded) void fetchRunDetail(row.id)
            },
            expandedRowRender: renderExpandedRow,
          }}
        />
      </div>

      <div className="sc-card" id="mrp-k3-card">
        <div className="sc-card-head" style={{ padding: '10px 16px' }}>
          <h3>K3 对比</h3>
          <span className="sc-hint">
            影子校验 · 近 7 天批次并集 · 按物料聚合{comparisonSummary ? ` · 并集 ${fmtQty(k3Union)} 项` : ''}
          </span>
        </div>
        <div style={{ padding: '12px 16px 14px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8 }}>
            {K3_STATUS_ORDER.map((kind) => (
              <K3MiniCard
                key={kind}
                kind={kind}
                value={comparisonSummary?.[kind]}
                desc={kind === 'match' && comparisonSummary
                  ? `匹配率 ${comparisonSummary.match_rate ?? '—'}%`
                  : COMPARE_META[kind].hint}
              />
            ))}
          </div>

          {comparisonError ? (
            <Alert
              type="info"
              showIcon
              style={{ marginTop: 12 }}
              message="暂无对比数据"
              description="需先有成功的运算批次，且 K3 计划订单表内有数据。"
            />
          ) : (
            <>
              <div style={{ marginTop: 12 }}>
                <Space style={{ marginBottom: 8 }}>
                  <Typography.Text strong>差异清单（SPC 建议 vs K3）</Typography.Text>
                  <span className="sc-sub">共 {fmtQty(comparisonSummary?.total_suggestions ?? comparison?.items.length ?? 0)} 条建议</span>
                </Space>
                <div style={{ border: '1px solid #e2e8f0', borderRadius: 9, overflow: 'hidden' }}>
                  <Table<ComparisonItem>
                    rowKey="id"
                    dataSource={comparison?.items || []}
                    columns={itemColumns}
                    loading={comparisonLoading}
                    size="small"
                    scroll={{ x: 1000 }}
                    pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
                  />
                </div>
              </div>

              <div style={{ marginTop: 14 }}>
                <Space style={{ marginBottom: 8 }}>
                  <Typography.Text strong>仅 K3 存在的需求</Typography.Text>
                  <span className="sc-sub">SPC 未产生对应建议 · {fmtQty(comparison?.k3_only.length ?? 0)} 条</span>
                </Space>
                <div style={{ border: '1px solid #e2e8f0', borderRadius: 9, overflow: 'hidden' }}>
                  <Table<K3OnlyItem>
                    rowKey={(row) => `${row.material_id}-${row.need_date}`}
                    dataSource={comparison?.k3_only || []}
                    columns={k3OnlyColumns}
                    loading={comparisonLoading}
                    size="small"
                    pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
                  />
                </div>
              </div>

              <div style={{ borderTop: '1px dashed #e2e8f0', paddingTop: 9, marginTop: 10, fontSize: 11.5, color: '#94a3b8', lineHeight: 1.8 }}>
                口径：K3 对比取<b style={NOTE_BOLD_STYLE}>近 7 天批次并集</b>、<b style={NOTE_BOLD_STYLE}>按物料聚合</b>；需求日按 <b style={NOTE_BOLD_STYLE}>±3 天窗口</b>对齐；数量差 <b style={NOTE_BOLD_STYLE}>≤5%</b> 记 <b style={NOTE_BOLD_STYLE}>match</b>；diff_qty＝量差超 5% · diff_date＝需求日差超 3 天 · spc_only＝仅 SPC 有建议 · k3_only＝仅 K3 有计划；K3 对比为影子校验，不影响 SPC 建议生效。
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
