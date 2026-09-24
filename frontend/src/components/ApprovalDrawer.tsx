import { Fragment, useCallback, useEffect, useState } from 'react'
import { Alert, Button, Drawer, Input, Space, Spin, Typography, message } from 'antd'
import dayjs from 'dayjs'
import { approvalApi, type ApprovalPreview } from '../services/approval'

const STATE_TEXT: Record<string, string> = { done: '已处理', current: '当前节点', todo: '待处理' }
const STATE_TAG: Record<string, string> = { done: 'sc-tag-done', current: 'sc-tag-prod', todo: 'sc-tag-wait' }
const STATUS_TAG: Record<string, { cls: string; text: string }> = {
  pending: { cls: 'sc-tag-kit', text: '审批中' },
  approved: { cls: 'sc-tag-done', text: '已通过' },
  rejected: { cls: 'sc-tag-danger', text: '已驳回' },
  recalled: { cls: 'sc-tag-wait', text: '已撤回' },
}

const fmt = (v?: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-')

export default function ApprovalDrawer({ open, bizType, itemId, onClose, onDone }: {
  open: boolean
  bizType?: string
  itemId?: number
  onClose: () => void
  onDone?: (payload: { action: 'approve' | 'reject'; id: number }) => void
}) {
  const [data, setData] = useState<ApprovalPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [comment, setComment] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const load = useCallback(async () => {
    if (!bizType || !itemId) return
    setLoading(true)
    try {
      const res: any = await approvalApi.preview(bizType, itemId)
      setData(res.data || null)
      setComment('')
    } catch { /* 全局拦截器已提示 */ } finally { setLoading(false) }
  }, [bizType, itemId])

  useEffect(() => { if (open) load() }, [open, load])

  const act = async (action: 'approve' | 'reject') => {
    if (!bizType || !itemId || !data) return
    if (action === 'reject' && !comment.trim()) { message.warning('驳回必须填写审批意见'); return }
    setSubmitting(true)
    try {
      const payload = { comment: comment.trim(), expected_version: data.version }
      const res: any = action === 'approve'
        ? await approvalApi.approve(bizType, itemId, payload)
        : await approvalApi.reject(bizType, itemId, payload)
      message.success(res.message || '操作成功')
      onDone?.({ action, id: itemId })
      onClose()
    } catch { /* 全局拦截器已提示 */ } finally { setSubmitting(false) }
  }

  const canAct = !!data?.can_act
  const status = data?.status ? STATUS_TAG[data.status] : undefined

  return (
    <Drawer
      title={data ? (
        <div>
          <div className="ac-dr-title">{data.title || '-'}</div>
          <div className="ac-dr-code">{data.no || '-'} · {data.biz_name}</div>
        </div>
      ) : '审批详情'}
      width={640}
      open={open}
      onClose={onClose}
      destroyOnClose
      rootClassName="sc-page ac-page sc-drawer ac-drawer"
      footer={canAct ? (
        <div>
          <div className="f-note">通过可不填意见；驳回必须填写原因，将退回申请人修改后重新提交。</div>
          <Input.TextArea rows={2} value={comment} onChange={e => setComment(e.target.value)}
            placeholder="审批意见（驳回必填）…" style={{ marginTop: 10 }} />
          <div style={{ textAlign: 'right', marginTop: 10 }}>
            <Space>
              <Button danger loading={submitting} onClick={() => act('reject')}>驳回</Button>
              <Button type="primary" loading={submitting} onClick={() => act('approve')}>通过并推进到下一节点</Button>
            </Space>
          </div>
        </div>
      ) : (
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Typography.Text type="secondary">{data?.action_hint || '该业务不支持在审批中心内审批'}</Typography.Text>
          {data?.deep_link ? <Button type="primary" onClick={() => window.open(data.deep_link, '_self')}>前往业务系统处理</Button> : null}
        </Space>
      )}
    >
      <Spin spinning={loading}>
        {data ? (
          <>
            <div className="ac-dr-tags">
              <span className={`sc-tag ${data.can_act || data.status === 'pending' ? 'sc-tag-prod' : 'sc-tag-purple'}`}>{data.biz_name}</span>
              {status ? <span className={`sc-tag ${status.cls}`}>{status.text}</span> : null}
              {data.wait_level === 'overdue' ? <span className="sc-tag sc-tag-danger"><span className="dot" />已超时 {data.wait_hours} 小时</span> : null}
              {data.wait_level === 'soon' ? <span className="sc-tag sc-tag-warn"><span className="dot" />已等待 {data.wait_hours} 小时</span> : null}
              {data.current_node ? <span className="sc-tag sc-tag-amber">{data.current_node}</span> : null}
              {data.deep_link ? (
                <a className="ac-dr-link" href={data.deep_link} target="_blank" rel="noreferrer">打开完整详情 ↗</a>
              ) : null}
            </div>

            <div className="d-sec">
              <h4>关键信息</h4>
              <dl className="d-kv">
                {(data.fields || []).map(f => (
                  <Fragment key={f.label}>
                    <dt>{f.label}</dt>
                    <dd style={f.emphasis ? { color: '#dc2626', fontWeight: 600 } : undefined}>{f.value ?? '-'}</dd>
                  </Fragment>
                ))}
              </dl>
            </div>

            {(data.progress || []).length > 0 && (
              <div className="d-sec">
                <h4>审批进度 · 按提交时冻结的快照执行</h4>
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
              </div>
            )}

            <div className="d-sec">
              <h4>审批记录</h4>
              <div className="ac-timeline">
                {(data.logs || []).map((lg, i) => (
                  <div key={i} className="ac-tl-item done">
                    <div className="t">{fmt(lg.time)}</div>
                    <div className="what">{lg.who} {lg.action_label || lg.action}</div>
                    {lg.comment ? <div className="who">{lg.comment}</div> : null}
                  </div>
                ))}
              </div>
            </div>
          </>
        ) : !loading ? <Alert type="warning" message="未获取到单据详情" /> : null}
      </Spin>
    </Drawer>
  )
}
