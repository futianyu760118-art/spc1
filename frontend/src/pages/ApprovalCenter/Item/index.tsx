import { Fragment, useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button, Card, Input, Spin, message } from 'antd'
import { ArrowLeftOutlined, CheckOutlined, CloseOutlined, FileImageOutlined, FilePdfOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { approvalApi, type ApprovalPreview } from '../../../services/approval'
import { qualityApi } from '../../../services/quality'
import { fileApi } from '../../../services/api'
import ClaimPaper, { opinionsFromClaim } from '../../../components/ClaimPaper'

const STATE_TEXT: Record<string, string> = { done: '已处理', current: '当前节点', todo: '待处理' }
const STATE_TAG: Record<string, string> = { done: 'sc-tag-done', current: 'sc-tag-prod', todo: 'sc-tag-wait' }
const STATUS_TAG: Record<string, { cls: string; text: string }> = {
  pending: { cls: 'sc-tag-kit', text: '审批中' },
  approved: { cls: 'sc-tag-done', text: '已通过' },
  rejected: { cls: 'sc-tag-danger', text: '已驳回' },
  recalled: { cls: 'sc-tag-wait', text: '已撤回' },
}

const fmt = (v?: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-')
const attIcon = (name?: string) => (String(name || '').toLowerCase().endsWith('.pdf') ? <FilePdfOutlined /> : <FileImageOutlined />)

/**
 * 审批详情页（/approvals/items/:bizType/:id）
 * 页面形式替代抽屉：左栏展示业务完整详情（内置业务复用业务侧视图，如索赔单纸张版式），
 * 右栏为审批进度 / 操作 / 记录 / 附件，一屏内完成「看详情 → 审批」。
 */
export default function ApprovalItemPage() {
  const { bizType, id } = useParams<{ bizType: string; id: string }>()
  const itemId = Number(id)
  const navigate = useNavigate()
  const [data, setData] = useState<ApprovalPreview | null>(null)
  const [claim, setClaim] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [comment, setComment] = useState('')
  const [acting, setActing] = useState(false)

  const load = useCallback(async () => {
    if (!bizType || !Number.isFinite(itemId) || itemId <= 0) { setLoading(false); return }
    setLoading(true)
    try {
      const res: any = await approvalApi.preview(bizType, itemId)
      setData(res.data || null)
      // 内置业务复用业务侧完整视图；取数失败时降级为映射字段展示
      if (bizType === 'supplier_claim') {
        try {
          const cRes: any = await qualityApi.get(itemId)
          setClaim(cRes.data || null)
        } catch { setClaim(null) }
      }
    } catch { /* 全局拦截器已提示 */ } finally { setLoading(false) }
  }, [bizType, itemId])
  useEffect(() => { load() }, [load])

  const act = async (action: 'approve' | 'reject') => {
    if (!bizType || !data) return
    if (action === 'reject' && !comment.trim()) { message.warning('驳回必须填写审批意见'); return }
    setActing(true)
    try {
      const payload = { comment: comment.trim(), expected_version: data.version }
      const res: any = action === 'approve'
        ? await approvalApi.approve(bizType, itemId, payload)
        : await approvalApi.reject(bizType, itemId, payload)
      message.success(res.message || '操作成功')
      setComment('')
      load()
    } catch { /* 全局拦截器已提示 */ } finally { setActing(false) }
  }

  if (loading && !data) {
    return <div className="sc-page ac-page"><Card styles={{ body: { padding: 60 } }}><Spin /></Card></div>
  }
  if (!data) {
    return (
      <div className="sc-page ac-page">
        <Card>
          <div className="ac-empty">
            <div className="ac-empty-title">未找到该单据</div>
            <div className="ac-empty-sub">单据可能已被处理或不属于当前业务</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <Button onClick={() => navigate('/approvals/pending')}>返回待办工作台</Button>
          </div>
        </Card>
      </div>
    )
  }

  const status = data.status ? STATUS_TAG[data.status] : undefined

  return (
    <div className="sc-page ac-page">
      <div className="ac-detail-head">
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/approvals/pending')}>返回待办工作台</Button>
        <span className="sc-mono ac-detail-no">{data.no || '-'}</span>
        {status ? <span className={`sc-tag ${status.cls}`}><span className="dot" />{status.text}</span> : null}
        {data.wait_level === 'overdue' ? <span className="sc-tag sc-tag-danger">已超时 {data.wait_hours} 小时</span> : null}
        {data.wait_level === 'soon' ? <span className="sc-tag sc-tag-warn">已等待 {data.wait_hours} 小时</span> : null}
        {data.current_node ? <span className="sc-tag sc-tag-amber">{data.current_node}</span> : null}
        {data.deep_link ? (
          <a className="ac-detail-link" href={data.deep_link} target="_blank" rel="noreferrer">打开完整详情 ↗</a>
        ) : null}
      </div>

      <div className="clm-detail-grid">
        {/* 左：业务完整详情（内置业务复用业务侧视图，其它业务展示映射字段） */}
        <Card styles={{ body: { padding: 0 } }}>
          <div className="ac-detail-sec-title">
            <span>{data.title || '单据详情'}</span>
            <span className="sc-note" style={{ fontWeight: 400 }}>
              {data.biz_name} · {data.applicant || '-'} 提交于 {fmt(data.submitted_at)}
            </span>
          </div>
          {claim ? (
            <div className="clm-paper-wrap"><ClaimPaper claim={claim} opinions={opinionsFromClaim(claim)} /></div>
          ) : (
            <div style={{ padding: 16 }}>
              <dl className="ac-kv">
                {(data.fields || []).map(f => (
                  <Fragment key={f.label}>
                    <dt>{f.label}</dt>
                    <dd style={f.emphasis ? { color: '#dc2626', fontWeight: 600 } : undefined}>{f.value ?? '-'}</dd>
                  </Fragment>
                ))}
              </dl>
            </div>
          )}
        </Card>

        {/* 右：审批进度 / 操作 / 记录 / 附件（粘性） */}
        <div className="clm-sticky">
          <Card title="审批进度 · 按提交时冻结的快照执行" size="small" styles={{ body: { paddingTop: 12 } }}>
            {(data.progress || []).length === 0 ? <div className="sc-note">暂无审批流程</div> : (
              <div className="ac-flow">
                {(data.progress || []).map((n, i) => (
                  <div key={n.seq ?? i} className={`ac-flow-item${n.state === 'done' ? ' done' : n.state === 'current' ? ' cur' : ''}`}>
                    <span className="ac-flow-dot" />
                    <div className="ac-flow-head">
                      {i + 1}. {n.label}
                      <span className={`sc-tag ${STATE_TAG[n.state] || 'sc-tag-wait'}`}>{STATE_TEXT[n.state] || n.state}</span>
                    </div>
                    <div className="ac-flow-sub">{n.approver_label}{n.acted_at ? ` · ${fmt(n.acted_at)}` : ''}</div>
                    {n.comment ? <div className="ac-flow-cmt">{n.comment}</div> : null}
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title={data.can_act ? `审批操作 · ${data.current_node || ''}` : '审批操作'} size="small">
            {data.can_act ? (
              <>
                <Input.TextArea rows={3} value={comment} onChange={e => setComment(e.target.value)}
                  placeholder="审批意见（驳回必填）" />
                <div style={{ display: 'flex', gap: 8, marginTop: 10, justifyContent: 'flex-end' }}>
                  <Button danger icon={<CloseOutlined />} loading={acting} onClick={() => act('reject')}>驳回</Button>
                  <Button type="primary" icon={<CheckOutlined />} loading={acting} onClick={() => act('approve')}>通过并推进到下一节点</Button>
                </div>
                <div className="f-note" style={{ marginTop: 10 }}>通过可不填意见；驳回必须填写原因，退回申请人修改后可重新提交。</div>
              </>
            ) : (
              <>
                <div className="sc-note" style={{ lineHeight: 1.8 }}>
                  {data.action_hint || '该业务不支持在审批中心内审批'}
                </div>
                {data.deep_link ? (
                  <Button type="primary" style={{ marginTop: 10 }} onClick={() => window.open(data.deep_link, '_self')}>
                    前往业务系统处理
                  </Button>
                ) : null}
              </>
            )}
          </Card>

          <Card title="审批记录" size="small" styles={{ body: { paddingTop: 8 } }}>
            {(data.logs || []).length === 0 ? <div className="sc-note">暂无审批记录</div> : (
              <div className="ac-timeline">
                {(data.logs || []).map((lg, i) => (
                  <div key={i} className="ac-tl-item done">
                    <div className="t sc-mono">{fmt(lg.time)}</div>
                    <div className="what">{lg.who} {lg.action_label || lg.action}</div>
                    {lg.comment ? <div className="who">{lg.comment}</div> : null}
                  </div>
                ))}
              </div>
            )}
          </Card>

          {claim && (claim.attachments || []).length > 0 ? (
            <Card title={`附件（${claim.attachments.length}）`} size="small" styles={{ body: { paddingTop: 10 } }}>
              {(claim.attachments || []).map((a: any, i: number) => (
                <div key={i} className="ac-att-item">
                  <span className="sc-note">{attIcon(a.name)}</span>
                  <a href={fileApi.downloadUrl(a.key)} target="_blank" rel="noreferrer"
                    style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name || a.key}</a>
                </div>
              ))}
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  )
}
