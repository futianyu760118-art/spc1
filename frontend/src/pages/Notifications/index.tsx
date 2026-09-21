import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Badge, Button, Empty, Pagination, Spin, Tag, Tooltip, message } from 'antd'
import {
  SoundOutlined, SettingOutlined, AppstoreOutlined, WarningOutlined,
  MessageOutlined, AuditOutlined, BellOutlined, CheckOutlined, ReloadOutlined,
  RightOutlined,
} from '@ant-design/icons'
import { notificationApi } from '../../services/api'
import { useAuthStore } from '../../store/auth'

interface NotifItem {
  id: number
  type: string
  title: string
  content?: string | null
  ref_type?: string | null
  ref_id?: number | null
  priority: string
  is_read: boolean
  read_at?: string | null
  created_at: string
}

const TYPE_DEFS = [
  { key: 'announcement', label: '公告', icon: SoundOutlined, color: '#5b5bd6', bg: '#eef0fe' },
  { key: 'system', label: '系统', icon: SettingOutlined, color: '#0284c7', bg: '#f0f9ff' },
  { key: 'material_alert', label: '物料提醒', icon: AppstoreOutlined, color: '#d97706', bg: '#fffbeb' },
  { key: 'exception_alert', label: '异常提醒', icon: WarningOutlined, color: '#dc2626', bg: '#fef2f2' },
  { key: 'feedback', label: '问题反馈', icon: MessageOutlined, color: '#8b5cf6', bg: '#f5f3ff' },
  { key: 'stock_check_audit', label: '盘点审核', icon: AuditOutlined, color: '#16a34a', bg: '#f0fdf4' },
] as const

const typeDef = (type: string) => TYPE_DEFS.find(t => t.key === type)

const PRIORITY_DEFS: Record<string, { label: string; color: string }> = {
  urgent: { label: '紧急', color: 'red' },
  important: { label: '重要', color: 'gold' },
  normal: { label: '普通', color: 'default' },
}

function jumpTarget(n: NotifItem): { label: string; path: string } | null {
  if (n.ref_type === 'stock_check' && n.ref_id) return { label: `盘点单 #${n.ref_id}`, path: `/stock-check/${n.ref_id}` }
  if (n.type === 'feedback' && n.ref_id) return { label: `反馈单 #${n.ref_id}`, path: `/basicdata/feedback?id=${n.ref_id}` }
  if (n.ref_type === 'purchase_order') return { label: '采购到料计划', path: '/purchase-plan' }
  if (n.type === 'exception_alert') return { label: '异常总池', path: '/issues' }
  return null
}

