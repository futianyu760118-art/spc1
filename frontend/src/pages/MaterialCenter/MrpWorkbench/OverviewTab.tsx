import { useCallback, useEffect, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import { Alert, Button, Col, Row, Spin, Table, Tag, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  AppstoreOutlined, CheckCircleOutlined, InboxOutlined, PlayCircleOutlined, ShoppingCartOutlined,
  SyncOutlined, WarningOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import api from '@/services/api'
import { useAuthStore } from '@/store/auth'

export type MrpTabKey = 'overview' | 'shortage' | 'order' | 'exceptions' | 'runs' | 'parameters'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

interface RunSummary {
  id: number
  run_no: string
  status: string
  run_type: string
  duration_sec: number | null
  suggestions: number | null
  exceptions: number | null
  created_at: string | null
}

interface TopGap {
  id: number
  material_code: string
  material_name: string | null
  bill_type: number
  suggest_qty: number
  need_date: string | null
  action_date: string | null
  source: string
  status: string
  supplier_name: string | null
}

interface MrpOverview {
  last_run: RunSummary | null
  pending_suggestions: number
  gap_materials: number
  pending_exceptions: number
  related_orders: number
  top_gaps: TopGap[]
}

const BILL_TYPE_MAP: Record<number, { label: string; color: string }> = {
  11010: { label: '外购', color: 'blue' },
  11011: { label: '自制', color: 'purple' },
  11012: { label: '委外', color: 'orange' },
}

const SUGGESTION_STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: '待审核', color: 'processing' },
  approved: { label: '已通过', color: 'success' },
  rejected: { label: '已驳回', color: 'error' },
  converted: { label: '已转单', color: 'default' },
}

const RUN_STATUS_MAP: Record<string, { label: string; color: string }> = {
  running: { label: '运算中', color: 'processing' },
  success: { label: '成功', color: 'success' },
  failed: { label: '失败', color: 'error' },
}

