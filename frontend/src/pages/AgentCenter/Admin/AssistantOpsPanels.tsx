import { useCallback, useEffect, useState } from 'react'
import {
  Drawer, List, Modal, Spin, Table, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  ClockCircleOutlined, LockOutlined, SearchOutlined,
} from '@ant-design/icons'
import api from '../../../services/api'
import { agentApi } from '../../../services/agent'

interface RunRow {
  id: number
  trace_id: string
  user_id: string | null
  user_message: string | null
  intent: string | null
  tools_called: string[] | null
  tool_rounds: number | null
  total_tokens: number | null
  duration_ms: number | null
  is_success: boolean
  error_message: string | null
  created_at: string
}

interface StatsData {
  total: number
  success: number
  success_rate: number | null
  avg_duration_ms: number
  total_tokens: number
  active_users: number
  trend: { day: string; total: number; ok: number }[]
  top_tools: { tool: string; hits: number }[]
}

interface CallRow {
  id: number
  callee?: { name?: string | null }
  capability: string
  instruction_summary?: string | null
  status: string
  result_summary?: string | null
  error?: string | null
  duration_ms?: number | null
  created_at?: string | null
}

const INTENT_LABELS: Record<string, string> = {
  query_data: '查数据',
  analyze_history: '分析历史',
  general_chat: '闲聊',
  agent: '工具链',
  unknown: '未知',
}

const CALL_STATUS_META: Record<string, { cls: string; text: string }> = {
  success: { cls: '', text: '成功' },
  failed: { cls: 'fail', text: '失败' },
  timeout: { cls: 'fail', text: '超时' },
  rejected: { cls: 'idle', text: '拒绝' },
  running: { cls: 'idle', text: '进行中' },
}

const CALL_STATUS_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' },
  { value: 'timeout', label: '超时' },
  { value: 'rejected', label: '拒绝' },
  { value: 'running', label: '进行中' },
]

function fmtNum(value: number): string {
  return value.toLocaleString('zh-CN')
}

