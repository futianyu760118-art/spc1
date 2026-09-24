import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Button, Card, Checkbox, Input, Modal, Popover, Segmented, Space, Table, Tabs, Tooltip, message } from 'antd'
import {
  AlertOutlined, CheckOutlined, ClockCircleOutlined, ColumnHeightOutlined, FieldTimeOutlined,
  InboxOutlined, ReloadOutlined, SearchOutlined, SettingOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { approvalApi, type ApprovalItem, type ApprovalStats } from '../../../services/approval'
import { daysAgoISO, mondayOf } from '../../../utils'
import ApprovalStatsCards from '../../../components/ApprovalStatsCards'
import MyApprovedTab from './MyApprovedTab'
import MySubmittedTab from './MySubmittedTab'

export type WorkbenchTabProps = {
  registerReload: (key: 'pending' | 'approved' | 'submitted', fn: (() => void) | undefined) => void
  onCount: (key: 'pending' | 'approved' | 'submitted', n: number) => void
}

const WAIT_CLASS: Record<string, string> = { overdue: 'urgent', soon: 'soon', normal: 'ok' }
const WAIT_TEXT = (h?: number | null, level?: string) =>
  h == null ? '-' : level === 'overdue' ? `${h} 小时 · 已超时` : level === 'soon' ? `${h} 小时 · 即将超时` : `${h} 小时`

function PendingTab({ bizMode, registerReload, onCount }: WorkbenchTabProps & { bizMode: 'all' | 'builtin' }) {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [items, setItems] = useState<ApprovalItem[]>([])
  const [stats, setStats] = useState<ApprovalStats>({})
  const [bizNames, setBizNames] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [bizType, setBizType] = useState<string | undefined>(undefined)
  const [selected, setSelected] = useState<ApprovalItem[]>([])
  const [batchOpen, setBatchOpen] = useState(false)
  const [batchComment, setBatchComment] = useState('')
  const [batchSubmitting, setBatchSubmitting] = useState(false)
  const [quickTarget, setQuickTarget] = useState<ApprovalItem | null>(null)
  const [quickComment, setQuickComment] = useState('')
  const [quickSubmitting, setQuickSubmitting] = useState(false)
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [waitLevel, setWaitLevel] = useState<'soon' | 'overdue' | undefined>(undefined)
  const [todayOnly, setTodayOnly] = useState(false)
  const [hiddenCols, setHiddenCols] = useState<string[]>([])
  const [dense, setDense] = useState(false)

  // 站内信深链（?biz_type=X&item_id=Y）直接进入该单据的审批详情页
  useEffect(() => {
    const bt = searchParams.get('biz_type')
    const id = Number(searchParams.get('item_id'))
    if (bt && Number.isFinite(id) && id > 0) {
      navigate(`/approvals/items/${bt}/${id}`, { replace: true })
    }
  }, [searchParams, navigate])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await approvalApi.pending({
        page, page_size: 20, keyword: keyword || undefined,
        biz_type: bizType, wait_level: waitLevel, today_only: todayOnly || undefined,
        provider_mode: bizMode === 'builtin' ? 'builtin' : undefined,
      })
      const list: ApprovalItem[] = res.data?.items || []
      const nextTotal = res.data?.total || 0
      // 末页条目被审批完后退回上一页，避免停在空白页
      if (page > 1 && list.length === 0 && nextTotal > 0) { setPage(page - 1); return }
      setItems(list)
      setTotal(nextTotal)
      setStats(res.data?.stats || {})
      // 业务名称只随条目返回，按业务筛选后其它业务的名称取不到，故累积；计数始终用全局 stats.by_biz
      setBizNames(prev => {
        const next = { ...prev }
        list.forEach(it => { next[it.biz_type] = it.biz_name || it.biz_type })
        return next
      })
      setSelected([])
    } catch { /* 全局拦截器已提示 */ } finally { setLoading(false) }
  }, [keyword, bizType, waitLevel, todayOnly, bizMode, page])
  useEffect(() => { load() }, [load])
  useEffect(() => { registerReload('pending', load); return () => registerReload('pending', undefined) }, [load, registerReload])
  useEffect(() => { onCount('pending', stats.total ?? 0) }, [stats, onCount])

  const bizOptions = Object.entries(stats.by_biz || {}).map(([value, count]) => ({
    value, label: bizNames[value] || value, count,
  }))

  const hasFilter = !!keyword || !!bizType || !!waitLevel || todayOnly
  const pickCard = (next: 'today' | 'soon' | 'overdue') => {
    setPage(1)
    if (next === 'today') { setTodayOnly(v => !v); setWaitLevel(undefined); return }
    setTodayOnly(false)
    setWaitLevel(v => (v === next ? undefined : next))
  }

  const submitBatch = async () => {
    setBatchSubmitting(true)
    const snapshot = [...selected]
    const labelOf = (x: any) => {
      const hit = snapshot.find(s => s.biz_type === x.biz_type && s.id === x.id)
      return hit ? ([hit.no, hit.title].filter(Boolean).join(' · ') || `${x.biz_type} #${x.id}`) : `${x.biz_type} #${x.id}`
    }
    try {
      const res: any = await approvalApi.batchApprove({
        items: snapshot.map(r => ({ biz_type: r.biz_type, id: r.id, expected_version: r.version })),
        comment: batchComment.trim() || undefined,
      })
      const { passed = [], failed = [], skipped = [] } = res.data || {}
      Modal.info({
        title: '批量审批结果',
        width: 560,
        content: (
          <div>
            <div className="ac-result-grid">
              <div className="ac-result-cell ok"><div className="k">通过</div><div className="v">{passed.length}</div></div>
              <div className="ac-result-cell bad"><div className="k">失败</div><div className="v">{failed.length}</div></div>
              <div className="ac-result-cell skip"><div className="k">跳过</div><div className="v">{skipped.length}</div></div>
            </div>
            <div className="ac-pick-list" style={{ maxHeight: 260 }}>
              {passed.map((p: any) => (
                <div className="ac-pick-item" key={`${p.biz_type}-${p.id}`}>
                  <span className="sc-tag sc-tag-done">通过</span>
                  <span className="t">{labelOf(p)}</span>
                  <span className="amt">{p.finished ? '单据已归档' : '已推进到下一审批节点'}</span>
                </div>
              ))}
              {failed.map((f: any) => (
                <div className="ac-pick-item" key={`${f.biz_type}-${f.id}`}>
                  <span className="sc-tag sc-tag-danger">失败</span>
                  <span className="t">{labelOf(f)}</span>
                  <span className="amt">{f.reason || '操作失败'}</span>
                </div>
              ))}
              {skipped.map((s: any) => (
                <div className="ac-pick-item" key={`${s.biz_type}-${s.id}`}>
                  <span className="sc-tag sc-tag-wait">跳过</span>
                  <span className="t">{labelOf(s)}</span>
                  <span className="amt">{s.reason || '已跳过'}</span>
                </div>
              ))}
            </div>
            {failed.length + skipped.length > 0 ? (
              <div className="ac-empty-sub" style={{ marginTop: 0 }}>失败与跳过的单据仍保留在待办列表中。</div>
            ) : null}
          </div>
        ),
      })
      setBatchOpen(false)
      setBatchComment('')
      load()
    } catch { /* 全局拦截器已提示 */ } finally { setBatchSubmitting(false) }
  }

  const submitQuick = async () => {
    if (!quickTarget) return
    setQuickSubmitting(true)
    try {
      const res: any = await approvalApi.approve(quickTarget.biz_type, quickTarget.id, {
        comment: quickComment.trim() || undefined, expected_version: quickTarget.version,
      })
      message.success(res.message || '已通过')
      setQuickTarget(null)
      setQuickComment('')
      load()
    } catch { /* 全局拦截器已提示 */ } finally { setQuickSubmitting(false) }
  }

  // 可隐藏列（单号 / 标题摘要 / 已等待 / 操作 常驻）
  const hideableCols = [
    { key: 'biz', label: '业务类型' },
    { key: 'applicant', label: '申请人' },
    { key: 'submitted', label: '提交时间' },
    { key: 'node', label: '当前节点' },
  ]
  const allColumns = [
    // 待办聚合已按节点权限过滤：内置业务出现在列表里即可操作（can_act=true），SQL 接入业务恒 false（无动作适配器）
    { key: 'biz', title: '业务类型', width: 140, render: (_: any, r: ApprovalItem) => (
      <span className={`sc-tag ${r.can_act ? 'sc-tag-prod' : 'sc-tag-purple'}`}>{r.biz_name}</span>
    ) },
    { key: 'no', title: '单号', width: 170, render: (_: any, r: ApprovalItem) => (
      <a className="sc-mono" style={{ fontWeight: 500 }} onClick={() => navigate(`/approvals/items/${r.biz_type}/${r.id}`)}>{r.no}</a>
    ) },
    { key: 'title', title: '标题 / 摘要', render: (_: any, r: ApprovalItem) => (
      <div style={{ minWidth: 0 }}>
        <div className="ac-cell-title">{r.title || '-'}</div>
        {r.summary ? <div className="ac-cell-sub">{r.summary}</div> : null}
      </div>
    ) },
    { key: 'applicant', title: '申请人', dataIndex: 'applicant', width: 100 },
    { key: 'submitted', title: '提交时间', width: 120, render: (_: any, r: ApprovalItem) => r.submitted_at ? dayjs(r.submitted_at).format('MM-DD HH:mm') : '-' },
    { key: 'wait', title: '已等待', width: 150, render: (_: any, r: ApprovalItem) => (
      <span className={`ac-due-pill ${WAIT_CLASS[r.wait_level || 'normal'] || 'ok'}`}>
        {WAIT_TEXT(r.wait_hours, r.wait_level)}
      </span>
    ) },
    { key: 'node', title: '当前节点', dataIndex: 'current_node', width: 140, render: (v?: string, r?: ApprovalItem) => v || (r?.current_level ? `L${r.current_level}` : '-') },
    { key: 'op', title: '操作', width: 150, fixed: 'right' as const, render: (_: any, r: ApprovalItem) => (
      <span className="sc-row-act">
        {r.can_act ? <Button size="small" type="link" onClick={() => { setQuickTarget(r); setQuickComment('') }}>通过</Button> : null}
        <Button size="small" type="link" onClick={() => navigate(`/approvals/items/${r.biz_type}/${r.id}`)}>
          {r.can_act ? '去审批' : '去处理'}
        </Button>
      </span>
    ) },
  ]
  const visibleColumns = allColumns.filter(c => !hiddenCols.includes(c.key))

  return (
    <div className="ac-pane">
      <ApprovalStatsCards
        cards={[
          { key: 'total', label: '待我审批', value: stats.total ?? 0, unit: '单', icon: <InboxOutlined />, hint: '点击清除筛选',
            active: !hasFilter,
            onClick: () => { setPage(1); setWaitLevel(undefined); setTodayOnly(false); setKeyword(''); setBizType(undefined) } },
          { key: 'today', label: '今日新增', value: stats.today ?? 0, unit: '单', tone: 'info', icon: <ClockCircleOutlined />, hint: '今日 00:00 后提交 · 点击筛选',
            active: todayOnly, onClick: () => pickCard('today') },
          { key: 'soon', label: '即将超时', value: stats.soon ?? 0, unit: '单', tone: 'warning', icon: <FieldTimeOutlined />, hint: '已等待超过阈值一半 · 点击筛选',
            active: waitLevel === 'soon', onClick: () => pickCard('soon') },
          { key: 'overdue', label: '已超时', value: stats.overdue ?? 0, unit: '单', tone: 'danger', icon: <AlertOutlined />, hint: '已推送催办提醒 · 点击筛选',
            active: waitLevel === 'overdue', onClick: () => pickCard('overdue') },
        ]}
      />
      <div className="sc-toolbar">
        <Input.Search allowClear placeholder="单号 / 标题 / 申请人" className="sc-search" style={{ width: 260 }}
          onSearch={v => { setPage(1); setKeyword(v) }} />
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          <span className={`sc-chip${!bizType ? ' on' : ''}`} onClick={() => { setPage(1); setBizType(undefined) }}>
            全部 <span className="n">{stats.total ?? 0}</span>
          </span>
          {bizOptions.map(o => (
            <span key={o.value} className={`sc-chip${bizType === o.value ? ' on' : ''}`}
              onClick={() => { setPage(1); setBizType(bizType === o.value ? undefined : o.value) }}>
              {o.label} <span className="n">{o.count}</span>
            </span>
          ))}
          <span className={`sc-chip${waitLevel === 'overdue' ? ' on' : ''}`}
            onClick={() => { setPage(1); setWaitLevel(waitLevel === 'overdue' ? undefined : 'overdue') }}>
            仅看超时
          </span>
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
          <Popover trigger="click" placement="bottomRight" content={(
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {hideableCols.map(h => (
                <Checkbox key={h.key} checked={!hiddenCols.includes(h.key)}
                  onChange={e => setHiddenCols(prev =>
                    e.target.checked ? prev.filter(k => k !== h.key) : [...prev, h.key])}>
                  {h.label}
                </Checkbox>
              ))}
            </div>
          )}>
            <Tooltip title="列设置"><Button className="ac-icon-btn" icon={<SettingOutlined />} /></Tooltip>
          </Popover>
          <Tooltip title={dense ? '宽松密度' : '紧凑密度'}>
            <Button className={`ac-icon-btn${dense ? ' on' : ''}`} icon={<ColumnHeightOutlined />}
              onClick={() => setDense(v => !v)} />
          </Tooltip>
          <Button className="ac-icon-btn" icon={<ReloadOutlined />} onClick={load} />
        </div>
      </div>
      <Table<ApprovalItem>
        rowKey={r => `${r.biz_type}-${r.id}`} loading={loading} dataSource={items} scroll={{ x: 1200 }}
        size={dense ? 'small' : 'large'}
        locale={{ emptyText: (
          <div className="ac-empty">
            <div className="ac-empty-ico">{hasFilter ? <SearchOutlined /> : <InboxOutlined />}</div>
            <div className="ac-empty-title">{hasFilter ? '没有符合筛选条件的待办' : '没有待你审批的单据'}</div>
            <div className="ac-empty-sub">{hasFilter ? '试试清除关键词或切换业务类型' : '新单据提交后会自动出现在这里，并推送站内信 / 企微提醒'}</div>
          </div>
        ) }}
        onRow={r => ({
          style: { cursor: 'pointer' },
          onClick: e => {
            const el = e.target as HTMLElement
            if (el.closest('input,button,a,label')) return
            navigate(`/approvals/items/${r.biz_type}/${r.id}`)
          },
        })}
        rowSelection={{ selectedRowKeys: selected.map(r => `${r.biz_type}-${r.id}`), onChange: (_k, rows) => setSelected(rows) }}
        pagination={{
          current: page, pageSize: 20, total, showSizeChanger: false,
          showTotal: t => `共 ${t} 条`, onChange: setPage,
        }}
        columns={visibleColumns} />

      {selected.length > 0 ? (
        <div className="sc-batch-bar">
          <span className="bb-n">已选 <b>{selected.length}</b> 项</span>
          <span className="bb-sep" />
          <Button size="small" type="primary" icon={<CheckOutlined />} onClick={() => setBatchOpen(true)}>批量通过</Button>
          <span className="bb-sep" />
          <a className="sc-note" style={{ cursor: 'pointer' }} onClick={() => setSelected([])}>清除选择</a>
        </div>
      ) : null}

      <Modal title="通过审批" open={!!quickTarget} confirmLoading={quickSubmitting}
        onOk={submitQuick} onCancel={() => setQuickTarget(null)} okText="确认通过">
        {quickTarget ? (
          <div className="ac-pick-list">
            <div className="ac-pick-item">
              <span className="sc-tag sc-tag-prod">{quickTarget.biz_name}</span>
              <span className="t">{quickTarget.no} · {quickTarget.title}</span>
            </div>
          </div>
        ) : null}
        <Input.TextArea rows={3} value={quickComment} onChange={e => setQuickComment(e.target.value)}
          placeholder="审批意见（选填）" />
        <div className="f-note" style={{ marginTop: 12 }}>
          通过后单据自动推进到下一审批节点；若下一节点审批人已审批过本轮，将自动跳过。
        </div>
      </Modal>

      <Modal title={`批量通过审批（${selected.length} 条）`} open={batchOpen} confirmLoading={batchSubmitting}
        onOk={submitBatch} onCancel={() => setBatchOpen(false)} okText="确认通过" width={560}>
        <div className="ac-pick-list">
          {selected.map((r, i) => (
            <div className="ac-pick-item" key={`${r.biz_type}-${r.id}`}>
              <span className="no">{i + 1}</span>
              <span className="sc-tag sc-tag-prod">{r.biz_name}</span>
              <span className="t">{r.no} · {r.title}</span>
              <span className="amt">{r.can_act ? '可审批' : '将跳过'}</span>
            </div>
          ))}
        </div>
        <Input.TextArea rows={3} value={batchComment} onChange={e => setBatchComment(e.target.value)}
          placeholder="统一审批意见（选填）" />
        <div className="f-warn" style={{ marginTop: 12 }}>
          SQL 接入业务不支持批量通过，将被自动跳过（请在业务系统内处理）；逐条校验失败的单据会列在结果报告中，不影响其他单据。
        </div>
      </Modal>
    </div>
  )
}

