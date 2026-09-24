import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Input, Select, Table } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, FieldTimeOutlined, SearchOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { approvalApi, type ApprovalItem, type ApprovalStats } from '../../../services/approval'
import { daysAgoISO, mondayOf } from '../../../utils'
import ApprovalStatsCards from '../../../components/ApprovalStatsCards'
import type { WorkbenchTabProps } from './index'

const round1 = (v?: number | null) => (v == null ? null : Math.round(v * 10) / 10)

const STATUS_TAG: Record<string, { cls: string; text: string }> = {
  pending: { cls: 'sc-tag-kit', text: '审批中' },
  approved: { cls: 'sc-tag-done', text: '已通过' },
  rejected: { cls: 'sc-tag-danger', text: '已驳回' },
  recalled: { cls: 'sc-tag-wait', text: '已撤回' },
}

export default function MyApprovedTab({ registerReload, onCount }: WorkbenchTabProps) {
  const navigate = useNavigate()
  const [items, setItems] = useState<ApprovalItem[]>([])
  const [winStats, setWinStats] = useState<ApprovalStats>({})
  const [weekStats, setWeekStats] = useState<{ cur: ApprovalStats; prev: ApprovalStats } | null>(null)
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [action, setAction] = useState<'approve' | 'reject' | undefined>(undefined)
  const [days, setDays] = useState(30)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await approvalApi.approved({
        page, page_size: 20, keyword: keyword || undefined, action,
        date_from: daysAgoISO(days),
      })
      setItems(res.data?.items || [])
      setTotal(res.data?.total || 0)
    } catch { /* 全局拦截器已提示 */ } finally { setLoading(false) }
  }, [keyword, action, days, page])
  useEffect(() => { load() }, [load])

  // chips 计数取「时间窗口内、未加动作/关键词筛选」的口径，避免选中通过后驳回计数被清零
  const loadWinStats = useCallback(async () => {
    try {
      const res: any = await approvalApi.approved({
        page: 1, page_size: 1, date_from: daysAgoISO(days),
      })
      setWinStats(res.data?.stats || {})
    } catch { /* 全局拦截器已提示 */ }
  }, [days])
  useEffect(() => { loadWinStats() }, [loadWinStats])

  // 统计卡按周口径展示，并带「较上周」变化
  const loadWeekStats = useCallback(async () => {
    const thisMonday = mondayOf()
    const lastMonday = mondayOf(1)
    try {
      const [curRes, prevRes]: any[] = await Promise.all([
        approvalApi.approved({ page: 1, page_size: 1, date_from: thisMonday.format('YYYY-MM-DD') }),
        approvalApi.approved({
          page: 1, page_size: 1,
          date_from: lastMonday.format('YYYY-MM-DD'),
          date_to: thisMonday.subtract(1, 'day').format('YYYY-MM-DD'),
        }),
      ])
      const cur = curRes.data?.stats || {}
      const prev = prevRes.data?.stats || {}
      setWeekStats({ cur, prev })
      onCount('approved', cur.processed ?? 0)
    } catch { /* 全局拦截器已提示 */ }
  }, [onCount])
  useEffect(() => { loadWeekStats() }, [loadWeekStats])

  useEffect(() => {
    registerReload('approved', () => { load(); loadWinStats(); loadWeekStats() })
    return () => registerReload('approved', undefined)
  }, [load, loadWinStats, loadWeekStats, registerReload])

  const cur = weekStats?.cur || {}
  const prev = weekStats?.prev || {}
  const avgCur = round1(cur.avg_hours)
  const avgPrev = round1(prev.avg_hours)
  const passRate = cur.processed ? Math.round(((cur.passed ?? 0) / cur.processed) * 1000) / 10 : null

  return (
    <div className="ac-pane">
      <ApprovalStatsCards cards={[
        { key: 'processed', label: '本周已处理', value: cur.processed ?? 0, unit: '单', icon: <CheckCircleOutlined />,
          delta: { count: (cur.processed ?? 0) - (prev.processed ?? 0), unit: ' 单' } },
        { key: 'passed', label: '通过', value: cur.passed ?? 0, unit: '单', tone: 'success', icon: <CheckCircleOutlined />,
          hint: passRate == null ? '本周暂无处理' : `通过率 ${passRate}%` },
        { key: 'rejected', label: '驳回', value: cur.rejected ?? 0, unit: '单', tone: 'danger', icon: <CloseCircleOutlined />, hint: '均已退回申请人' },
        { key: 'avg', label: '平均处理时长', value: avgCur ?? '-', unit: '小时', tone: 'info', icon: <FieldTimeOutlined />,
          delta: avgCur != null && avgPrev != null ? { count: avgCur - avgPrev, unit: 'h', goodWhenDown: true } : undefined },
      ]} />
      <div className="sc-toolbar">
        <Input.Search allowClear placeholder="单号 / 标题 / 申请人" className="sc-search" style={{ width: 240 }}
          onSearch={v => { setPage(1); setKeyword(v) }} />
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <span className={`sc-chip${!action ? ' on' : ''}`} onClick={() => { setPage(1); setAction(undefined) }}>
            全部 <span className="n">{winStats.processed ?? 0}</span>
          </span>
          <span className={`sc-chip${action === 'approve' ? ' on' : ''}`}
            onClick={() => { setPage(1); setAction(action === 'approve' ? undefined : 'approve') }}>
            通过 <span className="n">{winStats.passed ?? 0}</span>
          </span>
          <span className={`sc-chip${action === 'reject' ? ' on' : ''}`}
            onClick={() => { setPage(1); setAction(action === 'reject' ? undefined : 'reject') }}>
            驳回 <span className="n">{winStats.rejected ?? 0}</span>
          </span>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
          <Select value={days} onChange={v => { setPage(1); setDays(v) }} style={{ width: 110 }}
            options={[
              { value: 7, label: '近 7 天' },
              { value: 30, label: '近 30 天' },
              { value: 90, label: '近 90 天' },
            ]} />
        </div>
      </div>
      <Table<ApprovalItem> rowKey={r => `${r.biz_type}-${r.id}`} loading={loading} dataSource={items}
        scroll={{ x: 1200 }}
        locale={{ emptyText: (
          <div className="ac-empty">
            <div className="ac-empty-ico"><SearchOutlined /></div>
            <div className="ac-empty-title">暂无审批记录</div>
            <div className="ac-empty-sub">你处理过的单据会出现在这里，可按动作与时间范围筛选</div>
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
          { title: '申请人', dataIndex: 'applicant', width: 100 },
          { title: '我的动作', width: 90, render: (_: any, r: ApprovalItem) => (
            <span className={`sc-tag ${r.my_action === 'approve' ? 'sc-tag-done' : 'sc-tag-danger'}`}>
              {r.my_action === 'approve' ? '通过' : '驳回'}
            </span>
          ) },
          { title: '我的意见', dataIndex: 'my_comment', ellipsis: true, render: (v?: string) => v || '-' },
          { title: '审批时间', width: 150, render: (_: any, r: ApprovalItem) => r.acted_at ? dayjs(r.acted_at).format('YYYY-MM-DD HH:mm') : '-' },
          { title: '单据状态', width: 100, render: (_: any, r: ApprovalItem) => {
            const st = STATUS_TAG[r.status || '']
            return st ? <span className={`sc-tag ${st.cls}`}>{st.text}</span> : <span className="sc-tag sc-tag-wait">{r.status || '-'}</span>
          } },
          { title: '操作', width: 80, fixed: 'right', render: (_: any, r: ApprovalItem) => (
            <span className="sc-row-act">
              <Button size="small" type="link" onClick={() => navigate(`/approvals/items/${r.biz_type}/${r.id}`)}>查看</Button>
            </span>
          ) },
        ]} />
    </div>
  )
}
