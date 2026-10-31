import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Button, Card, Input, Modal, Spin, message } from 'antd'
import {
  ArrowLeftOutlined, CheckOutlined, CloseOutlined, EditOutlined, FileImageOutlined,
  FilePdfOutlined, PrinterOutlined, SendOutlined, UndoOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { qualityApi, CLAIM_STATUS_MAP, CLAIM_EDITABLE_STATUSES, type ClaimStatus } from '../../../services/quality'
import { canApproveNode } from '../../../utils/approvalNode'
import { waitPill } from '../../../utils'
import { useAuthStore } from '../../../store/auth'
import { fileApi } from '../../../services/api'
import ClaimPaper from '../../../components/ClaimPaper'

const ACTION_TAG: Record<string, { cls: string; text: string }> = {
  submit: { cls: 'sc-tag-kit', text: '提交' },
  approve: { cls: 'sc-tag-done', text: '通过' },
  reject: { cls: 'sc-tag-danger', text: '驳回' },
  recall: { cls: 'sc-tag-amber', text: '撤回' },
  auto_skip: { cls: 'sc-tag-done', text: '自动通过' },
  revoked: { cls: 'sc-tag-amber', text: '撤回审批' },
}
const NODE_STATE: Record<string, { cls: string; text: string }> = {
  done: { cls: 'sc-tag-done', text: '已处理' },
  current: { cls: 'sc-tag-prod', text: '当前节点' },
  todo: { cls: 'sc-tag-wait', text: '待处理' },
  err: { cls: 'sc-tag-danger', text: '已驳回' },
}

const fmt = (v?: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-')

const attIcon = (name?: string) => (String(name || '').toLowerCase().endsWith('.pdf') ? <FilePdfOutlined /> : <FileImageOutlined />)

export default function SupplierClaimDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [r, setR] = useState<any>(null)
  const [comment, setComment] = useState('')
  const [acting, setActing] = useState(false)

  const load = async () => {
    if (!id) return
    try {
      const res: any = await qualityApi.get(parseInt(id))
      setR(res.data)
    } catch { /* 全局拦截器已提示 */ }
  }
  useEffect(() => { load() }, [id]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!r) return <div className="sc-page"><Card styles={{ body: { padding: 60 } }}><Spin /></Card></div>

  const status = r.approval_status
  const s = CLAIM_STATUS_MAP[status as ClaimStatus] || CLAIM_STATUS_MAP.draft
  const snap = r.approval_snapshot || []
  const logs = r.approval_logs || []
  const currentLevel = r.approval_level || 1
  const currentStep = snap.find((n: any) => n.seq === currentLevel)
  const curLogs = logs.filter((l: any) => l.round === r.approval_round)
  const rounds = [...new Set<number>(logs.map((l: any) => l.round))]
  const user = useAuthStore.getState().currentUser
  const isMine = r.applicant === user?.username
  const canAct = status === 'pending' && canApproveNode(user, currentStep)

  const wait = status === 'pending' ? waitPill(r.submitted_at, currentStep?.timeout_hours || 48) : null

  // 进度只看当前轮次（驳回重提后上一轮记录不能把节点标成已处理），与后端 preview 口径一致
  const nodeLog: Record<number, any> = {}
  curLogs.forEach((l: any) => {
    if (['approve', 'reject', 'auto_skip'].includes(l.action)) nodeLog[l.approval_level] = l
  })

  const act = async (action: 'approve' | 'reject') => {
    if (!id) return
    if (action === 'reject' && !comment.trim()) { message.warning('驳回必须填写审批意见'); return }
    setActing(true)
    try {
      const cid = parseInt(id)
      const res: any = action === 'approve'
        ? await qualityApi.approve(cid, comment, r.version)
        : await qualityApi.reject(cid, comment, r.version)
      message.success(res.message || '操作成功')
      setComment('')
      load()
    } catch { /* 全局拦截器已提示 */ } finally { setActing(false) }
  }

  const doRecall = () => Modal.confirm({
    title: '撤回单据',
    okText: '确认撤回',
    content: (
      <div>
        确认撤回 <b className="sc-mono">{r.claim_no}</b>？
        <div className="f-note" style={{ marginTop: 10 }}>
          撤回后回到草稿态可继续编辑；本轮审批记录保留留档，重新提交将开启第 {r.approval_round + 1} 轮。
        </div>
      </div>
    ),
    onOk: async () => {
      try {
        await qualityApi.recall(parseInt(id!))
        message.success('已撤回')
        load()
      } catch { /* 全局拦截器已提示 */ }
    },
  })

  return (
    <div className="sc-page">
      {/* 页头：单号 + 状态 + 按态操作 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/quality/supplier-claims')}>返回台账</Button>
        <span className="sc-mono" style={{ fontSize: 18, fontWeight: 600 }}>{r.claim_no}</span>
        <span className={`sc-tag ${s.cls}`}><span className="dot" />{s.text}</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <Button icon={<PrinterOutlined />} onClick={() => navigate(`/quality/supplier-claims/print/${r.id}`)}>
            {status === 'approved' ? '打印 / 导出 PDF' : '预览打印'}
          </Button>
          {CLAIM_EDITABLE_STATUSES.includes(status) && isMine && (
            <Button icon={<EditOutlined />} onClick={() => navigate(`/quality/supplier-claims/new?edit=${r.id}`)}>编辑</Button>
          )}
          {CLAIM_EDITABLE_STATUSES.includes(status) && isMine && (
            <Button type="primary" icon={<SendOutlined />} loading={acting}
              onClick={async () => {
                try { await qualityApi.submit(r.id); message.success('已提交审批'); load() } catch { /* 全局拦截器已提示 */ }
              }}>
              {status === 'draft' ? '提交审批' : '重新提交'}
            </Button>
          )}
          {status === 'pending' && isMine && <Button icon={<UndoOutlined />} onClick={doRecall}>撤回单据</Button>}
        </div>
      </div>

      <div className="clm-detail-grid">
        {/* 左：纸质单只读（与打印同源） */}
        <Card styles={{ body: { padding: 0 } }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontWeight: 600 }}>供应商索赔通知单</span>
            <span className="sc-note">Supplier Claim Confirmation · 只读版式，归档后按此打印</span>
          </div>
          <div className="clm-paper-wrap"><ClaimPaper claim={r} /></div>
        </Card>

        {/* 右：审批面板（粘性） */}
        <div className="clm-sticky">
          <Card styles={{ body: { padding: '14px 16px' } }}>
            <dl className="clm-kv">
              <dt>申请人</dt><dd>{r.applicant_display || r.applicant || '-'}</dd>
              <dt>{status === 'draft' ? '创建于' : status === 'approved' ? '归档于' : '提交于'}</dt>
              <dd>{status === 'draft' ? fmt(r.created_at) : status === 'approved' ? fmt(r.approved_at) : fmt(r.submitted_at)}</dd>
              {status === 'pending' && currentStep && (
                <><dt>当前节点</dt><dd>{currentStep.label}{wait ? <span className={`ac-due-pill ${wait.level}`} style={{ marginLeft: 6 }}>{wait.text}</span> : null}</dd></>
              )}
              <dt>索赔金额</dt><dd><b style={{ color: '#dc2626', fontSize: 15 }}>¥{r.claim_amount != null ? Number(r.claim_amount).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '-'}</b></dd>
            </dl>
          </Card>

          <Card title={`审批进度 · 第 ${r.approval_round || 0} 轮`} size="small" styles={{ body: { paddingTop: 12 } }}>
            {snap.length === 0 ? (
              <div className="sc-note">暂无审批流程配置（草稿提交时按金额冻结快照）</div>
            ) : (
              <div className="ac-flow">
                {snap.map((n: any, i: number) => {
                  const lg = nodeLog[n.seq]
                  const state = lg ? (lg.action === 'reject' ? 'err' : 'done')
                    : status === 'pending' && n.seq === currentLevel ? 'current' : 'todo'
                  const st = NODE_STATE[state] || NODE_STATE.todo
                  return (
                    <div key={n.seq ?? i} className={`ac-flow-item${state === 'done' ? ' done' : state === 'current' ? ' cur' : ''}`}>
                      <span className="ac-flow-dot" />
                      <div className="ac-flow-head">
                        {i + 1}. {n.label}
                        <span className={`sc-tag ${st.cls}`}>{st.text}</span>
                      </div>
                      <div className="ac-flow-sub">
                        {Array.isArray(n.approvers) ? n.approvers.map((a: any) => a.username || a).join('、') : `角色 ${n.role}`}
                        {lg?.operated_at ? ` · ${fmt(lg.operated_at)}` : ''}
                      </div>
                      {lg?.comment ? <div className="ac-flow-cmt">{lg.comment}</div> : null}
                    </div>
                  )
                })}
              </div>
            )}
            <div className="sc-note" style={{ marginTop: 8, display: 'flex', gap: 6 }}>
              审批链按提交时金额冻结快照；金额条件节点未达标时不进入快照。
            </div>
          </Card>

          {status === 'pending' && (
            <Card title={canAct ? `审批操作 · ${currentStep?.label || ''}` : '审批操作'} size="small">
              {canAct ? (
                <>
                  <Input.TextArea rows={3} value={comment} onChange={e => setComment(e.target.value)}
                    placeholder="审批意见（驳回必填）" />
                  <div style={{ display: 'flex', gap: 8, marginTop: 10, justifyContent: 'flex-end' }}>
                    <Button danger icon={<CloseOutlined />} loading={acting} onClick={() => act('reject')}>驳回</Button>
                    <Button type="primary" icon={<CheckOutlined />} loading={acting} onClick={() => act('approve')}>通过</Button>
                  </div>
                  <div className="f-note" style={{ marginTop: 10 }}>通过可不填意见；驳回必须填写原因，退回申请人修改后可重新提交。</div>
                </>
              ) : (
                <div className="sc-note" style={{ lineHeight: 1.8 }}>
                  当前节点需 {currentStep?.approvers?.map((a: any) => a.username).join('、') || `角色 ${currentStep?.role}`} 审批，
                  您无权在本节点操作；审批也可在「审批中心 → 待办工作台」处理。
                </div>
              )}
            </Card>
          )}

          <Card title="审批记录" size="small" styles={{ body: { paddingTop: 8 } }}>
            {logs.length === 0 ? <div className="sc-note">暂无审批记录——提交后逐条留档，重新提交按轮次分组。</div> : rounds.map(rn => (
              <div key={rn} style={{ marginBottom: rounds[rounds.length - 1] === rn ? 0 : 14 }}>
                <div className="sc-note" style={{ fontWeight: 600, marginBottom: 8 }}>
                  第 {rn} 轮{rn < rounds[rounds.length - 1] ? '（历史存档）' : ''}
                </div>
                <div className="ac-timeline">
                  {logs.filter((l: any) => l.round === rn).map((l: any, i: number) => {
                    const tag = ACTION_TAG[l.action] || { cls: 'sc-tag-wait', text: l.action }
                    return (
                      <div key={i} className="ac-tl-item done">
                        <div className="t sc-mono">{fmt(l.operated_at)}</div>
                        <div className="what">
                          {l.approver} <span className={`sc-tag ${tag.cls}`}>{tag.text}</span>
                          {l.approval_level ? ` · ${snap.find((n: any) => n.seq === l.approval_level)?.label || `L${l.approval_level}`}` : ''}
                        </div>
                        {l.comment ? <div className="who">{l.comment}</div> : null}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))}
          </Card>

          <Card title={`附件（${(r.attachments || []).length}）`} size="small" styles={{ body: { paddingTop: 10 } }}>
            {(r.attachments || []).length === 0 ? <div className="sc-note">无附件</div> : r.attachments.map((a: any, i: number) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', border: '1px solid #f1f5f9', borderRadius: 8, marginBottom: 6, fontSize: 12.5 }}>
                <span className="sc-note">{attIcon(a.name)}</span>
                <a href={fileApi.downloadUrl(a.key)} target="_blank" rel="noreferrer"
                  style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name || a.key}</a>
              </div>
            ))}
          </Card>
        </div>
      </div>
    </div>
  )
}