export default function ApprovalPending() {
  const [activeKey, setActiveKey] = useState('pending')
  const [bizMode, setBizMode] = useState<'all' | 'builtin'>('all')
  const [syncedAt, setSyncedAt] = useState<Date | null>(null)
  const [counts, setCounts] = useState<Partial<Record<'pending' | 'approved' | 'submitted', number>>>({})
  const reloaders = useRef<Record<string, (() => void) | undefined>>({})

  const registerReload = useCallback((key: 'pending' | 'approved' | 'submitted', fn: (() => void) | undefined) => {
    reloaders.current[key] = fn ? () => { fn(); setSyncedAt(new Date()) } : undefined
  }, [])
  const onCount = useCallback((key: 'pending' | 'approved' | 'submitted', n: number) => {
    setCounts(prev => (prev[key] === n ? prev : { ...prev, [key]: n }))
  }, [])
  const refresh = useCallback(() => { reloaders.current[activeKey]?.() }, [activeKey])

  // 三个 Tab 的计数进入页面即预取（AntD Tabs 懒挂载，未点击的 Tab 不会自行上报，徽标会缺失）
  const loadCounts = useCallback(async () => {
    try {
      const [pRes, aRes, sRes]: any[] = await Promise.all([
        approvalApi.pending({ page: 1, page_size: 1 }),
        approvalApi.approved({ page: 1, page_size: 1, date_from: mondayOf().format('YYYY-MM-DD') }),
        approvalApi.submitted({ page: 1, page_size: 1, date_from: daysAgoISO(90) }),
      ])
      const s = sRes.data?.stats || {}
      setCounts({
        pending: pRes.data?.stats?.total ?? 0,
        approved: aRes.data?.stats?.processed ?? 0,
        submitted: (s.pending ?? 0) + (s.approved ?? 0) + (s.rejected ?? 0) + (s.recalled ?? 0),
      })
    } catch { /* 全局拦截器已提示 */ }
  }, [])
  useEffect(() => { loadCounts() }, [loadCounts])

  // 每 60 秒自动刷新当前 Tab 与三个 Tab 的计数（与原型「数据截至 HH:mm · 每 60 秒自动刷新」一致）
  useEffect(() => {
    const timer = setInterval(() => { refresh(); loadCounts() }, 60_000)
    return () => clearInterval(timer)
  }, [refresh, loadCounts])

  const tabLabel = (key: 'pending' | 'approved' | 'submitted', text: string) => {
    const n = counts[key]
    return n == null ? text : <span>{text}<span className="sc-tab-count">{n}</span></span>
  }

  return (
    <div className="sc-page ac-page">
      <Card styles={{ body: { padding: '0 12px 12px' } }}>
        <Tabs
          activeKey={activeKey}
          onChange={setActiveKey}
          tabBarExtraContent={{
            right: (
              <Space size={12}>
                <span className="ac-head-hint">
                  {syncedAt ? `数据截至 ${dayjs(syncedAt).format('HH:mm')} · 每 60 秒自动刷新` : '每 60 秒自动刷新'}
                </span>
                <Segmented value={bizMode} onChange={v => setBizMode(v as 'all' | 'builtin')}
                  options={[{ label: '全部业务', value: 'all' }, { label: '仅内置业务', value: 'builtin' }]} />
                <Tooltip title="刷新"><Button className="ac-icon-btn" icon={<ReloadOutlined />} onClick={refresh} /></Tooltip>
              </Space>
            ),
          }}
          items={[
            { key: 'pending', label: tabLabel('pending', '待我审批'),
              children: <PendingTab bizMode={bizMode} registerReload={registerReload} onCount={onCount} /> },
            { key: 'approved', label: tabLabel('approved', '我已审批'),
              children: <MyApprovedTab registerReload={registerReload} onCount={onCount} /> },
            { key: 'submitted', label: tabLabel('submitted', '我发起的'),
              children: <MySubmittedTab registerReload={registerReload} onCount={onCount} /> },
          ]}
        />
      </Card>
    </div>
  )
}
