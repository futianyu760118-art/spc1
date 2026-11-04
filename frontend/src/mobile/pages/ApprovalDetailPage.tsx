import { useCallback, useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { SpinLoading, Toast } from 'antd-mobile'
import dayjs from 'dayjs'
import { approvalApi, type ApprovalPreview } from '@/services/approval'
import { fileApi } from '@/services/api'
import NavBarSimple from '../components/NavBarSimple'
import MIcon from '../components/MIcon'
import { EmptyState } from '../components/Feedback'

const STATUS_TEXT: Record<string, string> = {
  pending: '审批中',
  approved: '已通过',
  rejected: '已驳回',
  recalled: '已撤回',
}
const STATUS_CHIP: Record<string, string> = {
  pending: 'm-chip--progress',
  approved: 'm-chip--done',
  rejected: 'm-chip--high',
  recalled: 'm-chip--cancel',
}
const NODE_STATE_TEXT: Record<string, string> = { done: '已处理', current: '当前节点', todo: '待处理' }
const NODE_STATE_CHIP: Record<string, string> = {
  done: 'm-chip--done',
  current: 'm-chip--progress',
  todo: 'm-chip--cancel',
}

const fmtDateTime = (v?: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-')

export default function ApprovalDetailPage() {
  const { bizType, id } = useParams<{ bizType: string; id: string }>()
  const itemId = Number(id)
  const navigate = useNavigate()
  const [data, setData] = useState<ApprovalPreview | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [comment, setComment] = useState('')
  const [acting, setActing] = useState<'approve' | 'reject' | null>(null)

  const load = useCallback(async () => {
    if (!bizType || !Number.isFinite(itemId) || itemId <= 0) {
      setLoading(false)
      setFailed(true)
      return
    }
    setLoading(true)
    setFailed(false)
    try {
      const res: any = await approvalApi.preview(bizType, itemId)
      setData(res.data || null)
    } catch {
      setFailed(true)
    } finally {
      setLoading(false)
    }
  }, [bizType, itemId])

  useEffect(() => { load() }, [load])

  const act = async (action: 'approve' | 'reject') => {
    if (!bizType || !data) return
    if (action === 'reject' && !comment.trim()) {
      Toast.show({ content: '驳回必须填写审批意见' })
      return
    }
    setActing(action)
    try {
      const payload = { comment: comment.trim(), expected_version: data.version }
      const res: any = action === 'approve'
        ? await approvalApi.approve(bizType, itemId, payload)
        : await approvalApi.reject(bizType, itemId, payload)
      Toast.show({ content: res.message || '操作成功' })
      setComment('')
      await load()
    } catch {
      // 全局拦截器已提示
    } finally {
      setActing(null)
    }
  }

  return (
    <div className="m-page m-page--full">
      <NavBarSimple title="审批详情" onBack={() => navigate(-1)} />

      <div className="m-page__scroll">
        {loading && !data && (
          <div style={{ textAlign: 'center', padding: 40 }}>
            <SpinLoading color="primary" />
          </div>
        )}
        {!loading && failed && <EmptyState icon="warn" text="加载失败，请稍后重试" />}
        {!loading && !failed && !data && <EmptyState text="未找到该审批单据" />}

        {!failed && data && (
          <>
            <div className="m-card">
              <div className="ad-head">
                <div className="ad-title">{data.title || data.no || '-'}</div>
                {data.status && (
                  <span className={`m-chip ${STATUS_CHIP[data.status] || 'm-chip--cancel'}`}>
                    {STATUS_TEXT[data.status] || data.status}
                  </span>
                )}
              </div>
              <div className="ad-tags">
                {data.biz_name && <span className="m-chip m-chip--low">{data.biz_name}</span>}
                {data.current_node && <span className="m-chip m-chip--progress">{data.current_node}</span>}
                {data.wait_level === 'overdue' && (
                  <span className="m-chip m-chip--high">已超时 {data.wait_hours} 小时</span>
                )}
                {data.wait_level === 'soon' && (
                  <span className="m-chip m-chip--mid">已等待 {data.wait_hours} 小时</span>
                )}
              </div>
              <div className="info-row"><span className="lab">单号</span><span className="val">{data.no || '-'}</span></div>
              <div className="info-row"><span className="lab">申请人</span><span className="val">{data.applicant || '-'}</span></div>
              <div className="info-row"><span className="lab">提交时间</span><span className="val">{fmtDateTime(data.submitted_at)}</span></div>
            </div>

            <div className="m-card">
              <div className="m-card__title">业务详情</div>
              {(data.fields || []).length === 0 ? (
                <div className="ad-empty">暂无业务字段</div>
              ) : (
                (data.fields || []).map((f) => (
                  <div className="info-row" key={f.label}>
                    <span className="lab">{f.label}</span>
                    <span
                      className="val"
                      style={f.emphasis ? { color: 'var(--spc-danger)', fontWeight: 700 } : undefined}
                    >
                      {f.value ?? '-'}
                    </span>
                  </div>
                ))
              )}
            </div>

            <div className="m-card">
              <div className="m-card__title">审批进度</div>
              {(data.progress || []).length === 0 ? (
                <div className="ad-empty">暂无审批流程</div>
              ) : (
                <div className="ad-flow">
                  {(data.progress || []).map((n, i) => (
                    <div className={`ad-flow__item ${n.state}`} key={n.seq ?? i}>
                      <span className="ad-flow__dot" />
                      <div className="ad-flow__body">
                        <div className="ad-flow__head">
                          <span>{n.label || `节点 ${i + 1}`}</span>
                          <span className={`m-chip ${NODE_STATE_CHIP[n.state] || 'm-chip--cancel'}`}>
                            {NODE_STATE_TEXT[n.state] || n.state}
                          </span>
                        </div>
                        <div className="ad-flow__sub">
                          {n.approver_label || '-'}{n.acted_at ? ` · ${fmtDateTime(n.acted_at)}` : ''}
                        </div>
                        {n.comment && <div className="ad-flow__cmt">{n.comment}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="m-card">
              <div className="m-card__title">审批操作</div>
              {data.can_act ? (
                <>
                  <textarea
                    className="ad-comment"
                    rows={3}
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                    placeholder="审批意见（驳回必填）"
                  />
                  <div className="ad-actions">
                    <button className="mbtn mbtn--danger-o" disabled={!!acting} onClick={() => act('reject')}>
                      {acting === 'reject' ? '提交中…' : '驳回'}
                    </button>
                    <button className="mbtn mbtn--deep" disabled={!!acting} onClick={() => act('approve')}>
                      {acting === 'approve' ? '提交中…' : '通过'}
                    </button>
                  </div>
                </>
              ) : (
                <div className="ad-hint">{data.action_hint || '当前单据不可在审批中心内操作'}</div>
              )}
            </div>

            {(data.logs || []).length > 0 && (
              <div className="m-card">
                <div className="m-card__title">审批记录</div>
                {(data.logs || []).map((lg, i) => (
                  <div className="ad-log" key={i}>
                    <div className="ad-log__head">
                      <span>{lg.who || '-'} {lg.action_label || lg.action || ''}</span>
                      <span>{fmtDateTime(lg.time)}</span>
                    </div>
                    {lg.comment && <div className="ad-log__cmt">{lg.comment}</div>}
                  </div>
                ))}
              </div>
            )}

            {(data.attachments || []).length > 0 && (
              <div className="m-card">
                <div className="m-card__title">{`附件（${(data.attachments || []).length}）`}</div>
                {(data.attachments || []).map((a, i) => (
                  <a className="ad-att" key={i} href={fileApi.downloadUrl(a.key)} target="_blank" rel="noreferrer">
                    <MIcon name="clipboard" size={16} />
                    <span>{a.name || a.key}</span>
                  </a>
                ))}
              </div>
            )}

            <div style={{ height: 20 }} />
          </>
        )}
      </div>
    </div>
  )
}
