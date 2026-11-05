import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { PullToRefresh, ErrorBlock, SpinLoading } from 'antd-mobile'
import { dashboardApi, materialApi, notificationApi } from '@/services/api'
import { approvalApi, type ApprovalItem } from '@/services/approval'
import { useAuthStore } from '@/store/auth'
import MIcon from '../components/MIcon'
import { useNotificationRefresh } from '../hooks/useNotificationRefresh'

interface Summary { total_orders: number; red_count: number; yellow_count: number; blue_count: number; green_count: number }

interface RollingDay { date: string; due_count: number; red_count: number; yellow_count: number; blue_count: number }

interface DueOrder {
  order_no: string
  line_no: string | null
  customer: string | null
  product_name: string | null
  promised_date: string | null
  risk_level: string | null
  owner: string | null
}

const RISK_COLORS: Record<string, string> = { red: '#ef4444', yellow: '#f59e0b', blue: '#3b82f6', green: '#10b981' }
const RISK_LABELS: Record<string, string> = { red: '高风险', yellow: '中风险', blue: '低风险', green: '正常' }
const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六']

interface TodoEntry {
  kind: 'approval'
  key: string
  kindLabel: string
  title: string
  subtitle: string
  chip?: { text: string; cls: string }
  path: string
}

const WAIT_RANK: Record<string, number> = { overdue: 0, soon: 1, normal: 2 }

function buildApprovalTodos(items: ApprovalItem[]): TodoEntry[] {
  return [...items]
    .sort((a, b) => {
      const rank = (WAIT_RANK[a.wait_level || 'normal'] ?? 2) - (WAIT_RANK[b.wait_level || 'normal'] ?? 2)
      return rank !== 0 ? rank : (b.wait_hours ?? 0) - (a.wait_hours ?? 0)
    })
    .map((it) => ({
      kind: 'approval',
      key: `${it.biz_type}-${it.id}`,
      kindLabel: '审批',
      title: [it.biz_name, it.no].filter(Boolean).join(' · ') || it.title || '待审批单据',
      subtitle: [
        it.summary,
        it.title && (!it.no || !it.title.includes(it.no)) ? it.title : '',
        it.applicant && `申请人 ${it.applicant}`,
        it.current_node,
      ].filter(Boolean).join(' · '),
      chip: it.wait_level === 'overdue'
        ? { text: `已超时 ${it.wait_hours ?? '-'} 小时`, cls: 'm-chip--high' }
        : it.wait_level === 'soon'
          ? { text: `已等待 ${it.wait_hours ?? '-'} 小时`, cls: 'm-chip--mid' }
          : undefined,
      path: `/approvals/items/${encodeURIComponent(it.biz_type)}/${it.id}`,
    }))
}

interface AppEntry {
  key: string
  title: string
  icon: string
  path: string
  perm?: readonly [string, string]
}

const APP_GROUPS: Array<{ group: string; items: AppEntry[] }> = [
  {
    group: '智能仓储',
    items: [
      { key: 'scan-count', title: '扫码盘点', icon: 'scan', path: '/scan-count', perm: ['materials.stock_check', 'read'] },
      { key: 'stock-check', title: '物料盘点', icon: 'clipboard', path: '/stock-check', perm: ['materials.stock_check', 'read'] },
    ],
  },
  {
    group: '个人中心',
    items: [
      { key: 'notifications', title: '消息中心', icon: 'bell', path: '/notifications', perm: ['topbar.notifications', 'read'] },
      { key: 'me', title: '我的', icon: 'user', path: '/me' },
    ],
  },
]