export default function Notifications() {
  const navigate = useNavigate()
  const originalToken = useAuthStore((s: any) => s.originalToken)

  const [filter, setFilter] = useState<string>('all') // all | unread | <type>
  const [items, setItems] = useState<NotifItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [unreadTotal, setUnreadTotal] = useState(0)
  const [unreadByType, setUnreadByType] = useState<Record<string, number>>({})
  const listRef = useRef<HTMLDivElement>(null)

  const fetchCounts = useCallback(async () => {
    try {
      const res: any = await notificationApi.unreadCount()
      setUnreadTotal(res.data?.total || 0)
      setUnreadByType(res.data?.by_type || {})
    } catch { /* silent */ }
  }, [])

  const fetchList = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, any> = { page, page_size: 20 }
      if (filter === 'unread') params.is_read = false
      else if (filter !== 'all') params.type = filter
      const res: any = await notificationApi.list(params)
      setItems(res.data?.items || [])
      setTotal(res.data?.total || 0)
    } catch { /* handled by interceptor */ }
    setLoading(false)
  }, [filter, page])

  useEffect(() => { fetchCounts() }, [fetchCounts])
  useEffect(() => { fetchList() }, [fetchList])

  // SSE 实时：未读数或列表变化时静默刷新（创建/已读都会触发 unread 事件）
  useEffect(() => {
    if (!originalToken) return
    let es: EventSource | null = null
    try {
      es = new EventSource(`/api/v1/notifications/stream?token=${encodeURIComponent(originalToken)}`)
    } catch { return }
    es.addEventListener('unread', () => {
      fetchCounts()
      fetchList()
    })
    return () => { try { es?.close() } catch { /* silent */ } }
  }, [originalToken, fetchCounts, fetchList])

  const changeFilter = (key: string) => {
    setFilter(key)
    setPage(1)
    setSelectedId(null)
    listRef.current?.scrollTo({ top: 0 })
  }

  const openDetail = async (n: NotifItem) => {
    setSelectedId(n.id)
    if (!n.is_read) {
      try {
        await notificationApi.markRead(n.id)
        setItems(prev => prev.map(x => x.id === n.id ? { ...x, is_read: true } : x))
        setUnreadByType(prev => ({ ...prev, [n.type]: Math.max(0, (prev[n.type] || 0) - 1) }))
        setUnreadTotal(v => Math.max(0, v - 1))
      } catch { /* silent */ }
    }
  }

  const handleMarkAllRead = async () => {
    try {
      await notificationApi.markAllRead()
      message.success('已全部标记为已读')
      setItems(prev => prev.map(x => ({ ...x, is_read: true })))
      setUnreadByType({})
      setUnreadTotal(0)
    } catch { /* handled by interceptor */ }
  }

  const selected = useMemo(() => items.find(n => n.id === selectedId) || null, [items, selectedId])

  const navItem = (key: string, icon: React.ReactNode, label: string, count?: number, hotCount?: number) => (
    <div
      onClick={() => changeFilter(key)}
      className={`flex items-center gap-2 h-9 px-3 rounded-lg cursor-pointer text-[13px] transition-colors ${
        filter === key ? 'bg-[#eef0fe] text-[#4c4dc2] font-medium' : 'text-slate-600 hover:bg-slate-100'
      }`}
    >
      <span className="opacity-70">{icon}</span>
      <span>{label}</span>
      {hotCount !== undefined && hotCount > 0 && (
        <span className="ml-auto min-w-[16px] h-4 px-1 rounded-full bg-red-600 text-white text-[10px] font-semibold leading-4 text-center tabular-nums">{hotCount}</span>
      )}
      {hotCount === undefined && count !== undefined && count > 0 && (
        <span className="ml-auto text-[10.5px] text-slate-400 tabular-nums">{count}</span>
      )}
    </div>
  )

  return (
    <div className="flex flex-col h-full" style={{ margin: '-16px -24px -24px', padding: '16px 24px 24px' }}>
      <div className="flex items-center gap-3 mb-3">
        <h1 className="text-[20px] font-semibold m-0">站内信</h1>
        <span className="text-xs text-slate-400">公告 / 系统 / 物料与异常提醒 / 反馈 / 盘点审核 统一收口</span>
        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-slate-400 tabular-nums">
            {unreadTotal > 0 ? <><span className="text-red-600 font-semibold text-base">{unreadTotal}</span> 条未读</> : '无未读消息'}
          </span>
          <Button size="small" icon={<CheckOutlined />} onClick={handleMarkAllRead} disabled={unreadTotal === 0}>全部已读</Button>
          <Tooltip title="刷新">
            <Button size="small" icon={<ReloadOutlined />} onClick={() => { fetchCounts(); fetchList() }} />
          </Tooltip>
        </div>
      </div>

      <div className="flex flex-1 min-h-0 bg-white border border-slate-200 rounded-[10px] shadow-sm overflow-hidden">
        {/* 左：类型导航 */}
        <div className="w-[190px] shrink-0 border-r border-slate-100 p-2 flex flex-col overflow-y-auto">
          <div className="text-[11px] text-slate-400 px-3 pt-1.5 pb-2">视图</div>
          {navItem('all', <AppstoreOutlined />, '全部消息', total)}
          {navItem('unread', <BellOutlined />, '仅看未读', undefined, unreadTotal)}
          <div className="text-[11px] text-slate-400 px-3 pt-3 pb-2">分类</div>
          {TYPE_DEFS.map(t => {
            const Icon = t.icon
            return navItem(t.key, <Icon />, t.label, undefined, unreadByType[t.key] || 0)
          })}
        </div>

        {/* 中：消息列表 */}
        <div className="flex-1 min-w-0 flex flex-col">
          <div ref={listRef} className="flex-1 overflow-y-auto">
            <Spin spinning={loading}>
              {items.length === 0 && !loading ? (
                <Empty className="mt-16" description="暂无消息" />
              ) : (
                items.map(n => {
                  const td = typeDef(n.type)
                  const Icon = td?.icon || BellOutlined
                  const active = n.id === selectedId
                  return (
                    <div
                      key={n.id}
                      onClick={() => openDetail(n)}
                      className={`flex gap-3 items-start px-4 py-3 border-b border-slate-100 cursor-pointer transition-colors ${
                        active ? 'bg-[#eef0fe] shadow-[inset_2px_0_0_#5b5bd6]' : 'hover:bg-slate-50'
                      } ${!n.is_read ? '' : 'opacity-70'}`}
                    >
                      <div className="w-[30px] h-[30px] rounded-lg flex items-center justify-center shrink-0" style={{ background: td?.bg || '#f1f5f9', color: td?.color || '#64748b' }}>
                        <Icon style={{ fontSize: 15 }} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          {!n.is_read && <span className="w-[7px] h-[7px] rounded-full bg-[#5b5bd6] shadow-[0_0_0_3px_rgba(91,91,214,0.15)] shrink-0" />}
                          <span className={`text-[13px] truncate ${!n.is_read ? 'font-semibold text-slate-900' : 'text-slate-700'}`}>{n.title}</span>
                          {n.priority === 'urgent' && <Tag color="red" style={{ marginInlineEnd: 0, fontSize: 11, lineHeight: '18px' }}>紧急</Tag>}
                          {n.priority === 'important' && <Tag color="gold" style={{ marginInlineEnd: 0, fontSize: 11, lineHeight: '18px' }}>重要</Tag>}
                        </div>
                        <div className="text-xs text-slate-400 mt-0.5 truncate">{n.content || '—'}</div>
                      </div>
                      <div className="text-[11px] text-slate-400 shrink-0 tabular-nums mt-1">{n.created_at}</div>
                    </div>
                  )
                })
              )}
            </Spin>
          </div>
          <div className="border-t border-slate-100 px-4 py-2 flex justify-between items-center">
            <span className="text-xs text-slate-400 tabular-nums">
              {filter === 'unread' ? `未读 ${total} 条` : filter === 'all' ? `共 ${total} 条` : `${typeDef(filter)?.label || ''} ${total} 条`}
            </span>
            <Pagination size="small" current={page} pageSize={20} total={total} showSizeChanger={false} onChange={p => { setPage(p); listRef.current?.scrollTo({ top: 0 }) }} />
          </div>
        </div>

        {/* 右：详情栏 */}
        <div className="w-[360px] shrink-0 border-l border-slate-100 overflow-y-auto">
          {!selected ? (
            <Empty className="mt-24" description="点击左侧消息查看详情" />
          ) : (() => {
            const td = typeDef(selected.type)
            const Icon = td?.icon || BellOutlined
            const jump = jumpTarget(selected)
            const pr = PRIORITY_DEFS[selected.priority] || PRIORITY_DEFS.normal
            return (
              <div className="p-5">
                <div className="flex gap-1.5 items-center">
                  <Tag style={{ color: td?.color, background: td?.bg, borderColor: 'transparent', fontSize: 11.5 }}>{td?.label || selected.type}</Tag>
                  {selected.priority !== 'normal' && <Tag color={pr.color} style={{ marginInlineEnd: 0, fontSize: 11.5 }}>{pr.label}</Tag>}
                  {selected.is_read && <Tag style={{ marginInlineEnd: 0, fontSize: 11.5 }} color="default">已读</Tag>}
                </div>
                <h2 className="text-base font-semibold leading-relaxed mt-3 mb-1">{selected.title}</h2>
                <div className="flex gap-3 flex-wrap text-[11.5px] text-slate-400 mb-3">
                  <span>{selected.created_at}</span>
                  {td && <span>类型：{td.label}</span>}
                </div>
                <div className="text-[13px] leading-[1.9] text-slate-800 whitespace-pre-line pb-4 border-b border-slate-100">
                  {selected.content || '（无正文）'}
                </div>
                {jump && (
                  <div className="mt-4">
                    <Button type="primary" size="small" onClick={() => navigate(jump.path)}>
                      打开{jump.label}<RightOutlined style={{ fontSize: 11 }} />
                    </Button>
                  </div>
                )}
              </div>
            )
          })()}
        </div>
      </div>
    </div>
  )
}
