import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Dialog, InfiniteScroll, PullToRefresh, Toast } from 'antd-mobile'
import { notificationApi } from '@/services/api'
import { formatNotificationTime } from '@/utils/notificationTime'
import NavBarSimple from '../components/NavBarSimple'
import SegTabs from '../components/SegTabs'
import MIcon from '../components/MIcon'
import MDialog from '../components/MDialog'
import { EmptyState, SkeletonCards } from '../components/Feedback'
import { useNotificationRefresh } from '../hooks/useNotificationRefresh'

interface NotifItem {
  id: number
  type: string
  title: string
  content?: string | null
  ref_type?: string | null
  ref_id?: number | null
  sender_name?: string | null
  priority: string
  is_read: boolean
  created_at: string
}

const PAGE_SIZE = 20

interface IconDef {
  icon: string
  bg: string
  color: string
}

const TYPE_ICONS: Record<string, IconDef> = {
  approval_pending: { icon: 'check', bg: '#eef0fe', color: '#4c4dc2' },
  approval_timeout: { icon: 'warn', bg: '#fef2f2', color: '#dc2626' },
  approval_result: { icon: 'check', bg: '#f0fdf4', color: '#16a34a' },
  announcement: { icon: 'bell', bg: '#eef0fe', color: '#4c4dc2' },
  stock_check_audit: { icon: 'clipboard', bg: '#f0fdf4', color: '#16a34a' },
  stock_check_appeal: { icon: 'clipboard', bg: '#dbeafe', color: '#1d4ed8' },
  material_alert: { icon: 'box', bg: '#fffbeb', color: '#d97706' },
  exception_alert: { icon: 'warn', bg: '#fef2f2', color: '#dc2626' },
  feedback: { icon: 'bell', bg: '#f5f3ff', color: '#8b5cf6' },
  feedback_alert: { icon: 'bell', bg: '#f5f3ff', color: '#8b5cf6' },
}
const DEFAULT_ICON: IconDef = { icon: 'bell', bg: '#f1f5f9', color: '#64748b' }
const PRIORITY_LABEL: Record<string, string> = { urgent: '紧急', high: '重要', important: '重要' }

function isApprovalNotify(n: NotifItem) {
  if (n.type === 'approval_pending' || n.type === 'approval_timeout' || n.type === 'approval_result') return true
  return n.type === 'supplier_claim' && n.title.startsWith('[索赔单] 待您审批')
}

function mobileJumpTarget(n: NotifItem): string | null {
  if (isApprovalNotify(n) && n.ref_type && n.ref_id) {
    return `/approvals/items/${encodeURIComponent(n.ref_type)}/${n.ref_id}`
  }
  if (n.ref_type === 'stock_check' && n.ref_id) return `/stock-check/${n.ref_id}`
  return null
}

