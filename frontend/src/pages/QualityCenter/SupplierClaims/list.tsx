import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, DatePicker, Input, Modal, Popover, Select, Table, message } from 'antd'
import {
  AccountBookOutlined, CheckCircleOutlined, ExportOutlined, InboxOutlined, PaperClipOutlined,
  PlusOutlined, ReloadOutlined, SearchOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import type { ColumnsType } from 'antd/es/table'
import { useExport } from '../../../hooks/useExport'
import { qualityApi, CLAIM_REASON_OPTIONS, CLAIM_STATUS_MAP, CLAIM_EDITABLE_STATUSES, type ClaimStats, type ClaimStatus } from '../../../services/quality'
import { useAuthStore } from '../../../store/auth'
import { waitPill } from '../../../utils'
import ApprovalStatsCards from '../../../components/ApprovalStatsCards'

const ITEM_LABELS: Record<string, string> = {
  replacement: '替代件', packing_fee: '包装', transporting_fee: '运输', man_hour_fee: '人工',
  additional_fee: '额外', punishment: '处罚', downgrade_use: '降级使用', direct_loss: '直接损失',
}
const CHIP_LIST: { value: '' | ClaimStatus; text: string }[] = [
  { value: '', text: '全部' },
  { value: 'draft', text: '草稿' },
  { value: 'pending', text: '审批中' },
  { value: 'rejected', text: '已驳回' },
  { value: 'recalled', text: '已撤回' },
  { value: 'approved', text: '已归档' },
]

type Row = Record<string, any>

/** 当前审批节点（快照 seq = approval_level）+ 已等待时长分级（阈值取节点 timeout_hours，默认 48h）。 */
function nodeAndWait(row: Row) {
  if (row.approval_status !== 'pending') return null
  const node = (row.approval_snapshot || []).find((n: any) => n.seq === row.approval_level)
  if (!node) return null
  return { label: node.label as string, pill: waitPill(row.submitted_at, node.timeout_hours || 48) }
}

export default function SupplierClaimList() {
  const navigate = useNavigate()
  const isAdmin = useAuthStore.getState().isAdmin()
  const canArchiveDelete = isAdmin || useAuthStore.getState().hasPermission('quality.supplier_claim.archive_delete', 'delete')

  const [items, setItems] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')
  const [stats, setStats] = useState<ClaimStats | null>(null)
  // 更多筛选（Popover 内控件，点「应用」才生效）
  const [filterDraft, setFilterDraft] = useState({ supplier: '', applicant: '', range: null as any })
  const [applied, setApplied] = useState({ supplier: '', applicant: '', date_start: '', date_end: '' })
  const [submitTarget, setSubmitTarget] = useState<Row | null>(null)
  const [acting, setActing] = useState(false)
  const { exporting, exportData } = useExport()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [listRes, statsRes]: any[] = await Promise.all([
        qualityApi.list({
          page, page_size: 20, keyword: keyword || undefined, status: status || undefined,
          supplier: applied.supplier || undefined, applicant: applied.applicant || undefined,
          date_start: applied.date_start || undefined, date_end: applied.date_end || undefined,
        }),
        qualityApi.stats(),
      ])
      const data = listRes.data || {}
      if (page > 1 && (data.items || []).length === 0 && data.total > 0) { setPage(page - 1); return }
      setItems(data.items || [])
      setTotal(data.total || 0)
      setStats(statsRes.data || null)
    } catch { /* 全局拦截器已提示 */ } finally { setLoading(false) }
  }, [page, keyword, status, applied])
  useEffect(() => { load() }, [load])

  const hasFilter = !!keyword || !!status || !!applied.supplier || !!applied.applicant || !!applied.date_start || !!applied.date_end
  const pickStatus = (v: string) => { setPage(1); setStatus(prev => (prev === v ? '' : v)) }

  const confirmSubmit = async () => {
    if (!submitTarget) return
    setActing(true)
    try {
      const res: any = await qualityApi.submit(submitTarget.id)
      message.success(res.message || '已提交审批')
      setSubmitTarget(null)
      load()
    } catch { /* 全局拦截器已提示 */ } finally { setActing(false) }
  }

  const confirmDelete = (row: Row) => Modal.confirm({
    title: '删除索赔单',
    okText: '确认删除',
    okButtonProps: { danger: true },
    content: (
      <div>
        确认删除 <b className="sc-mono">{row.claim_no}</b>（{CLAIM_STATUS_MAP[row.approval_status as ClaimStatus]?.text}）？
        <div className="f-note" style={{ marginTop: 10 }}>
          仅本人草稿 / 已驳回 / 已撤回单可删除；已归档单删除需「索赔单归档删除」权限。
        </div>
      </div>
    ),
    onOk: async () => {
      try {
        const res: any = await qualityApi.delete(row.id, canArchiveDelete)
        message.success(res.message || '已删除')
        load()
      } catch { /* 全局拦截器已提示 */ }
    },
  })

  const amountSum = useMemo(
    () => items.reduce((s, r) => s + (r.claim_amount != null ? Number(r.claim_amount) : 0), 0),
    [items])

  const columns: ColumnsType<Row> = [
    {
      title: '索赔单号', dataIndex: 'claim_no', width: 150, fixed: 'left',
      render: (v: string, r) => <a className="sc-mono" style={{ fontWeight: 600 }} onClick={() => navigate(`/quality/supplier-claims/${r.id}`)}>{v}</a>,
    },
    {
      title: '状态', dataIndex: 'approval_status', width: 92,
      render: (v: string) => { const s = CLAIM_STATUS_MAP[v as ClaimStatus] || CLAIM_STATUS_MAP.draft; return <span className={`sc-tag ${s.cls}`}><span className="dot" />{s.text}</span> },
    },
    {
      title: '供应商', dataIndex: 'supplier_name', width: 210, ellipsis: true,
      render: (v: string, r) => (
        <div style={{ minWidth: 0 }}>
          <div className="ac-cell-title">{v || '-'}</div>
          {r.supplier_code ? <div className="ac-cell-sub sc-mono">{r.supplier_code}</div> : null}
        </div>
      ),
    },
    {
      title: '索赔原因', dataIndex: 'claim_reason', width: 124,
      render: (v: string) => (
        <span className={`sc-tag ${v === 'field_customer_claim' ? 'sc-tag-danger' : 'sc-tag-kit'}`}>
          {CLAIM_REASON_OPTIONS.find(o => o.value === v)?.label.split(' ')[0] || '-'}
        </span>
      ),
    },
    {
      title: '索赔细项', dataIndex: 'claim_items', width: 190,
      render: (v: string[]) => {
        const list = v || []
        return (
          <span className="clm-itags">
            {list.slice(0, 3).map(i => <span key={i} className="clm-itag">{ITEM_LABELS[i] || i}</span>)}
            {list.length > 3 ? <span className="clm-more-n">+{list.length - 3}</span> : null}
          </span>
        )
      },
    },
    {
      title: '索赔金额（元）', dataIndex: 'claim_amount', width: 118, align: 'right',
      render: (v: any) => v != null
        ? <span className="sc-mono" style={{ fontWeight: 600 }}>{Number(v).toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
        : '-',
    },
    { title: '开单日期', dataIndex: 'claim_date', width: 104, render: (v: string) => <span className="sc-mono">{v || '-'}</span> },
    { title: '申请人', dataIndex: 'applicant_display', width: 92, ellipsis: true, render: (v: string, r) => v || r.applicant || '-' },
    {
      title: '当前节点 / 等待', width: 168,
      render: (_: any, r) => {
        const st = r.approval_status
        if (st === 'pending') {
          const nw = nodeAndWait(r)
          return nw?.pill
            ? <span>{nw.label} <span className={`ac-due-pill ${nw.pill.level}`}>{nw.pill.text}</span></span>
            : <span className="sc-note">审批中</span>
        }
        if (st === 'rejected') {
          const rej = (r.approval_logs || []).filter((l: any) => l.action === 'reject').slice(-1)[0]
          return rej?.comment
            ? <span className="sc-note" style={{ color: '#dc2626', display: 'block', maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={rej.comment}>驳回：{rej.comment}</span>
            : <span className="sc-note" style={{ color: '#dc2626' }}>已驳回</span>
        }
        if (st === 'approved') return <span className="sc-note">{r.approved_at ? `归档于 ${dayjs(r.approved_at).format('MM-DD HH:mm')}` : '已归档'}</span>
        if (st === 'recalled') return <span className="sc-note">发起人撤回 · 可重新提交</span>
        return <span className="sc-note">未提交</span>
      },
    },
    {
      title: '附件', width: 64, align: 'right',
      render: (_: any, r) => {
        const n = (r.attachments || []).length
        return <span className="sc-note sc-mono">{n > 0 ? <><PaperClipOutlined /> {n}</> : '0'}</span>
      },
    },
    {
      title: '操作', width: 140, fixed: 'right',
      render: (_: any, r) => {
        const st = r.approval_status
        return (
          <span className="sc-row-act" style={{ opacity: 1 }}>
            <Button size="small" type="link" onClick={() => navigate(`/quality/supplier-claims/${r.id}`)}>查看</Button>
            {CLAIM_EDITABLE_STATUSES.includes(st) && (
              <Button size="small" type="link" onClick={() => navigate(`/quality/supplier-claims/new?edit=${r.id}`)}>编辑</Button>
            )}
            {st === 'draft' && <Button size="small" type="link" onClick={() => setSubmitTarget(r)}>提交</Button>}
            {st === 'approved' && (
              <Button size="small" type="link" onClick={() => navigate(`/quality/supplier-claims/print/${r.id}`)}>打印</Button>
            )}
            {(CLAIM_EDITABLE_STATUSES.includes(st) || (st === 'approved' && canArchiveDelete)) && (
              <Button size="small" type="link" danger onClick={() => confirmDelete(r)}>删除</Button>
            )}
          </span>
        )
      },
    },
  ]

  const byStatus: ClaimStats['by_status'] = stats?.by_status
    ?? { draft: 0, pending: 0, approved: 0, rejected: 0, recalled: 0 }

  return (
    <div className="sc-page">
      <ApprovalStatsCards
        cards={[
          {
            key: 'amount', label: '本月索赔金额', value: `¥${(stats?.month_amount ?? 0).toLocaleString()}`, unit: '元',
            icon: <AccountBookOutlined />, hint: `${stats?.month_count ?? 0} 单 · 点击查看全部`,
            active: !status && !hasFilter, onClick: () => pickStatus(''),
          },
          {
            key: 'pending', label: '审批中', value: byStatus.pending ?? 0, unit: '单', tone: 'info',
            icon: <InboxOutlined />, hint: '点击筛选', active: status === 'pending', onClick: () => pickStatus('pending'),
          },
          {
            key: 'mine', label: '待我审批', value: stats?.pending_mine ?? 0, unit: '单', tone: 'danger',
            icon: <SearchOutlined />, hint: '前往审批中心处理 →',
            onClick: () => navigate('/approvals/pending?biz_type=supplier_claim'),
          },
          {
            key: 'approved', label: '已归档', value: byStatus.approved ?? 0, unit: '单', tone: 'success',
            icon: <CheckCircleOutlined />, hint: '点击筛选', active: status === 'approved', onClick: () => pickStatus('approved'),
          },
        ]}
      />

      <div className="sc-toolbar">
        <Input.Search allowClear className="sc-search" style={{ width: 250 }}
          placeholder="索赔单号 / 供应商 / 申请人" onSearch={v => { setPage(1); setKeyword(v) }} />
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
          {CHIP_LIST.map(c => (
            <span key={c.value} className={`sc-chip${status === c.value ? ' on' : ''}`}
              onClick={() => { setPage(1); setStatus(c.value) }}>
              {c.text} <span className="n">{c.value === '' ? (stats?.total ?? 0) : (byStatus[c.value] ?? 0)}</span>
            </span>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 6, alignItems: 'center' }}>
          <Popover trigger="click" placement="bottomRight" content={(
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, width: 264 }}>
              <Input allowClear placeholder="供应商（模糊）" value={filterDraft.supplier}
                onChange={e => setFilterDraft(d => ({ ...d, supplier: e.target.value }))} />
              <Input allowClear placeholder="申请人" value={filterDraft.applicant}
                onChange={e => setFilterDraft(d => ({ ...d, applicant: e.target.value }))} />
              <DatePicker.RangePicker style={{ width: '100%' }} value={filterDraft.range}
                onChange={v => setFilterDraft(d => ({ ...d, range: v }))} />
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <Button size="small" onClick={() => {
                  setFilterDraft({ supplier: '', applicant: '', range: null })
                  setApplied({ supplier: '', applicant: '', date_start: '', date_end: '' })
                  setPage(1)
                }}>重置</Button>
                <Button size="small" type="primary" onClick={() => {
                  setApplied({
                    supplier: filterDraft.supplier.trim(), applicant: filterDraft.applicant.trim(),
                    date_start: filterDraft.range?.[0]?.format('YYYY-MM-DD') || '',
                    date_end: filterDraft.range?.[1]?.format('YYYY-MM-DD') || '',
                  })
                  setPage(1)
                }}>应用</Button>
              </div>
            </div>
          )}>
            <Button size="small">更多筛选</Button>
          </Popover>
          <Button size="small" icon={<ReloadOutlined />} onClick={load} />
          <Button size="small" icon={<ExportOutlined />} loading={exporting}
            onClick={() => exportData('/api/v1/quality/supplier-claims/export', {
              format: 'xlsx', keyword: keyword || undefined, status: status || undefined,
              supplier: applied.supplier || undefined, applicant: applied.applicant || undefined,
              date_start: applied.date_start || undefined, date_end: applied.date_end || undefined,
            }, '供应商索赔单.xlsx')}>导出</Button>
          <Button type="primary" size="small" icon={<PlusOutlined />}
            onClick={() => navigate('/quality/supplier-claims/new')}>新建索赔单</Button>
        </div>
      </div>

      <Table<Row>
        rowKey="id" loading={loading} dataSource={items} columns={columns}
        scroll={{ x: 1360 }} size="middle"
        onRow={r => ({
          style: { cursor: 'pointer' },
          onClick: e => {
            const el = e.target as HTMLElement
            if (el.closest('input,button,a,label')) return
            navigate(`/quality/supplier-claims/${r.id}`)
          },
        })}
        summary={() => (
          <Table.Summary.Row className="sc-note">
            <Table.Summary.Cell index={0} colSpan={5}>本页 {items.length} 单</Table.Summary.Cell>
            <Table.Summary.Cell index={5} align="right">
              <b className="sc-mono" style={{ color: '#0f172a' }}>合计 ¥{amountSum.toLocaleString(undefined, { minimumFractionDigits: 2 })}</b>
            </Table.Summary.Cell>
            <Table.Summary.Cell index={6} colSpan={2} />
            <Table.Summary.Cell index={8}>审批中 {byStatus.pending ?? 0}</Table.Summary.Cell>
            <Table.Summary.Cell index={9} colSpan={2} />
          </Table.Summary.Row>
        )}
        locale={{ emptyText: (
          <div className="ac-empty">
            <div className="ac-empty-ico">{hasFilter ? <SearchOutlined /> : <InboxOutlined />}</div>
            <div className="ac-empty-title">{hasFilter ? '没有符合筛选条件的索赔单' : '暂无索赔单'}</div>
            <div className="ac-empty-sub">{hasFilter ? '试试清除关键词或切换状态' : '点击右上角「新建索赔单」发起第一笔供应商索赔'}</div>
          </div>
        ) }}
        pagination={{
          current: page, pageSize: 20, total, showSizeChanger: false,
          showTotal: t => `共 ${t} 条`, onChange: setPage,
        }}
      />

      <Modal title="提交审批" open={!!submitTarget} confirmLoading={acting}
        okText="确认提交" onOk={confirmSubmit} onCancel={() => setSubmitTarget(null)}>
        {submitTarget ? (
          <div>
            确认提交 <b className="sc-mono">{submitTarget.claim_no}</b>
            （{submitTarget.supplier_name} · ¥{Number(submitTarget.claim_amount ?? 0).toLocaleString()}）？
            <div className="f-note" style={{ marginTop: 12 }}>
              提交后将冻结当前审批链快照（按金额条件过滤节点），后续配置变更不再影响本单。
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
