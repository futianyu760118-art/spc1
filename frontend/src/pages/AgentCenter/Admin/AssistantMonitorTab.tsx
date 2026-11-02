import { useCallback, useEffect, useState } from 'react'
import { Col, Modal, Row, Spin, Table, Tabs, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  CheckCircleOutlined, ClockCircleOutlined, MessageOutlined,
  ThunderboltOutlined, UserOutlined,
} from '@ant-design/icons'
import { Column } from '@ant-design/charts'
import api from '../../../services/api'
import { agentApi } from '../../../services/agent'

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

const INTENT_LABELS: Record<string, string> = {
  query_data: '查数据', analyze_history: '分析历史', general_chat: '闲聊', agent: '工具链', unknown: '未知',
}

function fmtNum(n: number): string {
  return n.toLocaleString('zh-CN')
}

function StatCard(props: {
  icon: React.ReactNode; label: string; value: string; unit?: string
  accent: string; accentBg: string; delta?: React.ReactNode
}) {
  return (
    <Col span={props.unit === '%' ? 4 : 5} key={props.label}>
      <div className="sc-card sc-stat-card" style={{ ['--accent' as any]: props.accent, ['--accent-bg' as any]: props.accentBg, height: '100%' }}>
        <div className="sc-stat-icon">{props.icon}</div>
        <div className="sc-stat-main" style={{ minWidth: 0 }}>
          <div className="sc-stat-label">{props.label}</div>
          <div className="sc-stat-value">{props.value}{props.unit && <small>{props.unit}</small>}</div>
          {props.delta}
        </div>
      </div>
    </Col>
  )
}

function OverviewTab({ days }: { days: number }) {
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
  if (loading || !stats) return <div className="sc-card" style={{ padding: 48, textAlign: 'center' }}><Spin /></div>

  const fail = stats.total - stats.success
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Row gutter={[12, 12]}>
        <StatCard icon={<MessageOutlined />} label="总对话" value={fmtNum(stats.total)} unit="次"
          accent="#5b5bd6" accentBg="#eef0fe" />
        <StatCard icon={<CheckCircleOutlined />} label="成功率"
          value={stats.success_rate == null ? '-' : (stats.success_rate * 100).toFixed(1)} unit="%"
          accent="#16a34a" accentBg="#f0fdf4" />
        <StatCard icon={<ClockCircleOutlined />} label="平均耗时"
          value={(stats.avg_duration_ms / 1000).toFixed(1)} unit="s"
          accent="#0284c7" accentBg="#f0f9ff" />
        <StatCard icon={<ThunderboltOutlined />} label="累计 token" value={fmtNum(stats.total_tokens)}
          accent="#8b5cf6" accentBg="#f5f3ff" />
        <StatCard icon={<UserOutlined />} label="活跃用户" value={fmtNum(stats.active_users)} unit="人"
          accent="#d97706" accentBg="#fffbeb" />
      </Row>

      <div className="sc-card" style={{ padding: '14px 16px' }}>
        <div className="sc-card-head" style={{ padding: '0 0 10px' }}>
          <h3>每日对话趋势</h3>
          <span className="sc-hint">近 {days} 天 · 成功 <b className="sc-mono">{fmtNum(stats.success)}</b> / 失败 <b className="sc-mono">{fmtNum(fail)}</b></span>
        </div>
        <Column height={220} data={stats.trend} xField="day" yField="total" colorField="#5b5bd6"
          axis={{ y: { labelFormatter: (v: number) => String(v) } }} />
      </div>

      <div className="sc-card" style={{ padding: '14px 16px' }}>
        <div className="sc-card-head" style={{ padding: '0 0 10px' }}>
          <h3>工具命中 Top10</h3>
          <span className="sc-hint">统计窗口同上</span>
        </div>
        <Column height={220} data={stats.top_tools} xField="tool" yField="hits" colorField="#0ea5e9" />
      </div>
    </div>
  )
}

function RunsTab({ days }: { days: number }) {
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
    { title: '时间', dataIndex: 'created_at', width: 150, render: (v: string) => <span className="sc-mono">{new Date(v).toLocaleString()}</span> },
    { title: '用户', dataIndex: 'user_id', width: 90, ellipsis: true },
    {
      title: '意图', dataIndex: 'intent', width: 86,
      render: (v: string) => v ? <span className="sc-tag sc-tag-plain">{INTENT_LABELS[v] || v}</span> : '-',
    },
    { title: '提问', dataIndex: 'user_message', ellipsis: true },
    {
      title: '工具', dataIndex: 'tools_called', width: 200,
      render: (v: string[]) => v?.length
        ? v.map((t) => <span key={t} className="sc-tag sc-tag-plain" style={{ marginInlineEnd: 4 }}>{t}</span>)
        : <span className="sc-sub">-</span>,
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
      render: (_v, row) => <div className="sc-row-actions"><a onClick={() => openDetail(row.trace_id)}>trace</a></div>,
    },
  ]

  return (
    <>
      <div className="sc-card" style={{ padding: '0 0 4px' }}>
        <div className="sc-card-head" style={{ padding: '12px 16px' }}>
          <h3>运行记录</h3>
          <span className="sc-hint">近 {days} 天 · 共 <b className="sc-mono">{fmtNum(total)}</b> 条 · 点击 trace 查看完整调用链</span>
        </div>
        <Table rowKey="id" size="small" columns={columns} dataSource={rows} loading={loading}
          pagination={{ current: page, pageSize, total, showSizeChanger: true,
                        onChange: (p, s) => { setPage(p); setPageSize(s) } }}/>
      </div>
      <Modal open={!!detail} title={`Trace 详情 ${detail?.trace_id || ''}`} footer={null}
             width={860} onCancel={() => setDetail(null)} destroyOnClose>
        <div style={{ maxHeight: 480, overflow: 'auto', fontFamily: 'monospace', fontSize: 12 }}>
          {(detail?.records || []).map((r: any, i: number) => (
            <pre key={i} style={{ margin: 0, padding: 6, borderBottom: '1px solid #f0f0f0' }}>
              {JSON.stringify(r, null, 2)}
            </pre>
          ))}
        </div>
      </Modal>
    </>
  )
}

export default function AssistantMonitorTab() {
  const days = 30
  return (
    <div className="sc-page">
      <Tabs defaultActiveKey="overview" items={[
        { key: 'overview', label: '概览', children: <OverviewTab days={days}/> },
        { key: 'runs', label: '运行记录', children: <RunsTab days={days}/> },
      ]}/>
    </div>
  )
}
