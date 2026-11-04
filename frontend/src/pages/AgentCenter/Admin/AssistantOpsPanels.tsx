import { useCallback, useEffect, useState } from 'react'
import {
  Button, Drawer, Input, List, Modal, Select, Spin, Table, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckCircleOutlined, ClockCircleOutlined, MessageOutlined,
  ThunderboltOutlined, UserOutlined,
} from '@ant-design/icons'
import { Column } from '@ant-design/charts'
import api from '../../../services/api'
import { agentApi } from '../../../services/agent'
import StatCard from '../../../components/Agent/StatCard'

interface RunRow {
  id: number; trace_id: string; user_id: string | null; user_message: string | null
  intent: string | null; tools_called: string[] | null; tool_rounds: number | null
  total_tokens: number | null; duration_ms: number | null; is_success: boolean
  error_message: string | null; created_at: string
}

interface StatsData {
  total: number; success: number; success_rate: number | null; avg_duration_ms: number
  total_tokens: number; active_users: number
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
  query_data: '查数据', analyze_history: '分析历史', general_chat: '闲聊', agent: '工具链', unknown: '未知',
}

const CALL_STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' },
  { value: 'timeout', label: '超时' },
  { value: 'rejected', label: '拒绝' },
  { value: 'running', label: '进行中' },
]

const CALL_STATUS_META: Record<string, { cls: string; text: string }> = {
  success: { cls: 'sc-tag-done', text: '成功' },
  failed: { cls: 'sc-tag-danger', text: '失败' },
  timeout: { cls: 'sc-tag-warn', text: '超时' },
  rejected: { cls: 'sc-tag-plain', text: '拒绝' },
  running: { cls: 'sc-tag-kit', text: '进行中' },
}

function fmtNum(n: number): string {
  return n.toLocaleString('zh-CN')
}

function fmtTime(value?: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN') : '-'
}

