import { useCallback, useEffect, useState } from 'react'
import type { CSSProperties, Key, ReactNode } from 'react'
import {
  Alert, Button, Col, Input, Modal, Popconfirm, Row, Select, Space, Table, Tag, Typography, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  AppstoreOutlined, CheckCircleOutlined, CloseCircleOutlined, DownloadOutlined, ReloadOutlined, WarningOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import api from '@/services/api'
import ApprovalStatsCards from '@/components/ApprovalStatsCards'
import type { StatCard } from '@/components/ApprovalStatsCards'
import { useAuthStore } from '@/store/auth'
import { useExport } from '@/hooks/useExport'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

interface RunOption {
  id: number
  run_no: string
  status: string
}

interface ExceptionStats {
  by_status: Record<string, number>
  by_type: Record<string, number>
}

interface PageData<T> {
  total: number
  page: number
  page_size: number
  items: T[]
  stats?: ExceptionStats
}

interface PeggingItem {
  sale_order_no: string
  line_no: string | null
  qty: number
}

interface ExceptionRow {
  id: number
  run_id: number
  material_code: string
  material_name: string | null
  exception_code: number
  exception_type: string
  source_type: string
  source_doc_no: string | null
  source_line_no: string | null
  need_date: string | null
  doc_date: string | null
  adjust_days: number | null
  suggest_date: string | null
  suggest_qty: number | null
  detail: string | null
  pegging: PeggingItem[] | null
  status: string
}

interface BatchResult {
  updated: number
  skipped: { id: number; reason: string }[]
}

type BatchAction = 'ignore' | 'reschedule' | 'cancel_reduce' | 'notify'

const EXCEPTION_TYPE_MAP: Record<string, { label: string; color: string; code: string }> = {
  past_due_supply: { label: '拖期供给', color: 'volcano', code: '7' },
  past_due_demand: { label: '拖期需求', color: 'red', code: '6' },
  supply_late: { label: '建议提前', color: 'orange', code: '11' },
  supply_early: { label: '建议延后', color: 'blue', code: '15' },
  supply_excess: { label: '取消或减量', color: 'gold', code: '20·21' },
  below_safety_stock: { label: '低于安全库存', color: 'magenta', code: '96' },
  no_bom: { label: '无有效BOM', color: 'default', code: '50' },
}

const SOURCE_TYPE_MAP: Record<string, string> = {
  po: '采购订单',
  purchase_order: '采购订单',
  task: '生产任务',
  production_task_order: '生产任务',
  subcontract: '委外',
  subcontract_order: '委外',
  transfer: '调拨',
  transfer_order: '调拨',
  requisition: '采购申请',
  purchase_requisition: '采购申请',
  sale_order_line: '销售订单',
  mrp_material: '物料',
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  open: { label: '待处理', color: 'processing' },
  resolved: { label: '已处理', color: 'success' },
  ignored: { label: '已忽略', color: 'default' },
}

const ACTION_LABELS: Record<BatchAction, string> = {
  reschedule: '改期',
  ignore: '忽略',
  cancel_reduce: '取消减量',
  notify: '标记催货',
}

const BATCH_ACTIONS: BatchAction[] = ['reschedule', 'ignore', 'cancel_reduce']

const URGABLE_TYPES = ['past_due_supply', 'supply_late']
const RESCHEDULABLE_TYPES = ['past_due_supply', 'past_due_demand', 'supply_late', 'supply_early']

const PEGGING_COLUMNS: ColumnsType<PeggingItem> = [
  {
    title: '订单', dataIndex: 'sale_order_no',
    render: (v: string) => <span className="sc-mono" style={{ fontSize: 12 }}>{v || '—'}</span>,
  },
  { title: '行', dataIndex: 'line_no', width: 90, render: (v: string | null) => v || '—' },
  {
    title: '数量', dataIndex: 'qty', width: 110, align: 'right',
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

const PANEL_TITLE_STYLE: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  color: '#475569',
  marginBottom: 6,
}

function fmtQty(v: number | null | undefined): string {
  if (v == null) return '—'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

function fmtAdjust(v: number | null): ReactNode {
  if (v == null) return <span className="sc-sub">—</span>
  if (v === 0) return <span className="sc-mono">0</span>
  return (
    <b className="sc-mono" style={{ color: v > 0 ? '#d97706' : '#dc2626' }}>
      {v > 0 ? '+' : ''}{v.toLocaleString('zh-CN')}
    </b>
  )
}

function overdueNote(docDate: string | null): string | undefined {
  if (!docDate) return undefined
  const days = dayjs().startOf('day').diff(dayjs(docDate).startOf('day'), 'day')
  return days > 0 ? `已过 ${days.toLocaleString('zh-CN')} 天` : undefined
}

function buildAdvice(row: ExceptionRow): { text: string; note?: string } {
  switch (row.exception_type) {
    case 'supply_late':
      return row.adjust_days != null
        ? { text: `建议提前 ${Math.abs(row.adjust_days).toLocaleString('zh-CN')} 天` }
        : { text: '建议提前至需求日' }
    case 'supply_early':
      return row.adjust_days != null
        ? { text: `建议延后 ${Math.abs(row.adjust_days).toLocaleString('zh-CN')} 天` }
        : { text: '建议延后至需求日' }
    case 'past_due_demand':
      return { text: '请确认订单排期或关闭', note: overdueNote(row.doc_date) }
    case 'past_due_supply':
      return { text: '建议改期或催货', note: overdueNote(row.doc_date) }
    case 'supply_excess':
      return row.exception_code === 21 && row.suggest_qty != null
        ? { text: `建议减量 ${fmtQty(row.suggest_qty)}` }
        : { text: '建议取消，无对应需求' }
    case 'below_safety_stock':
      return {
        text: '已生成补货建议',
        note: row.suggest_qty != null ? `净缺口 ${fmtQty(row.suggest_qty)}` : undefined,
      }
    case 'no_bom':
      return { text: '请维护 BOM', note: '需求不展开，未参与覆盖计算' }
    default:
      return { text: row.detail || '—' }
  }
}

function buildWhy(row: ExceptionRow): string {
  const need = row.need_date || '—'
  const doc = row.doc_date || '—'
  const adjust = row.adjust_days != null ? Math.abs(row.adjust_days).toLocaleString('zh-CN') : '—'
  switch (row.exception_type) {
    case 'past_due_demand':
      return `需求日期 ${need} 已早于运算日，订单行仍挂着未交付需求（规则：需求日期 < 运算日）。`
    case 'past_due_supply':
      return `供给日期 ${doc} 已早于运算日，单据仍未到货 / 完工（规则：单据日期 < 运算日且未到货 / 完工）。`
    case 'supply_late':
      return `供给日期 ${doc} 晚于最早需求日 ${need} 达 ${adjust} 天，超出宽限期，建议提前至需求日。`
    case 'supply_early':
      return `供给日期 ${doc} 早于最晚需求日 ${need} 达 ${adjust} 天，超出宽限期，建议延后至需求日。`
    case 'supply_excess':
      return row.exception_code === 21
        ? `FIFO pegging 后该供给未被需求完全消化，剩余 ${fmtQty(row.suggest_qty)} 富余（规则：供给数量 > 需求合计）。`
        : 'FIFO pegging 后该供给未覆盖任何需求行，全部富余（规则：无对应需求）。'
    case 'below_safety_stock':
      return `当前可用库存低于安全库存水位，净缺口 ${fmtQty(row.suggest_qty)}（规则：可用库存 < 安全库存）。`
    case 'no_bom':
      return '物料为自制 / 委外，但 BOM 主数据无有效版本，需求无法展开（规则：自制物料无有效 BOM）。'
    default:
      return row.detail || '—'
  }
}

function peggingEmptyText(row: ExceptionRow): string {
  if (row.exception_type === 'below_safety_stock') return '无未结需求订单行（库存水位型例外）'
  if (row.exception_type === 'no_bom') return '待排产需求：暂无有效 BOM，不参与 pegging'
  if (row.exception_type === 'supply_excess') return '无关联需求（FIFO 未匹配到订单行）'
  return '无关联需求行（FIFO 未匹配到订单行）'
}

function describeResult(result: BatchResult): { text: string; hasSkipped: boolean } {
  if (!result.skipped || result.skipped.length === 0) {
    return { text: `已处理 ${result.updated} 条`, hasSkipped: false }
  }
  const reasons = Array.from(new Set(result.skipped.map((s) => s.reason)))
  return {
    text: `已处理 ${result.updated} 条，跳过 ${result.skipped.length} 条：${reasons.join('；')}`,
    hasSkipped: true,
  }
}

function DrillField({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div style={{
      display: 'flex', gap: 8, padding: '4px 0', borderBottom: '1px dashed #f1f5f9',
      fontSize: 12, lineHeight: 1.6,
    }}>
      <span style={{ width: 84, flexShrink: 0, color: '#94a3b8' }}>{label}</span>
      <span style={{ color: '#475569', minWidth: 0 }}>{value}</span>
    </div>
  )
}

function ExceptionDrill({ row }: { row: ExceptionRow }) {
  const pegging = row.pegging || []
  const fields: { label: string; value: ReactNode }[] = [
    {
      label: '源单据',
      value: `${SOURCE_TYPE_MAP[row.source_type] || row.source_type}${row.source_doc_no ? ` · ${row.source_doc_no}` : ''}`,
    },
    ...(row.source_line_no ? [{ label: '行号', value: row.source_line_no }] : []),
    { label: '需求日', value: <span className="sc-mono">{row.need_date || '—'}</span> },
    { label: '单据日期', value: <span className="sc-mono">{row.doc_date || '—'}</span> },
    ...(row.suggest_date ? [{ label: '建议日期', value: <span className="sc-mono">{row.suggest_date}</span> }] : []),
    ...(row.adjust_days != null ? [{ label: '调整天数', value: fmtAdjust(row.adjust_days) }] : []),
    ...(row.suggest_qty != null ? [{ label: '建议数量', value: <span className="sc-mono">{fmtQty(row.suggest_qty)}</span> }] : []),
    { label: '描述', value: row.detail || '—' },
  ]
  return (
    <div style={{ background: '#fbfcfe', borderTop: '1px dashed #e2e8f0', padding: '12px 16px' }}>
      <div style={{ fontSize: 12, color: '#475569', lineHeight: 1.7, marginBottom: 10, maxWidth: 980 }}>
        <b style={{ color: '#0f172a', marginRight: 6 }}>判定依据</b>{buildWhy(row)}
      </div>
      <Row gutter={[12, 12]}>
        <Col xs={24} xl={10}>
          <div style={PANEL_STYLE}>
            <div style={PANEL_TITLE_STYLE}>源单据摘要</div>
            {fields.map((f) => <DrillField key={f.label} label={f.label} value={f.value} />)}
          </div>
        </Col>
        <Col xs={24} xl={14}>
          <div style={PANEL_STYLE}>
            <div style={PANEL_TITLE_STYLE}>相关订单 pegging（FIFO）</div>
            {pegging.length > 0 ? (
              <Table<PeggingItem>
                rowKey={(r, index) => `${r.sale_order_no}-${r.line_no ?? ''}-${index}`}
                dataSource={pegging}
                columns={PEGGING_COLUMNS}
                size="small"
                pagination={false}
              />
            ) : (
              <div className="sc-sub" style={{ lineHeight: 1.8 }}>{peggingEmptyText(row)}</div>
            )}
          </div>
        </Col>
      </Row>
    </div>
  )
}

export default function ExceptionsTab({ runId }: { runId: number | null }) {
  const hasPermission = useAuthStore((s) => s.hasPermission) as (resource: string, action: string) => boolean
  const canReview = hasPermission('materials.mrp', 'review')
  const { exporting, exportData } = useExport()

  const [runOptions, setRunOptions] = useState<RunOption[]>([])
  const [selectedRunId, setSelectedRunId] = useState<number | null>(runId)
  const [exceptionType, setExceptionType] = useState('')
  const [status, setStatus] = useState('')
  const [sourceType, setSourceType] = useState('')
  const [keyword, setKeyword] = useState('')
  const [data, setData] = useState<ExceptionRow[]>([])
  const [stats, setStats] = useState<ExceptionStats | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])
  const [handling, setHandling] = useState(false)

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
      const res = (await api.get('/mrp/exceptions', {
        params: {
          run_id: selectedRunId,
          ...(exceptionType ? { exception_type: exceptionType } : {}),
          ...(status ? { status } : {}),
          ...(sourceType ? { source_type: sourceType } : {}),
          ...(keyword ? { keyword } : {}),
          page,
          page_size: pageSize,
        },
      })) as unknown as ApiResponse<PageData<ExceptionRow>>
      setData(res.data.items || [])
      setStats(res.data.stats || null)
      setTotal(res.data.total || 0)
    } catch {
      // 全局拦截器已提示
    } finally {
      setLoading(false)
    }
  }, [selectedRunId, exceptionType, status, sourceType, keyword, page, pageSize])

  useEffect(() => { load() }, [load])

  const resetPage = () => setPage(1)

  const toggleStatus = (next: string) => {
    setStatus((prev) => (prev === next ? '' : next))
    resetPage()
  }

  const clearStatus = () => {
    setStatus('')
    resetPage()
  }

  const handleExport = () => {
    if (selectedRunId == null) return
    exportData('/api/v1/mrp/exceptions/export', {
      run_id: selectedRunId,
      ...(exceptionType ? { exception_type: exceptionType } : {}),
      ...(status ? { status } : {}),
      ...(sourceType ? { source_type: sourceType } : {}),
      ...(keyword ? { keyword } : {}),
    }, 'MRP例外清单.csv')
  }

  const callBatch = async (action: BatchAction, ids: number[]): Promise<BatchResult> => {
    const res = (await api.post('/mrp/exceptions/batch-handle', {
      exception_ids: ids,
      action,
    })) as unknown as ApiResponse<BatchResult>
    return res.data
  }

  const runHandle = async (action: BatchAction, ids: number[], successText?: string, clearSelection = false) => {
    if (handling) return
    setHandling(true)
    try {
      const result = await callBatch(action, ids)
      const { text, hasSkipped } = describeResult(result)
      if (hasSkipped) message.warning(text)
      else message.success(successText || text)
      if (clearSelection) setSelectedRowKeys([])
      await load()
    } catch {
      // 全局拦截器已提示
    } finally {
      setHandling(false)
    }
  }

  const confirmBatch = (action: BatchAction) => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先勾选例外')
      return
    }
    Modal.confirm({
      title: `确认对已勾选的 ${selectedRowKeys.length} 条例外执行「${ACTION_LABELS[action]}」？`,
      onOk: () => runHandle(action, selectedRowKeys.map(Number), undefined, true),
    })
  }

  const renderRowActions = (row: ExceptionRow) => {
    if (!canReview || row.status !== 'open') return <span className="sc-sub">—</span>
    const actions: { key: BatchAction; label: string; confirm: string }[] = []
    if (RESCHEDULABLE_TYPES.includes(row.exception_type) && row.suggest_date != null) {
      actions.push({ key: 'reschedule', label: ACTION_LABELS.reschedule, confirm: '确认对该例外执行改期？' })
    }
    if (row.exception_type === 'supply_excess') {
      actions.push({ key: 'cancel_reduce', label: ACTION_LABELS.cancel_reduce, confirm: '确认对该例外执行取消或减量？' })
    }
    if (URGABLE_TYPES.includes(row.exception_type)) {
      actions.push({ key: 'notify', label: ACTION_LABELS.notify, confirm: '确认将该例外标记为已催货？' })
    }
    actions.push({ key: 'ignore', label: ACTION_LABELS.ignore, confirm: '确认忽略该例外？（下次运算会再次提示）' })
    return (
      <Space size={8} wrap>
        {actions.map((a) => (
          <Popconfirm key={a.key} title={a.confirm} onConfirm={() => runHandle(a.key, [row.id], `已${a.label}`)}>
            <a style={handling ? { pointerEvents: 'none', opacity: 0.5 } : undefined}>{a.label}</a>
          </Popconfirm>
        ))}
      </Space>
    )
  }

  const columns: ColumnsType<ExceptionRow> = [
    {
      title: '物料', dataIndex: 'material_code', width: 230,
      render: (_: string, row: ExceptionRow) => (
        <div>
          <div className="sc-mono" style={{ fontSize: 12.5, fontWeight: 600 }}>{row.material_code}</div>
          <div className="sc-sub">{row.material_name || '—'}</div>
        </div>
      ),
    },
    {
      title: '例外类型', dataIndex: 'exception_type', width: 160,
      render: (v: string, row: ExceptionRow) => {
        const m = EXCEPTION_TYPE_MAP[v] || { label: v, color: 'default', code: '' }
        return (
          <span style={{ whiteSpace: 'nowrap' }}>
            <Tag color={m.color}>{m.label}</Tag>
            <span style={{ fontSize: 10.5, color: '#94a3b8' }}>{row.exception_code}</span>
          </span>
        )
      },
    },
    {
      title: '源单据', key: 'source', width: 210,
      render: (_: unknown, row: ExceptionRow) => (
        <div>
          <div style={{ fontSize: 12.5 }}>
            {SOURCE_TYPE_MAP[row.source_type] || row.source_type}
            {row.source_doc_no ? ` · ${row.source_doc_no}` : ''}
          </div>
          {row.source_line_no && <div className="sc-sub">行 {row.source_line_no}</div>}
        </div>
      ),
    },
    {
      title: '需求日', dataIndex: 'need_date', width: 100,
      render: (v: string | null) => (v ? <span className="sc-mono">{v}</span> : <span className="sc-sub">—</span>),
    },
    {
      title: '单据日期', dataIndex: 'doc_date', width: 100,
      render: (v: string | null) => (v ? <span className="sc-mono">{v}</span> : <span className="sc-sub">—</span>),
    },
    {
      title: '建议日期', dataIndex: 'suggest_date', width: 100,
      render: (v: string | null) => (v ? <span className="sc-mono">{v}</span> : <span className="sc-sub">—</span>),
    },
    {
      title: '调整天数', dataIndex: 'adjust_days', width: 90, align: 'right',
      render: (v: number | null) => fmtAdjust(v),
    },
    {
      title: '一句话建议', key: 'advice', width: 220,
      render: (_: unknown, row: ExceptionRow) => {
        const { text, note } = buildAdvice(row)
        return (
          <div>
            <div style={{ fontSize: 12.5 }}>{text}</div>
            {note && <div className="sc-sub" style={{ marginTop: 1 }}>{note}</div>}
          </div>
        )
      },
    },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: string) => {
        const m = STATUS_MAP[v] || { label: v, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    ...(canReview ? [{
      title: '操作', key: 'action', width: 200, fixed: 'right' as const,
      render: (_: unknown, row: ExceptionRow) => renderRowActions(row),
    }] : []),
  ]

  const byStatus = stats?.by_status || {}
  const byType = stats?.by_type || {}
  const statusTotal = Object.values(byStatus).reduce((acc, n) => acc + (Number(n) || 0), 0)

  const kpiCards: StatCard[] = [
    {
      key: 'open', label: '待处理', value: fmtQty(byStatus.open || 0), unit: '条',
      icon: <WarningOutlined />, tone: 'danger', active: status === 'open',
      onClick: () => toggleStatus('open'),
    },
    {
      key: 'resolved', label: '已处理', value: fmtQty(byStatus.resolved || 0), unit: '条',
      icon: <CheckCircleOutlined />, tone: 'success', active: status === 'resolved',
      onClick: () => toggleStatus('resolved'),
    },
    {
      key: 'ignored', label: '已忽略', value: fmtQty(byStatus.ignored || 0), unit: '条',
      icon: <CloseCircleOutlined />, tone: 'muted', active: status === 'ignored',
      onClick: () => toggleStatus('ignored'),
    },
    {
      key: 'all', label: '合计', value: fmtQty(statusTotal), unit: '条',
      icon: <AppstoreOutlined />, tone: 'default', active: status === '',
      onClick: clearStatus,
    },
  ]

  const runNo = runOptions.find((r) => r.id === selectedRunId)?.run_no

  return (
    <div>
      <Alert
        type="info"
        showIcon
        message={<><b>怎么看：</b>例外不看未来缺口，而是挑现有单据的毛病：来早了、来晚了、过期了、多了。可直接处理或忽略（<b>忽略后下次运算会再提示</b>）。</>}
        style={{ marginBottom: 12 }}
      />

      <ApprovalStatsCards cards={kpiCards} />

      <div className="sc-card" style={{ padding: '14px 16px', marginBottom: 12 }}>
        <Row gutter={[12, 12]} align="middle">
          <Col>
            <Input.Search
              placeholder="搜索物料编码/名称"
              style={{ width: 220 }}
              allowClear
              onSearch={(v) => { setKeyword(v.trim()); resetPage() }}
            />
          </Col>
          <Col>
            <Select
              placeholder="运算批次"
              value={selectedRunId ?? undefined}
              onChange={(v) => { setSelectedRunId(v ?? null); resetPage() }}
              style={{ width: 260 }}
              options={runOptions.map((r) => ({
                value: r.id,
                label: `${r.run_no}${r.status === 'success' ? '' : `（${r.status}）`}`,
              }))}
            />
          </Col>
          <Col>
            <Select
              placeholder="源单据类型"
              value={sourceType || undefined}
              onChange={(v) => { setSourceType(v || ''); resetPage() }}
              style={{ width: 140 }}
              allowClear
            >
              {Object.entries(SOURCE_TYPE_MAP).map(([value, label]) => (
                <Select.Option key={value} value={value}>{label}</Select.Option>
              ))}
            </Select>
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<DownloadOutlined />} onClick={handleExport} loading={exporting} disabled={selectedRunId == null}>导出</Button>
              <Button icon={<ReloadOutlined />} onClick={() => load()} loading={loading}>刷新</Button>
            </Space>
          </Col>
        </Row>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap', marginTop: 12 }}>
          <span
            className={`sc-chip${exceptionType === '' ? ' on' : ''}`}
            onClick={() => { setExceptionType(''); resetPage() }}
          >
            全部 <span className="n">{statusTotal.toLocaleString('zh-CN')}</span>
          </span>
          {Object.entries(EXCEPTION_TYPE_MAP).map(([value, meta]) => (
            <span
              key={value}
              className={`sc-chip${exceptionType === value ? ' on' : ''}`}
              onClick={() => { setExceptionType(value); resetPage() }}
            >
              {meta.label}
              <span style={{ fontSize: 10.5, color: '#94a3b8' }}>{meta.code}</span>
              <span className="n">{(byType[value] || 0).toLocaleString('zh-CN')}</span>
            </span>
          ))}
          <span className="sc-sub" style={{ marginLeft: 'auto', fontSize: 11.5 }}>状态 × 类型可叠加</span>
        </div>
      </div>

      {selectedRunId == null ? (
        <div className="sc-card" style={{ padding: 40, textAlign: 'center' }}>
          <Typography.Text type="secondary">暂无成功的运算批次，请先在「运算批次」触发一次运算</Typography.Text>
        </div>
      ) : (
        <div className="sc-card" style={{ padding: '0 0 4px' }}>
          <div className="sc-card-head">
            <h3>例外清单</h3>
            <span className="sc-hint">
              {runNo ? `批次 ${runNo}` : ''}{total > 0 ? `${runNo ? ' · ' : ''}共 ${total.toLocaleString('zh-CN')} 条` : ''}
            </span>
            <span className="sc-sub" style={{ marginLeft: 'auto' }}>
              待处理 {byStatus.open || 0} · 已处理 {byStatus.resolved || 0} · 已忽略 {byStatus.ignored || 0}
            </span>
          </div>
          <Table<ExceptionRow>
            rowKey="id"
            dataSource={data}
            columns={columns}
            loading={loading}
            size="small"
            scroll={{ x: 1560 }}
            rowSelection={canReview ? {
              selectedRowKeys,
              onChange: (keys) => setSelectedRowKeys(keys),
              getCheckboxProps: (row) => ({ disabled: row.status !== 'open' }),
            } : undefined}
            expandable={{ expandedRowRender: (row) => <ExceptionDrill row={row} /> }}
            pagination={{
              total, current: page, pageSize,
              showSizeChanger: true, showTotal: (t) => `共 ${t} 条`,
            }}
            locale={{
              emptyText: '本批次无例外：现有单据的时间与数量都与需求匹配。',
            }}
            onChange={(pagination) => {
              setPage(pagination.current || 1)
              setPageSize(pagination.pageSize || 20)
            }}
          />
        </div>
      )}

      {canReview && selectedRowKeys.length > 0 && (
        <div className="sc-batch-bar">
          <span className="bb-n">已选 <b>{selectedRowKeys.length}</b> 条</span>
          <span className="bb-sep" />
          {BATCH_ACTIONS.map((action) => (
            <Button key={action} size="small" loading={handling} onClick={() => confirmBatch(action)}>
              批量{ACTION_LABELS[action]}
            </Button>
          ))}
          <span className="bb-sep" />
          <Button size="small" type="text" onClick={() => setSelectedRowKeys([])}>清除选择</Button>
        </div>
      )}
    </div>
  )
}