function fmtCompact(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k`
  return String(value)
}

function fmtTime(value?: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  }) : '-'
}

function fmtDay(value: string): string {
  if (!value) return ''
  if (value.length >= 10) return value.slice(5, 10).replace('-', '/')
  return value
}

function StatusPill({ success, text }: { success: boolean; text: string }) {
  return <span className={`ac-pill ${success ? '' : 'fail'}`}>{text}</span>
}

export function AssistantOverviewPanel({
  days, onOpenRuns,
}: { days: number; onOpenRuns?: () => void }) {
  const [stats, setStats] = useState<StatsData | null>(null)
  const [runs, setRuns] = useState<RunRow[]>([])
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const [statsRes, runsRes]: any = await Promise.all([
        agentApi.assistantStats({ days }),
        agentApi.assistantRuns({ days, page: 1, page_size: 6 }).catch(() => ({ data: { items: [] } })),
      ])
      setStats(statsRes.data)
      setRuns(runsRes.data?.items || [])
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => { refresh() }, [refresh])

  if (loading && !stats) {
    return <div className="ac-surface"><div className="ac-empty"><Spin /></div></div>
  }
  if (!stats) {
    return <div className="ac-surface"><div className="ac-empty">暂无运营数据</div></div>
  }

  const failCount = Math.max(0, stats.total - stats.success)
  const successRate = stats.success_rate == null ? null : stats.success_rate * 100
  const avgSeconds = (stats.avg_duration_ms / 1000).toFixed(1)
  const trend = (stats.trend || []).slice(-14)
  const maxTotal = Math.max(...trend.map(item => item.total), 1)
  const avgDaily = trend.length
    ? Math.round(trend.reduce((sum, item) => sum + item.total, 0) / trend.length)
    : 0
  const topTools = (stats.top_tools || []).slice(0, 6)
  const maxHits = Math.max(...topTools.map(item => item.hits), 1)
  const donutPercent = successRate == null ? 0 : Math.max(0, Math.min(100, successRate))

  return (
    <>
      <div className="ac-metric-band">
        <div className="m"><span>总对话</span><b>{fmtNum(stats.total)}</b><small>近 {days} 天</small></div>
        <div className="m"><span>成功率</span><b>{successRate == null ? '-' : `${successRate.toFixed(1)}%`}</b><small>近 {days} 天</small></div>
        <div className="m"><span>平均耗时</span><b>{avgSeconds}s</b><small>近 {days} 天</small></div>
        <div className="m"><span>累计 Token</span><b>{fmtCompact(stats.total_tokens)}</b><small>近 {days} 天</small></div>
        <div className="m"><span>活跃用户</span><b>{fmtNum(stats.active_users)}</b><small>近 {days} 天</small></div>
      </div>

      <div className="ac-ops-row">
        <section className="ac-surface">
          <div className="ac-surface-head">
            <h2>每日对话趋势</h2>
            <span className="ac-hint">均值 {avgDaily} 次 / 天</span>
            <div className="ac-actions">
              <div className="ac-chart-legend">
                <span><i />成功</span>
                <span><i className="bad" />失败</span>
              </div>
            </div>
          </div>
          <div className="ac-chart-body">
            {trend.length === 0 ? (
              <div className="ac-empty">暂无趋势数据</div>
            ) : (
              <div className="ac-bar-chart" role="img" aria-label={`近 ${days} 天每日对话趋势`}>
                {trend.map((item, index) => {
                  const okHeight = Math.max(2, Math.round((item.ok / maxTotal) * 100))
                  const badHeight = Math.max(0, Math.round(((item.total - item.ok) / maxTotal) * 100))
                  return (
                    <div
                      key={item.day}
                      className="ac-bar"
                      title={`${fmtDay(item.day)} · ${item.total} 次 · 失败 ${item.total - item.ok}`}
                    >
                      <span className="ok" style={{ height: `${okHeight}%` }} />
                      {badHeight > 0 && <span className="bad" style={{ height: `${badHeight}%` }} />}
                      {index % 3 === 0 && <span className="lbl">{fmtDay(item.day)}</span>}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </section>

        <section className="ac-surface">
          <div className="ac-surface-head"><h2>质量</h2><span className="ac-hint">近 {days} 天</span></div>
          <div className="ac-quality-body">
            <div
              className="ac-donut"
              style={{ background: `conic-gradient(var(--ac-brand) 0 ${donutPercent}%, var(--ac-line-2) ${donutPercent}% 100%)` }}
            >
              <div className="val">
                {successRate == null ? '-' : `${successRate.toFixed(1)}%`}
                <small>SUCCESS</small>
              </div>
            </div>
            <div className="ac-quality-list">
              <div><span>成功对话</span><b>{fmtNum(stats.success)}</b></div>
              <div><span>失败 / 超时</span><b>{fmtNum(failCount)}</b></div>
              <div><span>平均耗时</span><b>{avgSeconds}s</b></div>
              <div><span>活跃用户</span><b>{fmtNum(stats.active_users)}</b></div>
            </div>
          </div>
        </section>
      </div>

      <div className="ac-ops-row">
        <section className="ac-surface">
          <div className="ac-surface-head"><h2>工具命中 Top 6</h2><span className="ac-hint">按调用次数</span></div>
          <div className="ac-tool-list">
            {topTools.length === 0 ? (
              <div className="ac-empty">暂无工具调用</div>
            ) : topTools.map(item => (
              <div className="ac-tool-row" key={item.tool}>
                <span className="ac-tool-name" title={item.tool}>{item.tool}</span>
                <span className="ac-tool-bar"><i style={{ width: `${Math.max(3, (item.hits / maxHits) * 100)}%` }} /></span>
                <span className="ac-tool-count">{item.hits}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="ac-surface">
          <div className="ac-surface-head">
            <h2>最近运行</h2>
            {onOpenRuns && (
              <div className="ac-actions">
                <button type="button" className="ac-link" onClick={onOpenRuns}>全部</button>
              </div>
            )}
          </div>
          {runs.length === 0 ? (
            <div className="ac-empty">暂无运行记录</div>
          ) : (
            <div className="ac-ops-table-wrap">
              <table className="ac-ops-table">
                <thead><tr><th>时间</th><th>用户</th><th>提问</th><th>状态</th></tr></thead>
                <tbody>
                  {runs.slice(0, 6).map(run => (
                    <tr key={run.id}>
                      <td className="mono">{fmtTime(run.created_at)}</td>
                      <td>{run.user_id || '-'}</td>
                      <td style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis' }} title={run.user_message || ''}>
                        {run.user_message || '-'}
                      </td>
                      <td>
                        <StatusPill success={run.is_success} text={run.is_success ? '成功' : '失败'} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </>
  )
}

export function AssistantRunsPanel({ days }: { days: number }) {
  const [rows, setRows] = useState<RunRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [detail, setDetail] = useState<{ trace_id: string; records: any[] } | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await agentApi.assistantRuns({ days, page, page_size: pageSize })
      setRows(res.data.items)
      setTotal(res.data.total)
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }, [days, page, pageSize])

  useEffect(() => { refresh() }, [refresh])

  const openDetail = async (traceId: string) => {
    try {
      const res: any = await api.get(`/assistant/logs/${traceId}`)
      const data = res.data
      if (!data) return message.error('未找到该 trace 的文件日志')
      setDetail({ trace_id: traceId, records: data.records })
    } catch (e: any) {
      message.error(String(e?.message || e))
    }
  }

  const columns: ColumnsType<RunRow> = [
    { title: '时间', dataIndex: 'created_at', width: 148, render: (value: string) => <span className="ac-hint" style={{ fontFamily: 'var(--ac-font-mono)' }}>{fmtTime(value)}</span> },
    { title: '用户', dataIndex: 'user_id', width: 86, ellipsis: true },
    {
      title: '意图', dataIndex: 'intent', width: 86,
      render: (value: string) => value ? <span className="ac-pill idle">{INTENT_LABELS[value] || value}</span> : '-',
    },
    { title: '提问', dataIndex: 'user_message', ellipsis: true },
    {
      title: '工具', dataIndex: 'tools_called', width: 200,
      render: (value: string[]) => value?.length
        ? value.map(tool => <span key={tool} className="ac-pill idle" style={{ marginInlineEnd: 4 }}>{tool}</span>)
        : <span className="ac-hint">-</span>,
    },
    { title: '轮数', dataIndex: 'tool_rounds', width: 58, align: 'right', render: (value: number) => value ?? '-' },
    { title: 'Token', dataIndex: 'total_tokens', width: 78, align: 'right', render: (value: number) => value != null ? fmtNum(value) : '-' },
    {
      title: '耗时', dataIndex: 'duration_ms', width: 72, align: 'right',
      render: (value: number) => value != null ? `${(value / 1000).toFixed(1)}s` : '-',
    },
    {
      title: '状态', dataIndex: 'is_success', width: 72,
      render: (value: boolean, row) => (
        <span title={row.error_message || ''}>
          <StatusPill success={value} text={value ? '成功' : '失败'} />
        </span>
      ),
    },
    {
      title: '', width: 60,
      render: (_value, row) => (
        <button type="button" className="ac-link" onClick={() => openDetail(row.trace_id)}>trace</button>
      ),
    },
  ]

  return (
    <>
      <section className="ac-surface">
        <div className="ac-surface-head">
          <h2>运行记录</h2>
          <span className="ac-hint">近 {days} 天 · 共 {fmtNum(total)} 条 · 点击 trace 查看完整调用链</span>
        </div>
        <Table
          rowKey="id"
          size="small"
          columns={columns}
          dataSource={rows}
          loading={loading}
          scroll={{ x: 1080 }}
          pagination={{
            current: page,
            pageSize,
            total,
            size: 'small',
            showSizeChanger: true,
            onChange: (nextPage, nextSize) => { setPage(nextPage); setPageSize(nextSize) },
          }}
        />
      </section>

      <Modal
        open={!!detail}
        title={`Trace 详情 ${detail?.trace_id || ''}`}
        footer={null}
        width={860}
        onCancel={() => setDetail(null)}
        destroyOnClose
        className="sc-page ai-center"
      >
        <div style={{ maxHeight: 480, overflow: 'auto', fontFamily: 'var(--ac-font-mono)', fontSize: 11 }}>
          {(detail?.records || []).map((record: any, index: number) => (
            <pre key={index} style={{ margin: 0, padding: 6, borderBottom: '1px solid #f1f5f9' }}>
              {JSON.stringify(record, null, 2)}
            </pre>
          ))}
        </div>
      </Modal>
    </>
  )
}

export function AgentCallsPanel() {
  const [rows, setRows] = useState<CallRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [keywordInput, setKeywordInput] = useState('')
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState('')
  const [loading, setLoading] = useState(false)
  const pageSize = 10

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await agentApi.adminCalls({
        keyword, status, page, page_size: pageSize,
      })
      setRows(res.data?.items || [])
      setTotal(res.data?.total || 0)
    } finally {
      setLoading(false)
    }
  }, [keyword, status, page])

  useEffect(() => { refresh() }, [refresh])

  const applyKeyword = () => {
    setKeyword(keywordInput.trim())
    setPage(1)
  }

  return (
    <section className="ac-surface">
      <div className="ac-surface-head">
        <h2>调用审计</h2>
        <span className="ac-hint">共 {fmtNum(total)} 条</span>
      </div>
      <div className="ac-table-toolbar">
        <label className="ac-search">
          <SearchOutlined />
          <input
            value={keywordInput}
            placeholder="能力 / 指令 / 结果关键字"
            onChange={event => setKeywordInput(event.target.value)}
            onKeyDown={event => { if (event.key === 'Enter') applyKeyword() }}
          />
        </label>
        <div className="ac-chips">
          {CALL_STATUS_OPTIONS.map(option => (
            <button
              key={option.value}
              type="button"
              className={`ac-chip ${status === option.value ? 'active' : ''}`}
              onClick={() => { setStatus(option.value); setPage(1) }}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      <Table
        rowKey="id"
        size="small"
        loading={loading}
        dataSource={rows}
        scroll={{ x: 980 }}
        pagination={{
          current: page,
          pageSize,
          total,
          size: 'small',
          showSizeChanger: false,
          onChange: setPage,
        }}
        columns={[
          { title: '成员', dataIndex: 'callee', width: 120, ellipsis: true, render: (value: CallRow['callee']) => value?.name || '-' },
          { title: '能力', dataIndex: 'capability', width: 150, ellipsis: true },
          { title: '指令', dataIndex: 'instruction_summary', width: 200, ellipsis: true, render: (value: string | null) => value || '-' },
          {
            title: '状态', dataIndex: 'status', width: 82,
            render: (value: string) => {
              const meta = CALL_STATUS_META[value] || { cls: 'idle', text: value }
              return <span className={`ac-pill ${meta.cls}`}>{meta.text}</span>
            },
          },
          {
            title: '结果 / 错误', dataIndex: 'result_summary', ellipsis: true,
            render: (value: string | null, row: CallRow) => value || row.error || '-',
          },
          { title: '耗时', dataIndex: 'duration_ms', width: 76, render: (value: number | null) => value ? `${value}ms` : '-' },
          { title: '时间', dataIndex: 'created_at', width: 140, render: fmtTime },
        ]}
      />
    </section>
  )
}

export function ConversationAuditPanel() {
  const [auditId, setAuditId] = useState('')
  const [auditReason, setAuditReason] = useState('')
  const [auditOpen, setAuditOpen] = useState(false)
  const [auditData, setAuditData] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const viewAudit = async () => {
    if (!auditId || !auditReason.trim()) {
      message.warning('会话 ID 与查看原因必填')
      return
    }
    setLoading(true)
    try {
      const res: any = await agentApi.adminConversation(Number(auditId), auditReason)
      setAuditData(res.data)
      setAuditOpen(true)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="ac-surface">
      <div className="ac-surface-head">
        <h2>会话审计</h2>
        <span className="ac-hint">管理员查看私人会话必须填写原因并留痕</span>
      </div>
      <div className="ac-audit-body">
        <div className="ac-audit-note">
          <LockOutlined style={{ marginTop: 2 }} />
          <div>会话内容属于员工个人数据。提交后会记录查看人、时间、会话 ID 与原因，出现在系统审计日志中，不可删除。</div>
        </div>
        <div className="ac-audit-form">
          <div className="ac-field" style={{ maxWidth: 190 }}>
            <label htmlFor="auditId">会话 ID</label>
            <input
              id="auditId"
              value={auditId}
              placeholder="例如 2048"
              onChange={event => setAuditId(event.target.value)}
            />
          </div>
          <div className="ac-field" style={{ flex: 1, minWidth: 220 }}>
            <label htmlFor="auditReason">查看原因</label>
            <input
              id="auditReason"
              value={auditReason}
              placeholder="例如：排查 10/28 订单写操作异常"
              onChange={event => setAuditReason(event.target.value)}
            />
          </div>
          <button
            type="button"
            className="ac-btn primary"
            style={{ alignSelf: 'flex-end' }}
            disabled={loading}
            onClick={viewAudit}
          >
            查看并留痕
          </button>
        </div>
        <div className="ac-audit-log">
          <h4>审计规则</h4>
          <div className="ac-audit-record">
            <ClockCircleOutlined style={{ marginTop: 2 }} />
            <span>每次查看必须填写原因，提交后写入系统审计日志；不会提供批量导出或删除入口。</span>
          </div>
        </div>
      </div>
      <Drawer
        title="会话审计"
        width={640}
        open={auditOpen}
        onClose={() => setAuditOpen(false)}
        className="sc-page ai-center"
      >
        {auditData && (
          <>
            <div className="ac-hint" style={{ marginBottom: 12 }}>
              原因：{auditData.reason}；查看人：{auditData.viewed_by}
            </div>
            <List
              dataSource={auditData.messages || []}
              renderItem={(item: any) => (
                <List.Item style={{ display: 'block' }}>
                  <div className="ac-hint">{item.role} · {fmtTime(item.created_at)}</div>
                  <div style={{ whiteSpace: 'pre-wrap' }}>{item.content}</div>
                </List.Item>
              )}
            />
          </>
        )}
      </Drawer>
    </section>
  )
}