export default function NotificationsPage() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState<'all' | 'unread'>('all')
  const [items, setItems] = useState<NotifItem[]>([])
  const [total, setTotal] = useState(0)
  const [unread, setUnread] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [detail, setDetail] = useState<NotifItem | null>(null)

  const fetchCounts = useCallback(async () => {
    try {
      const res: any = await notificationApi.unreadCount()
      setUnread(Number(res.data?.total || 0))
    } catch {
      // 未读数失败不阻塞列表
    }
  }, [])

  const loadFirst = useCallback(async () => {
    setFailed(false)
    setLoading(true)
    try {
      const res: any = await notificationApi.list({
        page: 1,
        page_size: PAGE_SIZE,
        ...(filter === 'unread' ? { is_read: false } : {}),
      })
      setItems(res.data?.items || [])
      setTotal(Number(res.data?.total || 0))
      setPage(1)
    } catch {
      setFailed(true)
    } finally {
      setLoading(false)
    }
  }, [filter])

  const loadMore = useCallback(async () => {
    const next = page + 1
    try {
      const res: any = await notificationApi.list({
        page: next,
        page_size: PAGE_SIZE,
        ...(filter === 'unread' ? { is_read: false } : {}),
      })
      setItems((prev) => [...prev, ...(res.data?.items || [])])
      setTotal(Number(res.data?.total || 0))
      setPage(next)
    } catch {
      // 静默失败，InfiniteScroll 可再次触发
    }
  }, [filter, page])

  useEffect(() => { loadFirst() }, [loadFirst])
  useEffect(() => { fetchCounts() }, [fetchCounts])

  const refreshAll = useCallback(async () => {
    await Promise.all([fetchCounts(), loadFirst()])
  }, [fetchCounts, loadFirst])

  useNotificationRefresh(true, refreshAll)

  const openItem = (n: NotifItem) => {
    if (!n.is_read) {
      if (filter === 'unread') {
        setItems((prev) => prev.filter((x) => x.id !== n.id))
        setTotal((v) => Math.max(0, v - 1))
      } else {
        setItems((prev) => prev.map((x) => (x.id === n.id ? { ...x, is_read: true } : x)))
      }
      setUnread((v) => Math.max(0, v - 1))
      notificationApi.markRead(n.id).catch(() => {})
    }
    const target = mobileJumpTarget(n)
    if (target) {
      navigate(target)
      return
    }
    setDetail(n)
  }

  const handleMarkAll = () => {
    if (unread === 0) return
    Dialog.confirm({
      content: '确定将全部消息标记为已读吗？',
      onConfirm: async () => {
        try {
          await notificationApi.markAllRead()
          setUnread(0)
          Toast.show({ content: '已全部标记为已读' })
          await Promise.all([fetchCounts(), loadFirst()])
        } catch {
          // 全局拦截器已提示
        }
      },
    })
  }

  return (
    <div className="m-page m-page--full">
      <NavBarSimple
        title="消息中心"
        onBack={() => navigate('/')}
        right={(
          <button className="msg-readall" disabled={unread === 0} onClick={handleMarkAll}>
            全部已读
          </button>
        )}
      />

      <div className="lk-tabs">
        <SegTabs
          items={[
            { key: 'all', label: '全部' },
            { key: 'unread', label: '未读', count: unread, red: true },
          ]}
          active={filter}
          onChange={(key) => setFilter(key as 'all' | 'unread')}
        />
      </div>

      <div className="m-page__scroll">
        <PullToRefresh onRefresh={refreshAll}>
          {loading && items.length === 0 && <SkeletonCards count={4} />}
          {failed && <EmptyState icon="warn" text="加载失败，下拉重试" />}
          {!loading && !failed && items.length === 0 && (
            <EmptyState text={filter === 'unread' ? '没有未读消息' : '暂无消息'} />
          )}
          {items.map((n) => {
            const ico = TYPE_ICONS[n.type] || DEFAULT_ICON
            return (
              <button key={n.id} className={`msg-row${n.is_read ? '' : ' unread'}`} onClick={() => openItem(n)}>
                <span className="msg-row__ico" style={{ background: ico.bg, color: ico.color }}>
                  <MIcon name={ico.icon} size={18} />
                </span>
                <span className="msg-row__main">
                  <span className="msg-row__title">
                    {!n.is_read && <i className="msg-row__dot" />}
                    <span className="msg-row__tt">{n.title}</span>
                    {PRIORITY_LABEL[n.priority] && (
                      <span className="m-chip m-chip--high">{PRIORITY_LABEL[n.priority]}</span>
                    )}
                  </span>
                  {n.content && (
                    <span className="msg-row__snip">
                      {n.sender_name ? `${n.sender_name}：` : ''}{n.content}
                    </span>
                  )}
                </span>
                <span className="msg-row__side">
                  <span className="msg-row__time">{formatNotificationTime(n.created_at)}</span>
                  {mobileJumpTarget(n) && <MIcon name="chev" size={14} />}
                </span>
              </button>
            )
          })}
          {!loading && !failed && (
            <InfiniteScroll loadMore={loadMore} hasMore={items.length < total} />
          )}
          <div style={{ height: 20 }} />
        </PullToRefresh>
      </div>

      <MDialog
        visible={!!detail}
        title={detail?.title || '消息详情'}
        onClose={() => setDetail(null)}
        actions={[{ label: '关闭', kind: 'plain', onClick: () => setDetail(null) }]}
      >
        {detail && (
          <>
            <div className="msg-detail-meta">
              <span>{formatNotificationTime(detail.created_at)}</span>
              {detail.sender_name && <span>{detail.sender_name}</span>}
            </div>
            <div className="msg-detail-body">{detail.content || '（无正文）'}</div>
          </>
        )}
      </MDialog>
    </div>
  )
}