function AppGrid({ unread }: { unread: number }) {
  const navigate = useNavigate()
  const hasPermission = useAuthStore((s) => s.hasPermission)
  const groups = APP_GROUPS
    .map((g) => ({ ...g, items: g.items.filter((e) => !e.perm || hasPermission(e.perm[0], e.perm[1])) }))
    .filter((g) => g.items.length > 0)
  if (groups.length === 0) return null
  return (
    <div className="app-sec">
      {groups.map((g) => (
        <div key={g.group}>
          <div className="app-group">{g.group}</div>
          <div className="app-grid">
            {g.items.map((e) => {
              const badge = e.key === 'notifications' ? unread : 0
              return (
                <button className="app" key={e.key} onClick={() => navigate(e.path)}>
                  <div className="app__ic">
                    <MIcon name={e.icon} size={24} />
                    {badge > 0 && <span className="app__badge">{badge > 99 ? '99+' : badge}</span>}
                  </div>
                  <span>{e.title}</span>
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}

export default function WorkbenchPage() {
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.currentUser)
  const [summary, setSummary] = useState<Summary | null>(null)
  const [rolling, setRolling] = useState<RollingDay[]>([])
  const [dueOrders, setDueOrders] = useState<DueOrder[]>([])
  const [activeChecks, setActiveChecks] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [insight, setInsight] = useState<'dist' | 'trend'>('dist')
  const [todoExpanded, setTodoExpanded] = useState(false)
  const canReadNotifications = useAuthStore((s) => s.hasPermission('topbar.notifications', 'read'))
  const canReadApprovals = useAuthStore((s) => s.hasPermission('approval.pending', 'read'))
  const [unread, setUnread] = useState(0)
  const [todos, setTodos] = useState<ApprovalItem[]>([])
  const [todoTotal, setTodoTotal] = useState(0)

  const fetchUnread = useCallback(async () => {
    if (!canReadNotifications) return
    try {
      const res: any = await notificationApi.unreadCount()
      setUnread(Number(res.data?.total || 0))
    } catch {
      // 角标失败不影响工作台主体
    }
  }, [canReadNotifications])

  const load = useCallback(async () => {
    setFailed(false)
    try {
      const [s, r, d, c, t] = await Promise.all([
        dashboardApi.getSummary(),
        dashboardApi.getRollingRisk(),
        dashboardApi.getTodayDueOrders({ page: 1, page_size: 50 }),
        materialApi.getRecentStockChecks({ page: 1, page_size: 1, status: 'open,in_progress' }).catch(() => null),
        canReadApprovals
          ? approvalApi.pending({ page: 1, page_size: 50 }).catch(() => null)
          : Promise.resolve(null),
      ])
      setSummary((s as any).data)
      setRolling(((r as any).data?.days || []) as RollingDay[])
      setDueOrders(((d as any).data?.items || (d as any).data || []) as DueOrder[])
      setActiveChecks(c ? Number((c as any).data?.total ?? 0) : null)
      if (t) {
        const todoData = (t as any).data
        setTodos(todoData?.items || [])
        setTodoTotal(Number(todoData?.total ?? (todoData?.items || []).length))
      }
    } catch {
      setFailed(true)
    } finally {
      setLoading(false)
    }
  }, [canReadApprovals])

  useEffect(() => { load() }, [load])
  useEffect(() => { fetchUnread() }, [fetchUnread])
  useNotificationRefresh(canReadNotifications, fetchUnread)

  const now = new Date()
  const hour = now.getHours()
  const greet = hour < 12 ? '上午好' : hour < 18 ? '下午好' : '晚上好'
  const displayName = user && 'display_name' in user ? user.display_name || user.username : ''
  const due14 = rolling.reduce((a, b) => a + (b.due_count || 0), 0)
  const todoEntries = buildApprovalTodos(todos)
  const shownTodos = todoExpanded ? todoEntries : todoEntries.slice(0, 3)

  const trendMax = Math.max(1, ...rolling.map((d) => Math.max(d.red_count, d.yellow_count, d.due_count)))
  const trendTotals = rolling.reduce(
    (acc, d) => ({ r: acc.r + d.red_count, y: acc.y + d.yellow_count, d: acc.d + d.due_count }),
    { r: 0, y: 0, d: 0 },
  )

  return (
    <div className="m-page">
      <PullToRefresh onRefresh={load}>
        <header className="wb-head">
          <div>
            <div className="wb-date">{`${now.getMonth() + 1}月${now.getDate()}日 星期${WEEKDAYS[now.getDay()]}`}</div>
            <div className="wb-greet">{`${greet}，${displayName || ''}`}</div>
          </div>
          <button className="wb-avatar" onClick={() => navigate('/me')}>
            {(displayName || '?').slice(0, 1)}
          </button>
        </header>

        {loading && <div style={{ textAlign: 'center', padding: 40 }}><SpinLoading color="primary" /></div>}
        {failed && <ErrorBlock status="empty" title="加载失败" description="下拉重试" />}

        {!loading && !failed && (
          <>
            <div className="kpi-band">
              <button className="kpi" onClick={() => navigate('/stock-check')}>
                <div className="kpi__dot" style={{ background: '#eef2ff', color: '#4f46e5' }}>
                  <MIcon name="clipboard" size={13} />
                </div>
                <div className="kpi__v">{activeChecks ?? '—'}</div>
                <div className="kpi__l">进行中盘点</div>
              </button>
              <div className="kpi">
                <div className="kpi__dot" style={{ background: '#fef2f2', color: '#dc2626' }}>
                  <MIcon name="cal" size={13} />
                </div>
                <div className="kpi__v">{dueOrders.length}</div>
                <div className="kpi__l">今日到期</div>
              </div>
              <div className="kpi">
                <div className="kpi__dot" style={{ background: '#fff7ed', color: '#ea580c' }}>
                  <MIcon name="warn" size={13} />
                </div>
                <div className="kpi__v">{summary?.red_count ?? '—'}</div>
                <div className="kpi__l">高风险项</div>
              </div>
              <div className="kpi">
                <div className="kpi__dot" style={{ background: '#eff6ff', color: '#2563eb' }}>
                  <MIcon name="flag" size={13} />
                </div>
                <div className="kpi__v">{due14}</div>
                <div className="kpi__l">14天内到期</div>
              </div>
            </div>

            {canReadApprovals && (
              <div className="m-card">
                <div className="m-card__title">
                  今日待办
                  {todoTotal > 0 && <span className="todo-total">共 {todoTotal} 项</span>}
                </div>
                {todoEntries.length === 0 ? (
                  <div className="m-empty" style={{ padding: '18px 0' }}>
                    <span>今日暂无待办</span>
                  </div>
                ) : (
                  <>
                    {shownTodos.map((t) => (
                      <button className="todo todo--btn" key={t.key} onClick={() => navigate(t.path)}>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div className="todo-no">
                            <span className="m-chip m-chip--progress">{t.kindLabel}</span>
                            <span className="todo-name">{t.title}</span>
                            {t.chip && <span className={`m-chip ${t.chip.cls}`}>{t.chip.text}</span>}
                          </div>
                          <div className="todo-sub">{t.subtitle || '-'}</div>
                        </div>
                        <span className="go"><MIcon name="chev" size={16} /></span>
                      </button>
                    ))}
                    {todoEntries.length > 3 && (
                      <button className="todo-more" onClick={() => setTodoExpanded((v) => !v)}>
                        {todoExpanded ? '收起' : `展开全部 ${todoEntries.length} 项`}
                        <span style={{ display: 'inline-flex', transform: todoExpanded ? 'rotate(180deg)' : 'none' }}>
                          <MIcon name="chev" size={14} />
                        </span>
                      </button>
                    )}
                  </>
                )}
              </div>
            )}

            {summary && summary.total_orders > 0 && (
              <div className="m-card">
                <div className="m-card__title" style={{ marginBottom: 8 }}>
                  风险洞察
                  <div className="m-seg" style={{ width: 170, marginLeft: 'auto' }}>
                    <button
                      className={`m-seg__item${insight === 'dist' ? ' active' : ''}`}
                      style={{ padding: '5px 0', fontSize: 12 }}
                      onClick={() => setInsight('dist')}
                    >
                      分布
                    </button>
                    <button
                      className={`m-seg__item${insight === 'trend' ? ' active' : ''}`}
                      style={{ padding: '5px 0', fontSize: 12 }}
                      onClick={() => setInsight('trend')}
                    >
                      14天趋势
                    </button>
                  </div>
                </div>
                {insight === 'dist' ? (
                  <>
                    <div className="dist-bar">
                      {(['red', 'yellow', 'blue', 'green'] as const).map((k) => (
                        <i key={k} style={{ flex: summary[`${k}_count` as keyof Summary] as number, background: RISK_COLORS[k] }} />
                      ))}
                    </div>
                    <div className="dist-lg">
                      {(['red', 'yellow', 'blue', 'green'] as const).map((k) => (
                        <span key={k}>
                          <i className="m-dot" style={{ background: RISK_COLORS[k] }} />
                          {RISK_LABELS[k]} <b>{summary[`${k}_count` as keyof Summary] as number}</b>
                        </span>
                      ))}
                      <span style={{ marginLeft: 'auto', color: 'var(--spc-text3)' }}>共 {summary.total_orders} 单</span>
                    </div>
                  </>
                ) : rolling.length > 0 ? (
                  <>
                    <div className="trend-wrap">
                      {rolling.map((d) => (
                        <div
                          className="trend-col"
                          key={d.date}
                          title={`${d.date} 到期${d.due_count} 红${d.red_count} 黄${d.yellow_count}`}
                        >
                          <i style={{ height: Math.max((d.red_count / trendMax) * 60, 3), background: '#ef4444' }} />
                          <i style={{ height: Math.max((d.yellow_count / trendMax) * 60, 3), background: '#f59e0b' }} />
                          <i style={{ height: Math.max((d.due_count / trendMax) * 60, 3), background: '#cbd5e1' }} />
                        </div>
                      ))}
                    </div>
                    <div className="trend-x">
                      <span>{rolling[0]?.date?.slice(5) || ''}</span>
                      <span>{rolling[rolling.length - 1]?.date?.slice(5) || ''}</span>
                    </div>
                    <div className="dist-lg" style={{ marginTop: 8 }}>
                      <span><i className="m-dot" style={{ background: '#ef4444' }} />红 <b>{trendTotals.r}</b></span>
                      <span><i className="m-dot" style={{ background: '#f59e0b' }} />黄 <b>{trendTotals.y}</b></span>
                      <span><i className="m-dot" style={{ background: '#cbd5e1' }} />到期 <b>{trendTotals.d}</b></span>
                    </div>
                  </>
                ) : (
                  <div className="m-empty"><span>暂无趋势数据</span></div>
                )}
              </div>
            )}
          </>
        )}

        <AppGrid unread={unread} />
      </PullToRefresh>
    </div>
  )
}