function fmtQty(v: number | null | undefined): string {
  if (v == null) return '—'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

function fmtDateTime(v: string | null): string {
  return v ? dayjs(v).format('MM-DD HH:mm') : '—'
}

function duePill(dateStr: string) {
  const days = dayjs(dateStr).startOf('day').diff(dayjs().startOf('day'), 'day')
  const level = days <= 3 ? 'urgent' : days <= 7 ? 'soon' : 'ok'
  const text = days < 0 ? `逾期${-days}天` : days === 0 ? '今天' : `${days}天`
  return <span className={`ac-due-pill ${level}`} title={`需求日 ${dateStr}`}>{dateStr.slice(5)} · {text}</span>
}

function isActionUrgent(dateStr: string | null): boolean {
  if (!dateStr) return false
  return dayjs(dateStr).startOf('day').diff(dayjs().startOf('day'), 'day') <= 0
}

interface StatCardData {
  key: string
  label: string
  value: string
  unit?: string
  icon: ReactNode
  accent: string
  accentBg: string
  hint?: string
  onClick?: () => void
}

function StatCardView({ card }: { card: StatCardData }) {
  return (
    <div
      className={`sc-stat-card ac-stat-card${card.onClick ? ' clickable' : ''}`}
      style={{ '--accent': card.accent, '--accent-bg': card.accentBg, height: '100%' } as CSSProperties}
      onClick={card.onClick}
    >
      <div className="sc-stat-icon">{card.icon}</div>
      <div className="sc-stat-main" style={{ minWidth: 0 }}>
        <div className="sc-stat-label">{card.label}</div>
        <div className="sc-stat-value">{card.value}{card.unit ? <small>{card.unit}</small> : null}</div>
        {card.hint ? <div className="sc-stat-delta flat">{card.hint}</div> : null}
      </div>
    </div>
  )
}

interface TaskCardData {
  key: string
  title: string
  num?: number
  icon: ReactNode
  accent: string
  accentBg: string
  desc: string
  buttonText: string
  primary?: boolean
  go: string
  onClick: () => void
}

function TaskCardView({ card }: { card: TaskCardData }) {
  return (
    <div className="sc-card" style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 8, height: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div
          className="sc-stat-icon"
          style={{ width: 32, height: 32, borderRadius: 8, fontSize: 16, '--accent': card.accent, '--accent-bg': card.accentBg } as CSSProperties}
        >
          {card.icon}
        </div>
        {card.num != null && <div className="sc-mono" style={{ marginLeft: 'auto', fontSize: 22, fontWeight: 700 }}>{card.num.toLocaleString('zh-CN')}</div>}
      </div>
      <div style={{ fontSize: 13.5, fontWeight: 600 }}>{card.title}</div>
      <div style={{ fontSize: 12, color: '#475569', lineHeight: 1.7, flex: 1 }}>{card.desc}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Button size="small" type={card.primary ? 'primary' : 'default'} onClick={card.onClick}>{card.buttonText}</Button>
        <span className="sc-sub">{card.go}</span>
      </div>
    </div>
  )
}

export default function OverviewTab({ onNavigate }: { onNavigate: (key: MrpTabKey) => void }) {
  const navigate = useNavigate()
  const hasPermission = useAuthStore((s) => s.hasPermission) as (resource: string, action: string) => boolean
  const canRun = hasPermission('materials.mrp', 'run')

  const [data, setData] = useState<MrpOverview | null>(null)
  const [loading, setLoading] = useState(false)
  const [running, setRunning] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = (await api.get('/mrp/overview')) as unknown as ApiResponse<MrpOverview>
      setData(res.data)
    } catch {
      // 全局拦截器已提示
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const runNow = async () => {
    setRunning(true)
    try {
      const res = (await api.post('/mrp/runs', { scope: 'all' })) as unknown as ApiResponse<{ run_no: string }>
      message.success(`已触发运算：${res.data.run_no}`)
      await load()
    } catch (e) {
      const status = (e as { response?: { status?: number } })?.response?.status
      if (status === 409) message.warning('正在运算中')
      // 其余错误由全局拦截器提示
    } finally {
      setRunning(false)
    }
  }

  const columns: ColumnsType<TopGap> = [
    {
      title: '物料', dataIndex: 'material_code', width: 240,
      render: (_: string, row: TopGap) => (
        <div>
          <div className="sc-mono" style={{ fontSize: 12.5, fontWeight: 600 }}>{row.material_code}</div>
          <div className="sc-sub">{row.material_name || '—'}</div>
        </div>
      ),
    },
    {
      title: '类型', dataIndex: 'bill_type', width: 76,
      render: (v: number) => {
        const m = BILL_TYPE_MAP[v]
        return m ? <Tag color={m.color}>{m.label}</Tag> : <Tag>{v}</Tag>
      },
    },
    {
      title: '缺口数量', dataIndex: 'suggest_qty', width: 100, align: 'right',
      render: (v: number) => <b className="sc-mono" style={{ color: '#dc2626' }}>{fmtQty(v)}</b>,
    },
    {
      title: '需求日', dataIndex: 'need_date', width: 130,
      render: (v: string | null) => (v ? duePill(v) : <span className="sc-sub">—</span>),
    },
    {
      title: '下单日', dataIndex: 'action_date', width: 120,
      render: (v: string | null) => {
        if (!v) return '—'
        const urgent = isActionUrgent(v)
        return (
          <span className="sc-mono" style={urgent ? { color: '#dc2626', fontWeight: 700 } : undefined}>
            {v}{urgent ? ' · 紧急' : ''}
          </span>
        )
      },
    },
    {
      title: '供应商', dataIndex: 'supplier_name', width: 150,
      render: (v: string | null) => v || '—',
    },
    {
      title: '状态', dataIndex: 'status', width: 88,
      render: (v: string) => {
        const m = SUGGESTION_STATUS_MAP[v] || { label: v, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '操作', width: 90,
      render: () => <Button type="link" size="small" onClick={() => onNavigate('shortage')}>去审核</Button>,
    },
  ]

  const infoStrip = (
    <Alert
      type="info"
      showIcon
      message={<><b>怎么看：</b>MRP 把销售订单翻译成缺口清单：这里有缺口才有建议；没有建议＝已被库存/在途覆盖。每天 02:00 自动运算。</>}
      style={{ marginBottom: 12 }}
    />
  )

  if (loading && !data) {
    return (
      <div>
        {infoStrip}
        <div className="sc-card" style={{ padding: 60, textAlign: 'center' }}><Spin /></div>
      </div>
    )
  }

  const overview = data
  const lastRun = overview?.last_run ?? null

  if (!overview || !lastRun) {
    return (
      <div>
        {infoStrip}
        <div className="sc-card" style={{ padding: 48, textAlign: 'center' }}>
          <div className="sc-sub" style={{ marginBottom: 16 }}>还没有成功的运算批次：点「立即运算」跑一次。</div>
          {canRun && (
            <Button type="primary" icon={<PlayCircleOutlined />} loading={running} onClick={runNow}>立即运算</Button>
          )}
        </div>
      </div>
    )
  }

  const runStatus = RUN_STATUS_MAP[lastRun.status] || { label: lastRun.status, color: 'default' }
  const earliestAction = overview.top_gaps
    .map((g) => g.action_date)
    .filter((v): v is string => Boolean(v))
    .sort()[0]
  const countByStatus = (status: string) => overview.top_gaps.filter((g) => g.status === status).length

  const statCards: StatCardData[] = [
    {
      key: 'pending-suggestions', label: '待审核建议', value: fmtQty(overview.pending_suggestions), unit: '条',
      icon: <CheckCircleOutlined />, accent: '#d97706', accentBg: '#fffbeb',
      hint: earliestAction ? `最早 ${earliestAction.slice(5)} 需下单` : '暂无紧急下单',
      onClick: () => onNavigate('shortage'),
    },
    {
      key: 'gap-materials', label: '缺口物料', value: fmtQty(overview.gap_materials), unit: '个',
      icon: <InboxOutlined />, accent: '#dc2626', accentBg: '#fef2f2',
      hint: '本批运算口径',
      onClick: () => onNavigate('shortage'),
    },
    {
      key: 'pending-exceptions', label: '待处理例外', value: fmtQty(overview.pending_exceptions), unit: '条',
      icon: <WarningOutlined />, accent: '#d97706', accentBg: '#fffbeb',
      hint: lastRun.exceptions != null ? `本批累计 ${fmtQty(lastRun.exceptions)} 条` : '逾期单据不计入覆盖',
      onClick: () => onNavigate('exceptions'),
    },
    {
      key: 'related-orders', label: '涉及订单', value: fmtQty(overview.related_orders), unit: '单',
      icon: <AppstoreOutlined />, accent: '#5b5bd6', accentBg: '#eef0fe',
      hint: '待审核建议关联的销售订单',
      onClick: () => onNavigate('order'),
    },
    {
      key: 'last-run', label: '上次运算',
      value: lastRun.duration_sec != null ? `${lastRun.duration_sec}s` : runStatus.label,
      unit: lastRun.duration_sec != null ? runStatus.label : undefined,
      icon: <PlayCircleOutlined />, accent: '#16a34a', accentBg: '#f0fdf4',
      hint: `${lastRun.run_no} · ${fmtDateTime(lastRun.created_at)}`,
      onClick: () => onNavigate('runs'),
    },
  ]

  const taskCards: TaskCardData[] = [
    {
      key: 'review', title: '批量审核建议', num: overview.pending_suggestions,
      icon: <CheckCircleOutlined />, accent: '#d97706', accentBg: '#fffbeb',
      desc: `本批共 ${fmtQty(lastRun.suggestions)} 条建议，其中 ${fmtQty(overview.pending_suggestions)} 条待审核；审核通过后可转单或执行。`,
      buttonText: '去审核', primary: true, go: '缺口与建议 →',
      onClick: () => onNavigate('shortage'),
    },
    {
      key: 'exceptions', title: '处理拖期例外', num: overview.pending_exceptions,
      icon: <WarningOutlined />, accent: '#dc2626', accentBg: '#fef2f2',
      desc: `本批共 ${fmtQty(lastRun.exceptions)} 条例外，其中 ${fmtQty(overview.pending_exceptions)} 条待处理；逾期单据不计入覆盖，需改期或关闭。`,
      buttonText: '去处理', go: '例外 →',
      onClick: () => onNavigate('exceptions'),
    },
    {
      key: 'requisition', title: '转采购申请',
      icon: <ShoppingCartOutlined />, accent: '#5b5bd6', accentBg: '#eef0fe',
      desc: '已通过的外购建议可在「采购申请单」页转单，并跟踪后续审批进度。',
      buttonText: '去转单', go: '采购申请单 →',
      onClick: () => navigate('/purchase-requisitions'),
    },
    {
      key: 'k3', title: 'K3 差异排查',
      icon: <SyncOutlined />, accent: '#0284c7', accentBg: '#f0f9ff',
      desc: '打开「批次与对比」查看最新批次的数据体检与 K3 对比差异，定位数据问题。',
      buttonText: '去排查', go: '批次与对比 →',
      onClick: () => onNavigate('runs'),
    },
  ]

  return (
    <div>
      {infoStrip}

      <Row gutter={[12, 12]} style={{ marginBottom: 14 }}>
        {statCards.map((card) => (
          <Col key={card.key} flex="1 1 190px"><StatCardView card={card} /></Col>
        ))}
      </Row>

      <div className="sc-card-head" style={{ padding: '0 0 10px', borderBottom: 'none' }}>
        <h3>今日先做这几件事</h3>
        <span className="sc-hint">按批次结果排的 4 个动作</span>
      </div>
      <Row gutter={[12, 12]} style={{ marginBottom: 14 }}>
        {taskCards.map((card) => (
          <Col key={card.key} xs={24} sm={12} xl={6}><TaskCardView card={card} /></Col>
        ))}
      </Row>

      <div className="sc-card">
        <div className="sc-card-head">
          <h3>缺口 TOP</h3>
          <span className="sc-hint">批次 {lastRun.run_no} · 按缺口数量降序 TOP {overview.top_gaps.length}</span>
          <span className="sc-sub" style={{ marginLeft: 'auto' }}>
            待审核 {countByStatus('pending')} · 已通过 {countByStatus('approved')} · 已转单 {countByStatus('converted')}
          </span>
        </div>
        <Table<TopGap>
          rowKey="id"
          dataSource={overview.top_gaps}
          columns={columns}
          loading={loading}
          size="small"
          pagination={false}
          scroll={{ x: 1080 }}
          locale={{ emptyText: '本批次无待审核缺口：所有需求已被库存/在途单据覆盖，无需新增采购或生产。' }}
        />
      </div>

      <div className="sc-card" style={{ marginTop: 14, padding: '13px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <div className="sc-stat-icon" style={{ background: '#f0fdf4', color: '#16a34a' }}><PlayCircleOutlined /></div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            最近批次 <span className="sc-mono">{lastRun.run_no}</span>
            <Tag color={runStatus.color}>{runStatus.label}</Tag>
          </div>
          <div className="sc-sub" style={{ marginTop: 2 }}>
            {fmtDateTime(lastRun.created_at)} · 耗时 {lastRun.duration_sec != null ? `${lastRun.duration_sec}s` : '—'} · 生成建议 {fmtQty(lastRun.suggestions)} 条 / 例外 {fmtQty(lastRun.exceptions)} 条 · 下次自动运算 每天 02:00
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
          <Button size="small" onClick={() => onNavigate('runs')}>批次与对比</Button>
          {canRun && (
            <Button size="small" type="primary" icon={<PlayCircleOutlined />} loading={running} onClick={runNow}>立即运算</Button>
          )}
        </div>
      </div>
    </div>
  )
}