export function AssistantOverviewPanel({ days }: { days: number }) {
  const [stats, setStats] = useState<StatsData | null>(null)
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await agentApi.assistantStats({ days })
      setStats(res.data)
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => { refresh() }, [refresh])

  if (loading || !stats) {
    return <div className="ai-card"><div className="ai-empty"><Spin /></div></div>
  }

  const fail = stats.total - stats.success
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="ai-stat-grid cols-5">
        <StatCard icon={<MessageOutlined />} label="总对话" value={fmtNum(stats.total)} unit="次" />
        <StatCard icon={<CheckCircleOutlined />} label="成功率" value={stats.success_rate == null ? '-' : (stats.success_rate * 100).toFixed(1)} unit="%" accent="#16a34a" accentBg="#f0fdf4" />
        <StatCard icon={<ClockCircleOutlined />} label="平均耗时" value={(stats.avg_duration_ms / 1000).toFixed(1)} unit="s" accent="#0284c7" accentBg="#f0f9ff" />
        <StatCard icon={<ThunderboltOutlined />} label="累计 token" value={fmtNum(stats.total_tokens)} accent="#8b5cf6" accentBg="#f5f3ff" />
        <StatCard icon={<UserOutlined />} label="活跃用户" value={fmtNum(stats.active_users)} unit="人" accent="#d97706" accentBg="#fffbeb" />
      </div>

      <div className="ai-card ai-chart-card">
        <div className="ai-card-head">
          <h3>每日对话趋势</h3>
          <span className="ai-hint">近 {days} 天 · 成功 {fmtNum(stats.success)} / 失败 {fmtNum(fail)}</span>
        </div>
        <Column height={220} data={stats.trend} xField="day" yField="total" colorField="#5b5bd6"
          axis={{ y: { labelFormatter: (v: number) => String(v) } }} />
      </div>

      <div className="ai-card ai-chart-card">
        <div className="ai-card-head">
          <h3>工具命中 Top10</h3>
          <span className="ai-hint">统计窗口同上</span>
        </div>
        <Column height={220} data={stats.top_tools} xField="tool" yField="hits" colorField="#0ea5e9" />
      </div>
    </div>
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
    { title: '时间', dataIndex: 'created_at', width: 150, render: (v: string) => <span className="sc-mono">{fmtTime(v)}</span> },
    { title: '用户', dataIndex: 'user_id', width: 90, ellipsis: true },
    {
      title: '意图', dataIndex: 'intent', width: 86,
      render: (v: string) => v ? <span className="sc-tag sc-tag-plain">{INTENT_LABELS[v] || v}</span> : '-',
    },
    { title: '提问', dataIndex: 'user_message', ellipsis: true },
    {
      title: '工具', dataIndex: 'tools_called', width: 200,
      render: (v: string[]) => v?.length
        ? v.map(t => <span key={t} className="sc-tag sc-tag-plain" style={{ marginInlineEnd: 4 }}>{t}</span>)
        : <span className="ai-muted">-</span>,
    },
    { title: '轮数', dataIndex: 'tool_rounds', width: 60, align: 'right', render: (v: number) => <span className="sc-mono">{v ?? '-'}</span> },
    { title: 'token', dataIndex: 'total_tokens', width: 80, align: 'right', render: (v: number) => <span className="sc-mono">{v != null ? fmtNum(v) : '-'}</span> },
    {
      title: '耗时', dataIndex: 'duration_ms', width: 76, align: 'right',
      render: (v: number) => <span className="sc-mono">{v != null ? `${(v / 1000).toFixed(1)}s` : '-'}</span>,
    },
    {
      title: '状态', dataIndex: 'is_success', width: 76,
      render: (v: boolean, row) => v
        ? <span className="sc-tag sc-tag-done">成功</span>
        : <span className="sc-tag sc-tag-danger" title={row.error_message || ''}>失败</span>,
    },
    {
      title: '', width: 64,
      render: (_v, row) => <Button type="link" size="small" onClick={() => openDetail(row.trace_id)}>trace</Button>,
    },
  ]

  return (
    <>
      <div className="ai-card">
        <div className="ai-card-head">
          <h3>运行记录</h3>
          <span className="ai-hint">近 {days} 天 · 共 {fmtNum(total)} 条 · 点击 trace 查看完整调用链</span>
        </div>
        <Table rowKey="id" size="small" columns={columns} dataSource={rows} loading={loading}
          scroll={{ x: 1100 }}
          pagination={{ current: page, pageSize, total, showSizeChanger: true,
                        onChange: (p, s) => { setPage(p); setPageSize(s) } }}/>
      </div>
      <Modal open={!!detail} title={`Trace 详情 ${detail?.trace_id || ''}`} footer={null}
             width={860} onCancel={() => setDetail(null)} destroyOnClose>
        <div style={{ maxHeight: 480, overflow: 'auto', fontFamily: 'monospace', fontSize: 12 }}>
          {(detail?.records || []).map((record: any, index: number) => (
            <pre key={index} style={{ margin: 0, padding: 6, borderBottom: '1px solid #f0f0f0' }}>
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

  return (
    <div className="ai-card">
      <div className="ai-toolbar">
        <Input.Search
          placeholder="能力 / 指令 / 结果关键字"
          allowClear
          style={{ width: 280 }}
          onSearch={value => { setKeyword(value); setPage(1) }}
        />
        <Select
          value={status}
          style={{ width: 140 }}
          options={CALL_STATUS_OPTIONS}
          onChange={value => { setStatus(value); setPage(1) }}
        />
        <span className="ai-toolbar-meta">共 {total} 条</span>
      </div>
      <Table
        size="small" rowKey="id" loading={loading} dataSource={rows}
        scroll={{ x: 900 }}
        pagination={{
          current: page, pageSize, total, size: 'small', showSizeChanger: false,
          onChange: setPage,
        }}
        columns={[
          { title: '成员', dataIndex: 'callee', width: 130, ellipsis: true, render: (v: CallRow['callee']) => v?.name || '-' },
          { title: '能力', dataIndex: 'capability', width: 150, ellipsis: true },
          { title: '指令', dataIndex: 'instruction_summary', width: 200, ellipsis: true, render: (v: string | null) => v || '-' },
          {
            title: '状态', dataIndex: 'status', width: 82,
            render: (value: string) => {
              const meta = CALL_STATUS_META[value] || { cls: 'sc-tag-plain', text: value }
              return <span className={`sc-tag ${meta.cls}`}>{meta.text}</span>
            },
          },
          {
            title: '结果 / 错误', dataIndex: 'result_summary', ellipsis: true,
            render: (v: string | null, row: CallRow) => v || row.error || '-',
          },
          { title: '耗时', dataIndex: 'duration_ms', width: 76, render: (v: number | null) => v ? `${v}ms` : '-' },
          { title: '时间', dataIndex: 'created_at', width: 140, render: fmtTime },
        ]}
      />
    </div>
  )
}

export function ConversationAuditPanel() {
  const [auditId, setAuditId] = useState('')
  const [auditReason, setAuditReason] = useState('')
  const [auditOpen, setAuditOpen] = useState(false)
  const [auditData, setAuditData] = useState<any>(null)

  const viewAudit = async () => {
    if (!auditId || !auditReason.trim()) {
      message.warning('会话 ID 与查看原因必填')
      return
    }
    const res: any = await agentApi.adminConversation(Number(auditId), auditReason)
    setAuditData(res.data)
    setAuditOpen(true)
  }

  return (
    <div className="ai-card">
      <div className="ai-card-head">
        <h3>会话审计</h3>
        <span className="ai-hint">管理员查看私人会话必须填写原因并留痕</span>
      </div>
      <div className="ai-card-body">
        <div className="ai-toolbar" style={{ padding: 0, borderBottom: 'none' }}>
          <Input
            placeholder="会话 ID"
            value={auditId}
            onChange={event => setAuditId(event.target.value)}
            style={{ width: 180 }}
          />
          <Input
            placeholder="查看原因（必填）"
            value={auditReason}
            onChange={event => setAuditReason(event.target.value)}
            style={{ width: 320 }}
          />
          <Button type="primary" onClick={viewAudit}>查看并留痕</Button>
        </div>
      </div>
      <Drawer
        title="会话审计"
        width={640}
        open={auditOpen}
        onClose={() => setAuditOpen(false)}
        className="sc-page"
      >
        {auditData && (
          <>
            <div className="ai-muted" style={{ marginBottom: 12 }}>
              原因：{auditData.reason}；查看人：{auditData.viewed_by}
            </div>
            <List
              dataSource={auditData.messages || []}
              renderItem={(item: any) => (
                <List.Item style={{ display: 'block' }}>
                  <div className="ai-muted">{item.role} · {fmtTime(item.created_at)}</div>
                  <div style={{ whiteSpace: 'pre-wrap' }}>{item.content}</div>
                </List.Item>
              )}
            />
          </>
        )}
      </Drawer>
    </div>
  )
}
