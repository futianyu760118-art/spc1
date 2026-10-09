import { useEffect, useRef, useState, type CSSProperties, type MutableRefObject, type ReactNode } from 'react'
import { Table, Button, Space, Input, Select, Form, message, Modal, Image, Tooltip, Typography } from 'antd'
import {
  ReloadOutlined, SearchOutlined, DeleteOutlined, MessageOutlined,
  DownloadOutlined, PaperClipOutlined, ClockCircleOutlined,
  SyncOutlined, CheckCircleOutlined, CloseCircleOutlined,
  CheckOutlined, LoadingOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { feedbackApi } from '../../../services/api'
import { useAuthStore } from '../../../store/auth'
import { useTableScrollY } from '../../../hooks/useTableScrollY'
import { useSearchParams } from 'react-router-dom'
import KpiBand, { type KpiItem } from '../components/KpiBand'
import ChipsFilter, { type ChipOption } from '../components/ChipsFilter'
import BdDrawer, { DrawerSection, KvGrid } from '../components/BdDrawer'
import Markdown from '../../../components/Markdown'

const typeMeta: Record<string, { label: string; cls: string }> = {
  issue: { label: '问题', cls: 'sc-tag-danger' },
  suggestion: { label: '建议', cls: 'sc-tag-kit' },
  inquiry: { label: '咨询', cls: 'sc-tag-done' },
}
const severityMeta: Record<string, { label: string; cls: string }> = {
  low: { label: '低', cls: 'sc-tag-wait' },
  medium: { label: '中', cls: 'sc-tag-warn' },
  high: { label: '高', cls: 'sc-tag-danger' },
}
const statusMeta: Record<string, { label: string; cls: string }> = {
  pending: { label: '待处理', cls: 'sc-tag-warn' },
  processing: { label: '处理中', cls: 'sc-tag-kit' },
  resolved: { label: '已解决', cls: 'sc-tag-done' },
  closed: { label: '已关闭', cls: 'sc-tag-wait' },
}

const aiStatusMeta: Record<string, { label: string; cls: string }> = {
  queued: { label: '排队中', cls: 'sc-tag-wait' },
  running: { label: '实现中', cls: 'sc-tag-kit' },
  done: { label: '已实现', cls: 'sc-tag-done' },
  failed: { label: '失败', cls: 'sc-tag-danger' },
}

const aiStageMeta: Record<string, { label: string }> = {
  preparing: { label: '准备隔离环境' },
  fetching: { label: '下载附件' },
  agent: { label: 'AI 修改代码' },
  gate_backend: { label: '后端测试' },
  gate_frontend: { label: '前端构建' },
  committing: { label: '提交代码' },
}

const stageEntries = (list?: any[]) => (list || []).filter((e: any) => e?.kind === 'stage')
const actionEntries = (list?: any[]) => (list || []).filter((e: any) => e?.kind === 'action')
const fmtClock = (t?: string | null) => (t ? dayjs(t).format('HH:mm:ss') : '')
const elapsedMinutes = (from?: string | null) => {
  if (!from) return 0
  return Math.max(0, dayjs().diff(dayjs(from), 'minute'))
}

const SEC_LABEL: CSSProperties = {
  fontSize: 'calc(12px * var(--font-size-scale))', color: '#94a3b8',
  fontWeight: 600, letterSpacing: '0.05em', marginBottom: 8,
}

const ACTION_PREFIX_COLORS: Array<[string, string]> = [
  ['执行命令', '#c4b5fd'],
  ['读取', '#7dd3fc'],
  ['修改', '#fdba74'],
  ['新建', '#86efac'],
]
const actionColor = (text: string) => ACTION_PREFIX_COLORS.find(([p]) => text?.startsWith(p))?.[1] || '#cbd5e1'

const FILE_STATUS_META: Record<string, { label: string; bg: string; color: string }> = {
  A: { label: '新增', bg: '#dcfce7', color: '#15803d' },
  M: { label: '修改', bg: '#ffedd5', color: '#c2410c' },
  D: { label: '删除', bg: '#fee2e2', color: '#b91c1c' },
}
const fileBadge = (status: string) => {
  const m = FILE_STATUS_META[status] || FILE_STATUS_META.M
  return (
    <span style={{
      background: m.bg, color: m.color, borderRadius: 4, padding: '0 6px',
      fontSize: 'calc(11px * var(--font-size-scale))', fontWeight: 600, flexShrink: 0,
    }}>{m.label}</span>
  )
}

const GATE_NAME_LABELS: Record<string, string> = { backend: '后端测试', frontend: '前端构建' }
const fmtDuration = (seconds?: number | null) => {
  if (seconds == null) return ''
  return seconds >= 60 ? `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒` : `${seconds} 秒`
}

const STATUS_CLS = (k?: string) => (k ? statusMeta[k]?.cls || 'sc-tag-plain' : 'sc-tag-plain')
const STATUS_LBL = (k?: string) => (k ? statusMeta[k]?.label || k : '—')

const AVATAR_GRADIENTS = [
  'linear-gradient(135deg,#5b5bd6,#8b5cf6)',
  'linear-gradient(135deg,#0ea5e9,#14b8a6)',
  'linear-gradient(135deg,#f59e0b,#f43f5e)',
  'linear-gradient(135deg,#16a34a,#0ea5e9)',
]
const avatarColor = (name: string) => {
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0
  return AVATAR_GRADIENTS[h % AVATAR_GRADIENTS.length]
}

const timeAgo = (t?: string | null) => {
  if (!t) return ''
  const diff = dayjs().diff(dayjs(t), 'minute')
  if (diff < 1) return '刚刚'
  if (diff < 60) return `${diff} 分钟前`
  const h = Math.floor(diff / 60)
  if (h < 24) return `${h} 小时前`
  return `${Math.floor(h / 24)} 天前`
}

const Operator = ({ name, dim }: { name?: string | null; dim?: boolean }) =>
  name ? (
    <span className="sys-op">
      <span className="um-avatar" style={{ background: dim ? 'linear-gradient(135deg,#94a3b8,#64748b)' : avatarColor(name) }}>
        {name.slice(0, 1)}
      </span>
      <span className="sys-op-name" style={dim ? { color: '#94a3b8' } : undefined}>{name}</span>
    </span>
  ) : <span className="sc-note">—</span>

const TERMINAL_PANEL: CSSProperties = {
  background: '#0f172a', borderRadius: 8,
  fontFamily: 'Consolas, Menlo, monospace',
  fontSize: 'calc(12px * var(--font-size-scale))',
}

function AiSection({
  detail, action, actionBoxRef, filesExpanded, onToggleFiles, openGate, onToggleGate,
}: {
  detail: any
  action: ReactNode
  actionBoxRef: MutableRefObject<HTMLDivElement | null>
  filesExpanded: boolean
  onToggleFiles: () => void
  openGate: string | null
  onToggleGate: (key: string) => void
}) {
  const result = detail.ai_result || null
  const stages = stageEntries(detail.ai_progress)
  const actions = actionEntries(detail.ai_progress)
  const files = result?.files || []
  const gates = result?.gates || []
  const totalAdd = files.reduce((s: number, f: any) => s + (f.additions || 0), 0)
  const totalDel = files.reduce((s: number, f: any) => s + (f.deletions || 0), 0)
  const visibleFiles = filesExpanded ? files : files.slice(0, 8)

  return (
    <>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
        <span className={`sc-tag ${aiStatusMeta[detail.ai_status]?.cls || 'sc-tag-plain'}`}>
          {aiStatusMeta[detail.ai_status]?.label || detail.ai_status}
        </span>
        {detail.ai_branch && (
          <Typography.Text copyable className="sc-mono" style={{ fontSize: 'calc(12px * var(--font-size-scale))', color: '#475569' }}>
            {detail.ai_branch}
          </Typography.Text>
        )}
        {(detail.ai_requested_by || detail.ai_requested_at) && (
          <span className="sc-note">
            {detail.ai_requested_by ? `${detail.ai_requested_by} 派单` : '派单'}
            {detail.ai_requested_at ? ` · ${dayjs(detail.ai_requested_at).format('MM-DD HH:mm')}` : ''}
          </span>
        )}
        {action}
      </div>

      {stages.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={SEC_LABEL}>执行进度</div>
          {stages.map((e: any, i: number, arr: any[]) => {
            const isCurrent = detail.ai_status === 'running' && detail.ai_stage === e.stage
            const next = arr[i + 1]
            const duration = next ? dayjs(next.at).diff(dayjs(e.at), 'minute') : null
            return (
              <div key={`stage-${i}-${e.stage}`} style={{ display: 'flex', gap: 10 }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', alignSelf: 'stretch' }}>
                  <span style={{
                    width: 24, height: 24, borderRadius: '50%', flexShrink: 0,
                    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 12,
                    background: isCurrent ? '#eef0ff' : '#f0fdf4',
                    color: isCurrent ? '#5b5bd6' : '#16a34a',
                    boxShadow: isCurrent ? '0 0 0 3px rgba(91,91,214,.12)' : undefined,
                  }}>
                    {isCurrent ? <LoadingOutlined spin /> : <CheckOutlined />}
                  </span>
                  {i < arr.length - 1 && <span style={{ width: 2, flex: 1, minHeight: 10, background: '#e2e8f0', margin: '2px 0' }} />}
                </div>
                <div style={{ paddingBottom: i < arr.length - 1 ? 12 : 0, minWidth: 0, flex: 1 }}>
                  <span style={{ fontSize: 'calc(13px * var(--font-size-scale))', color: isCurrent ? '#0f172a' : '#334155', fontWeight: isCurrent ? 600 : 500 }}>
                    {aiStageMeta[e.stage]?.label || e.text || e.stage}
                  </span>
                  <span className="sc-note" style={{ marginLeft: 8 }}>{fmtClock(e.at)}</span>
                  {isCurrent
                    ? <span className="sc-note" style={{ marginLeft: 8 }}>已运行 {elapsedMinutes(detail.ai_stage_started_at)} 分钟</span>
                    : duration !== null && <span className="sc-note" style={{ marginLeft: 8 }}>耗时 {duration} 分钟</span>}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {actions.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ ...SEC_LABEL, marginBottom: 6 }}>最近动作（{actions.length}）</div>
          <div ref={actionBoxRef} style={{ ...TERMINAL_PANEL, padding: '10px 12px', maxHeight: 240, overflow: 'auto', lineHeight: 1.9 }}>
            {actions.map((e: any, i: number) => (
              <div key={`action-${i}`} style={{ display: 'flex', gap: 10 }}>
                <span style={{ color: '#475569', flexShrink: 0 }}>{fmtClock(e.at)}</span>
                <span style={{ color: actionColor(e.text), whiteSpace: 'pre-wrap', wordBreak: 'break-all', minWidth: 0 }}>{e.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(detail.ai_status === 'done' || detail.ai_status === 'failed') && (result ? (
        <div style={{ marginTop: 12 }}>
          {detail.ai_status === 'failed' && result.error && (
            <div style={{
              background: '#fef2f2', border: '1px solid #fecaca', borderRadius: 8,
              padding: '8px 12px', whiteSpace: 'pre-wrap', wordBreak: 'break-all',
              fontSize: 'calc(12.5px * var(--font-size-scale))', color: '#b91c1c', lineHeight: 1.7, marginBottom: 10,
            }}>
              {result.error}
            </div>
          )}
          {detail.ai_status === 'done' && result.summary && (
            <div style={{
              background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8,
              padding: '8px 12px', fontSize: 'calc(12.5px * var(--font-size-scale))', color: '#334155', lineHeight: 1.7, marginBottom: 10,
            }}>
              <Markdown>{result.summary}</Markdown>
            </div>
          )}
          {files.length > 0 && (
            <div style={{ marginBottom: 10 }}>
              <div style={SEC_LABEL}>
                改动文件 · {files.length} 个
                <span style={{ color: '#16a34a', margin: '0 4px' }}>+{totalAdd}</span>
                <span style={{ color: '#dc2626' }}>-{totalDel}</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {visibleFiles.map((f: any, i: number) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 }}>
                    {fileBadge(f.status)}
                    <span className="sc-mono" style={{ fontSize: 'calc(12px * var(--font-size-scale))', color: '#334155', wordBreak: 'break-all', minWidth: 0, flex: 1 }}>
                      {f.path}
                    </span>
                    {(f.additions > 0 || f.deletions > 0) && (
                      <span style={{ fontSize: 'calc(11.5px * var(--font-size-scale))', flexShrink: 0 }}>
                        <span style={{ color: '#16a34a' }}>+{f.additions}</span>
                        <span style={{ color: '#dc2626' }}> / -{f.deletions}</span>
                      </span>
                    )}
                  </div>
                ))}
              </div>
              {files.length > 8 && (
                <a style={{ fontSize: 'calc(12px * var(--font-size-scale))', marginTop: 4, display: 'inline-block' }} onClick={onToggleFiles}>
                  {filesExpanded ? '收起' : `展开全部 ${files.length} 个文件`}
                </a>
              )}
            </div>
          )}
          {gates.length > 0 && (
            <div>
              <div style={SEC_LABEL}>门禁结果</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {gates.map((g: any) => {
                  const key = String(g.name)
                  const isOpen = openGate === key
                  return (
                    <div key={key} style={{ border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', background: '#f8fafc', flexWrap: 'wrap' }}>
                        <span style={{ fontSize: 'calc(12.5px * var(--font-size-scale))', fontWeight: 600, color: '#334155' }}>
                          {GATE_NAME_LABELS[g.name] || g.name}
                        </span>
                        {g.passed ? (
                          <span style={{ color: '#16a34a', fontSize: 'calc(12px * var(--font-size-scale))', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <CheckCircleOutlined />通过
                          </span>
                        ) : (
                          <span style={{ color: '#dc2626', fontSize: 'calc(12px * var(--font-size-scale))', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                            <CloseCircleOutlined />失败
                          </span>
                        )}
                        {g.exitCode != null && g.exitCode !== 0 && <span className="sc-mono sc-note">exit={g.exitCode}</span>}
                        {g.durationSeconds != null && <span className="sc-note">{fmtDuration(g.durationSeconds)}</span>}
                        {g.outputTail && (
                          <a style={{ marginLeft: 'auto', fontSize: 'calc(12px * var(--font-size-scale))' }} onClick={() => onToggleGate(key)}>
                            {isOpen ? '收起输出' : '查看输出'}
                          </a>
                        )}
                      </div>
                      {isOpen && g.outputTail && (
                        <pre style={{
                          ...TERMINAL_PANEL, margin: 0, padding: '8px 10px', maxHeight: 200, overflow: 'auto',
                          fontSize: 'calc(11.5px * var(--font-size-scale))', color: '#cbd5e1', lineHeight: 1.7,
                          whiteSpace: 'pre-wrap', wordBreak: 'break-all',
                        }}>
                          {g.outputTail}
                        </pre>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )}
          {result.runDir && (
            <div className="sc-note sc-mono" style={{ marginTop: 10, wordBreak: 'break-all' }}>
              运行日志：{result.runDir}（开发机）
            </div>
          )}
        </div>
      ) : detail.ai_note ? (
        <div style={{
          marginTop: 12, background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8,
          padding: '8px 12px', whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto',
          fontSize: 'calc(12.5px * var(--font-size-scale))', color: '#334155', lineHeight: 1.7,
        }}>
          {detail.ai_note}
        </div>
      ) : null)}
    </>
  )
}

export default function FeedbackManagement() {
  const hasPermission = useAuthStore(s => s.hasPermission)
  const canHandle = hasPermission('basicdata.feedback.handle', 'handle') || hasPermission('basicdata.feedback', 'update')
  const canDelete = hasPermission('basicdata.feedback', 'delete')

  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState<any>({ total: 0, pending: 0, processing: 0, resolved: 0, closed: 0 })
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const [keyword, setKeyword] = useState<string>('')
  const [filterType, setFilterType] = useState<string | undefined>(undefined)
  const [filterSeverity, setFilterSeverity] = useState<string | undefined>(undefined)
  const [filterStatus, setFilterStatus] = useState<string | undefined>(undefined)
  const [filterAiStatus, setFilterAiStatus] = useState<string | undefined>(undefined)
  const [aiBusyId, setAiBusyId] = useState<number | null>(null)
  const [aiConfirm, setAiConfirm] = useState<{ record: any } | null>(null)
  const [sortInfo, setSortInfo] = useState<{ sort_by?: string; sort_order?: string }>({})

  const [detail, setDetail] = useState<any>(null)
  const [filesExpanded, setFilesExpanded] = useState(false)
  const [openGate, setOpenGate] = useState<string | null>(null)
  const [replyForm] = Form.useForm()
  const [replying, setReplying] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<any>(null)
  const [deleting, setDeleting] = useState(false)
  const [statusConfirm, setStatusConfirm] = useState<{ next: string } | null>(null)
  const [statusUpdating, setStatusUpdating] = useState(false)

  // 页面高度约束在视口内（同 Inventory / ScrapInventory 模式），表格体内部滚动，窗口不出滚动条
  const tableWrapRef = useRef<HTMLDivElement | null>(null)
  const actionBoxRef = useRef<HTMLDivElement | null>(null)
  const [, setProgressTick] = useState(0)
  const scrollY = useTableScrollY(tableWrapRef, [data.length, pagination.total])

  const fetchData = async (
    page = pagination.current,
    pageSize = pagination.pageSize,
    overrides: { kw?: string; type?: string; severity?: string; status?: string; aiStatus?: string } = {},
  ) => {
    setLoading(true)
    try {
      const params: any = { page, page_size: pageSize }
      const k = (overrides.kw !== undefined ? overrides.kw : keyword).trim()
      if (k) params.keyword = k
      const t = overrides.type !== undefined ? overrides.type : filterType
      const s = overrides.severity !== undefined ? overrides.severity : filterSeverity
      const st = overrides.status !== undefined ? overrides.status : filterStatus
      const aiSt = overrides.aiStatus !== undefined ? overrides.aiStatus : filterAiStatus
      if (aiSt) params.ai_status = aiSt
      if (t) params.type = t
      if (s) params.severity = s
      if (st) params.status = st
      if (sortInfo.sort_by) params.sort_by = sortInfo.sort_by
      if (sortInfo.sort_order) params.sort_order = sortInfo.sort_order
      const res: any = await feedbackApi.list(params)
      const items = res.data?.items || []
      setData(items)
      setDetail((prev: any) => (prev ? items.find((i: any) => i.id === prev.id) || prev : prev))
      setStats(res.data?.stats || stats)
      setPagination({ current: res.data?.page || 1, pageSize: res.data?.page_size || 20, total: res.data?.total || 0 })
    } catch {
      // 错误已由全局拦截器提示
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData(1) }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 自动搜索（输入即搜，300ms 防抖）
  useEffect(() => {
    const t = setTimeout(() => { fetchData(1, pagination.pageSize) }, 300)
    return () => clearTimeout(t)
  }, [keyword, filterType, filterSeverity, filterStatus, filterAiStatus, sortInfo]) // eslint-disable-line react-hooks/exhaustive-deps

  const openDetail = (record: any) => {
    setDetail(record)
    setFilesExpanded(false)
    setOpenGate(null)
    replyForm.setFieldsValue({ reply: '', status: undefined })
  }

  const [searchParams, setSearchParams] = useSearchParams()
  const urlSearchAppliedRef = useRef(false)

  // 从通知中心跳转而来:读取 ?id= 并自动打开该条反馈详情
  useEffect(() => {
    if (urlSearchAppliedRef.current) return
    const idParam = searchParams.get('id')
    if (!idParam) return
    urlSearchAppliedRef.current = true
    const newParams = new URLSearchParams(searchParams)
    newParams.delete('id')
    setSearchParams(newParams, { replace: true })
    feedbackApi.get(Number(idParam)).then((res: any) => {
      if (res?.data) openDetail(res.data)
    }).catch(() => {
      // 错误已由全局拦截器提示
    })
  }, [searchParams, setSearchParams])

  // AI 任务进行中时每 15s 自动刷新
  useEffect(() => {
    const hasActiveAi = data.some((r: any) => r.ai_status === 'queued' || r.ai_status === 'running')
    if (!hasActiveAi) return
    const timer = setInterval(() => { fetchData() }, 15000)
    return () => clearInterval(timer)
  }, [data]) // eslint-disable-line react-hooks/exhaustive-deps

  // AI 执行中：当前阶段耗时每 30s 重算
  useEffect(() => {
    if (detail?.ai_status !== 'running') return
    const timer = setInterval(() => setProgressTick(t => t + 1), 30000)
    return () => clearInterval(timer)
  }, [detail?.ai_status, detail?.ai_stage]) // eslint-disable-line react-hooks/exhaustive-deps

  // 动作列表更新时自动滚到底部
  useEffect(() => {
    const el = actionBoxRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [detail?.ai_progress?.length, detail?.ai_stage])

  const handleReply = async () => {
    try {
      const values = await replyForm.validateFields()
      if (!values.reply && !values.status) {
        message.warning('请填写回复内容或选择状态')
        return
      }
      setReplying(true)
      const res: any = await feedbackApi.reply(detail.id, values)
      message.success('已保存')
      setDetail(res.data)
      fetchData()
    } catch (e: any) {
      if (e?.errorFields) return
      // 错误已由全局拦截器提示
    } finally {
      setReplying(false)
    }
  }

  const doChangeStatus = async (status: string) => {
    setStatusUpdating(true)
    try {
      const res: any = await feedbackApi.updateStatus(detail.id, status)
      message.success(`状态已更新为「${(statusMeta[status] || {}).label || status}」`)
      setDetail(res.data)
      replyForm.setFieldsValue({ status: undefined })
      fetchData()
    } catch (e: any) {
      // 错误已由全局拦截器提示
    } finally {
      setStatusUpdating(false)
      setStatusConfirm(null)
    }
  }

  const changeStatus = (status: string, needConfirm: boolean) => {
    if (needConfirm) setStatusConfirm({ next: status })
    else doChangeStatus(status)
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await feedbackApi.remove(deleteTarget.id)
      message.success('已删除')
      setDeleteTarget(null)
      if (detail?.id === deleteTarget.id) setDetail(null)
      fetchData()
    } catch (e: any) {
      // 错误已由全局拦截器提示
    } finally {
      setDeleting(false)
    }
  }

  const handleAi = async (action: 'queue' | 'cancel', record: any) => {
    setAiBusyId(record.id)
    try {
      const res: any = action === 'queue'
        ? await feedbackApi.aiQueue(record.id)
        : await feedbackApi.aiCancel(record.id)
      message.success(action === 'queue' ? '已派给 AI，等待 runner 处理' : '已取消排队')
      if (detail?.id === record.id) setDetail(res.data)
      fetchData()
    } catch {
      // 错误已由全局拦截器提示
    } finally {
      setAiBusyId(null)
      setAiConfirm(null)
    }
  }

  const aiAction = (r: any) => {
    if (aiBusyId === r.id) return <SyncOutlined spin />
    if (r.ai_status === 'queued') return <a onClick={() => handleAi('cancel', r)}>取消排队</a>
    if (r.status === 'resolved' || r.status === 'closed') return null
    if (r.ai_status === 'running') return <a onClick={() => setAiConfirm({ record: r })}>重新排队</a>
    if (r.ai_status === 'failed') return <a onClick={() => handleAi('queue', r)}>重试</a>
    if (r.ai_status === 'done') return null
    return <a onClick={() => handleAi('queue', r)}>交 AI 实现</a>
  }

  // ---------- 状态流转按钮 ----------
  const statusButtons = (s: string) => {
    const btns: { text: string; type: any; confirm?: boolean; danger?: boolean; status: string }[] = []
    if (canHandle) {
      if (s === 'pending') {
        btns.push({ text: '开始处理', status: 'processing', type: 'default' })
        btns.push({ text: '标记已解决', status: 'resolved', type: 'primary', confirm: true })
        btns.push({ text: '关闭反馈', status: 'closed', type: 'default', confirm: true, danger: true })
      } else if (s === 'processing') {
        btns.push({ text: '标记已解决', status: 'resolved', type: 'primary', confirm: true })
        btns.push({ text: '关闭反馈', status: 'closed', type: 'default', confirm: true, danger: true })
      } else if (s === 'resolved') {
        btns.push({ text: '重开处理', status: 'processing', type: 'default' })
        btns.push({ text: '关闭反馈', status: 'closed', type: 'default', confirm: true, danger: true })
      } else if (s === 'closed') {
        btns.push({ text: '重新打开', status: 'pending', type: 'default' })
      }
    } else if (s === 'resolved') {
      btns.push({ text: '确认关闭', status: 'closed', type: 'primary', confirm: true, danger: true })
    } else if (s === 'closed') {
      btns.push({ text: '重新打开', status: 'pending', type: 'default' })
    }
    return btns
  }

  const kpiItems: KpiItem[] = [
    { label: '待处理', value: stats.pending, go: '优先处理 · 查看 →', accent: 'warning', icon: <ClockCircleOutlined />, onClick: () => setFilterStatus('pending') },
    { label: '处理中', value: stats.processing, sub: '跟进中的反馈', accent: 'info', icon: <SyncOutlined spin={stats.processing > 0} />, onClick: () => setFilterStatus('processing') },
    { label: '已解决', value: stats.resolved, sub: '闭环留痕', accent: 'success', icon: <CheckCircleOutlined />, onClick: () => setFilterStatus('resolved') },
    { label: '已关闭', value: stats.closed, sub: '无需处理 / 超时关闭', accent: 'gray', icon: <CloseCircleOutlined />, onClick: () => setFilterStatus('closed') },
    { label: '反馈总数', value: stats.total, sub: '问题 / 建议 / 咨询', accent: 'brand', icon: <MessageOutlined />, onClick: () => setFilterStatus(undefined) },
  ]

  const chipOptions: ChipOption[] = [
    { label: '全部', value: 'all', count: stats.total },
    { label: '待处理', value: 'pending', count: stats.pending, hot: true },
    { label: '处理中', value: 'processing', count: stats.processing },
    { label: '已解决', value: 'resolved', count: stats.resolved },
    { label: '已关闭', value: 'closed', count: stats.closed },
  ]

  const renderTitle = (record: any) => (
    <span>
      <span
        className="sc-mat-name"
        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
        onClick={() => openDetail(record)}
      >
        <span className="sc-mono" style={{ color: '#94a3b8', fontFamily: 'Consolas, Menlo, monospace', fontSize: 'calc(11px * var(--font-size-scale))' }}>#{record.id}</span>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{record.title}</span>
      </span>
      <div className="sys-op-sub" style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <PaperClipOutlined style={{ fontSize: 11 }} /> {record.page_path || '—'}
      </div>
    </span>
  )

  const columns: any[] = [
    { title: '标题', key: 'title', width: 320, render: (_: any, r: any) => renderTitle(r) },
    {
      title: '类型', dataIndex: 'type', key: 'type', width: 90,
      render: (v: string) => <span className={`sc-tag ${typeMeta[v]?.cls || 'sc-tag-plain'}`}>{typeMeta[v]?.label || v}</span>,
    },
    {
      title: '严重度', dataIndex: 'severity', key: 'severity', width: 90,
      render: (v: string) => <span className={`sc-tag ${severityMeta[v]?.cls || 'sc-tag-plain'}`}>{severityMeta[v]?.label || v}</span>,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 105,
      render: (v: string) => <span className={`sc-tag ${statusMeta[v]?.cls || 'sc-tag-plain'}`}><span className="dot" />{statusMeta[v]?.label || v}</span>,
    },
    {
      title: 'AI 实现', dataIndex: 'ai_status', key: 'ai_status', width: 70,
      render: (v: string) => (
        <Tooltip title={aiStatusMeta[v]?.label || '未派单'}>
          <span className={`fb-ai-lamp fb-ai-lamp--${v || 'none'}`} />
        </Tooltip>
      ),
    },
    { title: '提交人', dataIndex: 'submitter_name', key: 'submitter_name', width: 140, render: (v: string) => <Operator name={v} /> },
    {
      title: '提交时间', dataIndex: 'created_at', key: 'created_at', width: 170,
      render: (v: string) => (
        <span className="sys-tm">
          <div className="sc-mono">{v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '—'}</div>
          <div className="ago">{timeAgo(v)}</div>
        </span>
      ),
    },
    {
      title: '回复人', key: 'replied_by', width: 130,
      render: (_: any, r: any) => (r.replied_by ? <Operator name={r.replied_by} /> : <span className="sc-note">—</span>),
    },
    {
      title: '操作', key: 'action', width: 190, fixed: 'right' as const,
      render: (_: any, r: any) => (
        <span className="sc-row-act">
          <a onClick={() => openDetail(r)}>查看</a>
          {canHandle && aiAction(r)}
          {canDelete && <a style={{ color: '#dc2626' }} onClick={() => setDeleteTarget(r)}>删除</a>}
        </span>
      ),
    },
  ]

  return (
    <div className="sc-page" style={{ height: 'calc(100vh - 104px)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div style={{ flexShrink: 0 }}>
        <KpiBand items={kpiItems} />
      </div>

      <div className="sc-toolbar" style={{ flexShrink: 0 }}>
        <span className="sc-search">
          <Input
            allowClear
            prefix={<SearchOutlined style={{ color: '#94a3b8' }} />}
            placeholder="标题 / 所在页面 / 提交人 / 回复人"
            style={{ width: 280 }}
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        </span>
        <Select
          allowClear
          placeholder="全部类型"
          style={{ width: 120 }}
          value={filterType}
          onChange={setFilterType}
          options={Object.entries(typeMeta).map(([k, v]) => ({ label: v.label, value: k }))}
        />
        <Select
          allowClear
          placeholder="全部严重度"
          style={{ width: 130 }}
          value={filterSeverity}
          onChange={setFilterSeverity}
          options={Object.entries(severityMeta).map(([k, v]) => ({ label: v.label, value: k }))}
        />
        <Select
          allowClear
          placeholder="全部 AI 状态"
          style={{ width: 140 }}
          value={filterAiStatus}
          onChange={setFilterAiStatus}
          options={[
            { label: '未派单', value: 'none' },
            { label: '排队中', value: 'queued' },
            { label: '实现中', value: 'running' },
            { label: '已实现', value: 'done' },
            { label: '失败', value: 'failed' },
          ]}
        />
        <ChipsFilter
          options={chipOptions}
          value={filterStatus ?? 'all'}
          onChange={(v) => setFilterStatus(v === 'all' ? undefined : String(v))}
        />
        <span style={{ marginLeft: 'auto' }}>
          <Button icon={<ReloadOutlined />} onClick={() => fetchData()}>刷新</Button>
        </span>
      </div>

      <div ref={tableWrapRef} className="sc-card" style={{ padding: '0 0 4px', flex: 1, minHeight: 0, overflow: 'hidden' }}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          size="small"
          scroll={{ x: 1450, y: scrollY }}
          onChange={(_pag: any, tableFilters: any, sorter: any) => {
            const sortField = sorter.field
            const sortOrder = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : undefined
            if (sortField !== sortInfo.sort_by || sortOrder !== sortInfo.sort_order) {
              setSortInfo({ sort_by: sortField, sort_order: sortOrder })
            }
            if (tableFilters.type?.length) setFilterType(tableFilters.type.join(','))
            else if (tableFilters.type !== undefined) setFilterType(undefined)
            if (tableFilters.severity?.length) setFilterSeverity(tableFilters.severity.join(','))
            else if (tableFilters.severity !== undefined) setFilterSeverity(undefined)
            if (tableFilters.status?.length) setFilterStatus(tableFilters.status.join(','))
            else if (tableFilters.status !== undefined) setFilterStatus(undefined)
          }}
          pagination={{
            ...pagination,
            showSizeChanger: true,
            showTotal: (total: number) => `共 ${total} 条`,
            onChange: (page, pageSize) => fetchData(page, pageSize),
            pageSizeOptions: ['20', '50', '100'],
          }}
        />
      </div>

      {/* 详情抽屉 */}
      <BdDrawer
        open={!!detail}
        onClose={() => setDetail(null)}
        width={720}
        title={detail?.title}
        code={detail ? `#${detail.id} · ${detail.page_path || ''}` : ''}
        tags={detail && (
          <>
            <span className={`sc-tag ${typeMeta[detail.type]?.cls || 'sc-tag-plain'}`}>{typeMeta[detail.type]?.label || detail.type}</span>
            <span className={`sc-tag ${severityMeta[detail.severity]?.cls || 'sc-tag-plain'}`}>{severityMeta[detail.severity]?.label || detail.severity}严重度</span>
            <span className={`sc-tag ${statusMeta[detail.status]?.cls || 'sc-tag-plain'}`}><span className="dot" />{statusMeta[detail.status]?.label || detail.status}</span>
          </>
        )}
      >
        {detail && (
          <>
            <div style={{ marginTop: 12 }}>
              <DrawerSection title="反馈内容">
                <div style={{ whiteSpace: 'pre-wrap', fontSize: 'calc(14px * var(--font-size-scale))', color: '#334155', lineHeight: 1.8 }}>
                  {detail.description || '（无描述）'}
                </div>
                {detail.attachments?.length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <div style={SEC_LABEL}>
                      附件（{detail.attachments.length}）
                    </div>
                    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
                      {detail.attachments.map((a: any) => (
                        <a key={a.id} href={a.url} target="_blank" rel="noreferrer" style={{ width: 92, textAlign: 'center' }}>
                          {a.mime?.startsWith('image/') ? (
                            <Image src={a.url} alt={a.name} width={92} height={60} style={{ objectFit: 'cover', borderRadius: 8 }} preview={{ mask: '预览' }} />
                          ) : (
                            <span style={{ width: 92, height: 60, borderRadius: 8, background: 'linear-gradient(135deg,#94a3b8,#64748b)', color: '#fff', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 10, fontWeight: 700 }}>
                              {(a.name || '').split('.').pop()?.toUpperCase() || 'FILE'}
                            </span>
                          )}
                          <div style={{ fontSize: 'calc(10.5px * var(--font-size-scale))', color: '#94a3b8', marginTop: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.name}</div>
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </DrawerSection>
            </div>

            <DrawerSection title="状态流转">
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                <span className={`sc-tag ${statusMeta[detail.status]?.cls || 'sc-tag-plain'}`}><span className="dot" />当前：{statusMeta[detail.status]?.label || detail.status}</span>
                {statusButtons(detail.status).map(b => (
                  <Button
                    key={b.text}
                    type={b.type}
                    danger={b.danger}
                    size="small"
                    loading={statusUpdating}
                    onClick={() => changeStatus(b.status, !!b.confirm)}
                  >
                    {b.text}
                  </Button>
                ))}
              </div>
            </DrawerSection>

            {detail.ai_status && detail.ai_status !== 'none' && (
              <DrawerSection title="AI 实现">
                <AiSection
                  detail={detail}
                  action={canHandle ? aiAction(detail) : null}
                  actionBoxRef={actionBoxRef}
                  filesExpanded={filesExpanded}
                  onToggleFiles={() => setFilesExpanded(v => !v)}
                  openGate={openGate}
                  onToggleGate={(key) => setOpenGate(prev => (prev === key ? null : key))}
                />
              </DrawerSection>
            )}

            {detail.reply && (
              <DrawerSection title="处理回复">
                <div style={{ display: 'flex', gap: 10 }}>
                  <Operator name={detail.replied_by} />
                  <div style={{ background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 8, padding: '8px 12px', flex: 1, minWidth: 0 }}>
                    <div className="sys-op-sub">{detail.replied_at ? dayjs(detail.replied_at).format('YYYY-MM-DD HH:mm') : ''}</div>
                    <div style={{ whiteSpace: 'pre-wrap', fontSize: 'calc(13.5px * var(--font-size-scale))', color: '#0f172a', marginTop: 4, lineHeight: 1.7 }}>
                      <Markdown>{detail.reply}</Markdown>
                    </div>
                  </div>
                </div>
              </DrawerSection>
            )}

            {canHandle && (
              <DrawerSection title="回复提交人（可同步状态）">
                <Form form={replyForm} layout="vertical">
                  <Form.Item name="reply" label="回复内容" extra="支持 Markdown 格式（粗体 / 列表 / 代码等）；留空则仅更新状态">
                    <Input.TextArea rows={4} maxLength={2000} showCount placeholder="请填写处理结论或回复内容…" />
                  </Form.Item>
                  <Form.Item name="status" label="同步设置状态">
                    <Select
                      allowClear
                      placeholder="保持当前状态不变"
                      options={Object.entries(statusMeta).map(([k, v]) => ({ label: v.label, value: k }))}
                    />
                  </Form.Item>
                  <Button type="primary" icon={<MessageOutlined />} onClick={handleReply} loading={replying}>回复并保存</Button>
                </Form>
              </DrawerSection>
            )}
          </>
        )}
      </BdDrawer>

      {/* 状态流转确认 */}
      <Modal
        title="更新处理状态"
        open={!!statusConfirm}
        onCancel={() => setStatusConfirm(null)}
        onOk={() => statusConfirm && doChangeStatus(statusConfirm.next)}
        confirmLoading={statusUpdating}
        okText="确认更新"
        cancelText="取消"
        width={480}
        rootClassName="sc-page"
      >
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 12 }}>
          <span className={`sc-tag ${STATUS_CLS(detail?.status)}`}>{STATUS_LBL(detail?.status)}</span>
          <span style={{ color: '#94a3b8' }}>→</span>
          <span className={`sc-tag ${STATUS_CLS(statusConfirm?.next)}`}>{STATUS_LBL(statusConfirm?.next)}</span>
        </div>
        <p style={{ fontSize: 'calc(13.5px * var(--font-size-scale))', color: '#475569', lineHeight: 1.8 }}>
          确认将 <b>#{detail?.id}</b> 更新为「{STATUS_LBL(statusConfirm?.next)}」？
          {statusConfirm?.next === 'closed'
            ? <>关闭后提交人将看到已关闭状态；如未完全解决可先回复并保持「处理中」。</>
            : '提交人可在详情中看到最新状态。'}
        </p>
      </Modal>

      {/* AI 重新排队确认 */}
      <Modal
        title="重新排队"
        open={!!aiConfirm}
        onCancel={() => setAiConfirm(null)}
        onOk={() => aiConfirm && handleAi('queue', aiConfirm.record)}
        confirmLoading={!!aiBusyId}
        okText="确认重新排队"
        cancelText="取消"
        width={480}
        rootClassName="sc-page"
      >
        <p style={{ fontSize: 'calc(13.5px * var(--font-size-scale))', color: '#475569', lineHeight: 1.8 }}>
          确认将 <b>#{aiConfirm?.record?.id}</b> 重新排入 AI 实现队列？当前正在执行的结果将被忽略（反馈回到「排队中」）。
        </p>
      </Modal>

      {/* 删除确认 */}
      <Modal
        title={<span style={{ color: '#dc2626' }}>删除反馈</span>}
        open={!!deleteTarget}
        onOk={handleDelete}
        confirmLoading={deleting}
        onCancel={() => setDeleteTarget(null)}
        okText="删除反馈"
        okButtonProps={{ danger: true }}
        cancelText="取消"
        width={480}
        rootClassName="sc-page"
      >
        <p style={{ fontSize: 'calc(13.5px * var(--font-size-scale))', color: '#475569', lineHeight: 1.8 }}>
          确认删除反馈 <b style={{ color: '#0f172a' }}>#{deleteTarget?.id} {deleteTarget?.title}</b>？
          <br />
          删除后提交人将无法再查看本条内容与回复记录（附件一并删除）。<b>已解决 / 处理中的反馈建议保留作复盘依据</b>。
        </p>
      </Modal>
    </div>
  )
}
