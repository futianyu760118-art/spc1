import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Input, Modal, Select, Table, message } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, ClockCircleOutlined, SearchOutlined, UndoOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { approvalApi, type ApprovalItem, type ApprovalStats } from '../../../services/approval'
import { daysAgoISO } from '../../../utils'
import { useAuthStore } from '../../../store/auth'
import { getBusiness } from '../Create/businesses'
import ApprovalStatsCards from '../../../components/ApprovalStatsCards'
import type { WorkbenchTabProps } from './index'

const STATUS_TEXT: Record<string, string> = { draft: '草稿', pending: '审批中', approved: '已通过', rejected: '已驳回', recalled: '已撤回' }
const STATUS_TAG: Record<string, string> = { draft: 'sc-tag-plain', pending: 'sc-tag-kit', approved: 'sc-tag-done', rejected: 'sc-tag-danger', recalled: 'sc-tag-wait' }
const STATUS_KEYS = ['draft', 'pending', 'approved', 'rejected', 'recalled'] as const

export default function MySubmittedTab({ registerReload, onCount }: WorkbenchTabProps) {
  const navigate = useNavigate()
  const hasPermission = useAuthStore((s) => s.hasPermission) as (resource: string, action: string) => boolean
  const [items, setItems] = useState<ApprovalItem[]>([])
  const [winStats, setWinStats] = useState<ApprovalStats>({})
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState<string | undefined>(undefined)
  const [days, setDays] = useState(90)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [recallTarget, setRecallTarget] = useState<ApprovalItem | null>(null)
  const [recalling, setRecalling] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await approvalApi.submitted({
        page, page_size: 20, keyword: keyword || undefined, status,
        date_from: daysAgoISO(days),
      })
      setItems(res.data?.items || [])
      setTotal(res.data?.total || 0)
    } catch { /* 全局拦截器已提示 */ } finally { setLoading(false) }
  }, [keyword, status, days, page])
  useEffect(() => { load() }, [load])

  // chips / 统计卡取「时间窗口内、未加状态/关键词筛选」的口径
  const loadWinStats = useCallback(async () => {
    try {
      const res: any = await approvalApi.submitted({
        page: 1, page_size: 1, date_from: daysAgoISO(days),
      })
      const s = res.data?.stats || {}
      setWinStats(s)
      onCount('submitted', STATUS_KEYS.reduce((sum, k) => sum + (s[k] ?? 0), 0))
    } catch { /* 全局拦截器已提示 */ }
  }, [days, onCount])
  useEffect(() => { loadWinStats() }, [loadWinStats])

  useEffect(() => {
    registerReload('submitted', () => { load(); loadWinStats() })
    return () => registerReload('submitted', undefined)
  }, [load, loadWinStats, registerReload])

  const doRecall = async () => {
    if (!recallTarget) return
    setRecalling(true)
    try {
      const res: any = await approvalApi.recall(recallTarget.biz_type, recallTarget.id)
      message.success(res.message || '已撤回')
      setRecallTarget(null)
      load()
      loadWinStats()
    } catch { /* 全局拦截器已提示 */ } finally { setRecalling(false) }
  }

  const totalCount = STATUS_KEYS.reduce((sum, k) => sum + (winStats[k] ?? 0), 0)

  return (
    <div className="ac-pane">
      <ApprovalStatsCards cards={[
        { key: 'pending', label: '审批中', value: winStats.pending ?? 0, unit: '单', tone: 'info', icon: <ClockCircleOutlined /> },
        { key: 'approved', label: '已通过', value: winStats.approved ?? 0, unit: '单', tone: 'success', icon: <CheckCircleOutlined />, hint: '审批完成后单据归档' },
        { key: 'rejected', label: '已驳回', value: winStats.rejected ?? 0, unit: '单', tone: 'danger', icon: <CloseCircleOutlined />, hint: '可修改后重新提交' },
        { key: 'recalled', label: '已撤回', value: winStats.recalled ?? 0, unit: '单', icon: <UndoOutlined />, hint: '撤回后回到草稿' },
      ]} />
      <div className="sc-toolbar">
        <Input.Search allowClear placeholder="单号 / 标题" className="sc-search" style={{ width: 240 }}
          onSearch={v => { setPage(1); setKeyword(v) }} />
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <span className={`sc-chip${!status ? ' on' : ''}`} onClick={() => { setPage(1); setStatus(undefined) }}>
            全部 <span className="n">{totalCount}</span>
          </span>
          {STATUS_KEYS.map(k => (
            <span key={k} className={`sc-chip${status === k ? ' on' : ''}`}
              onClick={() => { setPage(1); setStatus(status === k ? undefined : k) }}>
              {STATUS_TEXT[k]} <span className="n">{winStats[k] ?? 0}</span>
            </span>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
          <Select value={days} onChange={v => { setPage(1); setDays(v) }} style={{ width: 110 }}
            options={[
              { value: 30, label: '近 30 天' },
              { value: 90, label: '近 90 天' },
              { value: 365, label: '近一年' },
            ]} />
        </div>
      </div>
      <Table<ApprovalItem> rowKey={r => `${r.biz_type}-${r.id}`} loading={loading} dataSource={items}
        scroll={{ x: 1100 }}
        locale={{ emptyText: (
          <div className="ac-empty">
            <div className="ac-empty-ico"><SearchOutlined /></div>
            <div className="ac-empty-title">暂无我发起的单据</div>
            <div className="ac-empty-sub">你提交的单据会出现在这里，可查看进度、撤回或重新提交</div>
          </div>
        ) }}
        pagination={{
          current: page, pageSize: 20, total, showSizeChanger: false,
          showTotal: t => `共 ${t} 条`, onChange: setPage,
        }}
        columns={[
          { title: '业务类型', width: 140, render: (_: any, r: ApprovalItem) => <span className="sc-tag sc-tag-prod">{r.biz_name}</span> },
          { title: '单号', width: 170, render: (_: any, r: ApprovalItem) => <span className="sc-mono">{r.no}</span> },
          { title: '标题', dataIndex: 'title', ellipsis: true },
          { title: '提交时间', width: 150, render: (_: any, r: ApprovalItem) => r.submitted_at ? dayjs(r.submitted_at).format('YYYY-MM-DD HH:mm') : '-' },
          { title: '当前节点', width: 130, render: (_: any, r: ApprovalItem) => r.current_node || '-' },
          { title: '整体状态', width: 100, render: (_: any, r: ApprovalItem) => (
            <span className={`sc-tag ${STATUS_TAG[r.status || ''] || 'sc-tag-wait'}`}>{STATUS_TEXT[r.status || ''] || r.status}</span>
          ) },
          { title: '操作', width: 190, fixed: 'right', render: (_: any, r: ApprovalItem) => {
            const biz = getBusiness(r.biz_type)
            const canEdit = !!biz && hasPermission(biz.permission[0], 'update')
            const canResubmit = r.status === 'rejected' || r.status === 'recalled'
            const centerEditPath = `/approvals/create/${r.biz_type}/${r.id}`
            return (
              <span className="sc-row-act">
                <Button size="small" type="link" onClick={() => navigate(`/approvals/items/${r.biz_type}/${r.id}`)}>查看</Button>
                {r.can_recall ? (
                  <Button size="small" type="link" danger onClick={() => setRecallTarget(r)}>撤回</Button>
                ) : null}
                {r.status === 'draft' && canEdit ? (
                  <Button size="small" type="link" onClick={() => navigate(centerEditPath)}>编辑</Button>
                ) : null}
                {canResubmit && canEdit ? (
                  <Button size="small" type="link" onClick={() => navigate(centerEditPath)}>重新提交</Button>
                ) : canResubmit && r.deep_link ? (
                  <Button size="small" type="link" onClick={() => window.open(r.deep_link, '_self')}>重新提交</Button>
                ) : null}
              </span>
            )
          } },
        ]} />

      <Modal title="撤回单据" open={!!recallTarget} confirmLoading={recalling}
        onOk={doRecall} onCancel={() => setRecallTarget(null)} okText="确认撤回" okButtonProps={{ danger: true }}>
        {recallTarget ? (
          <div className="ac-pick-list">
            <div className="ac-pick-item">
              <span className="sc-tag sc-tag-prod">{recallTarget.biz_name}</span>
              <span className="t">{recallTarget.no} · {recallTarget.title}</span>
            </div>
          </div>
        ) : null}
        <div className="f-warn">
          撤回后单据回到「草稿」状态，当前轮次已产生的审批记录保留留档；已进入下一节点或被他人处理时不可撤回。
        </div>
      </Modal>
    </div>
  )
}
