import { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Card, Col, Form, Input, InputNumber, Modal, Row, Spin, Switch,
  Table, Tabs, Tag, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { Column } from '@ant-design/charts'
import api from '../../../services/api'
import { useAuthStore } from '../../../store/auth'

interface ToolItem { name: string; display_name: string; description: string; disabled: boolean }
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
  query_data: '查数据', analyze_history: '析历史', general_chat: '闲聊', agent: '工具链', unknown: '未知',
}

function OverviewTab({ days }: { days: number }) {
  const [stats, setStats] = useState<StatsData | null>(null)
  const [loading, setLoading] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await api.get('/system/ai-assistant/stats', { params: { days } })
      setStats(res.data)
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }, [days])

  useEffect(() => { refresh() }, [refresh])
  if (loading || !stats) return <Spin/>
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Row gutter={16}>
        {[
          ['总对话', stats.total], ['成功率', stats.success_rate == null ? '-' : `${(stats.success_rate * 100).toFixed(1)}%`],
          ['平均耗时', `${(stats.avg_duration_ms / 1000).toFixed(1)}s`], ['累计 token', stats.total_tokens],
          ['活跃用户', stats.active_users],
        ].map(([label, value]) => (
          <Col key={String(label)} span={4}><Card size="small"><div style={{ opacity: 0.65 }}>{label}</div>
            <div style={{ fontSize: 22, fontWeight: 600 }}>{value}</div></Card></Col>
        ))}
      </Row>
      <Card size="small" title={`每日趋势（近 ${days} 天）`}>
        <Column height={220} data={stats.trend} xField="day" yField="total"
                 colorField="#1677ff" label={{ text: (d: any) => d.total }}/>
      </Card>
      <Card size="small" title="工具命中 Top10">
        <Column height={220} data={stats.top_tools} xField="tool" yField="hits"
                 colorField="#52c41a" label={{ text: (d: any) => d.hits }}/>
      </Card>
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
      const res: any = await api.get('/system/ai-assistant/runs', { params: { days, page, page_size: pageSize } })
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
    { title: '时间', dataIndex: 'created_at', width: 170, render: (v: string) => new Date(v).toLocaleString() },
    { title: '用户', dataIndex: 'user_id', width: 90 },
    { title: '意图', dataIndex: 'intent', width: 90, render: (v: string) => INTENT_LABELS[v] || v || '-' },
    { title: '提问', dataIndex: 'user_message', ellipsis: true },
    {
      title: '工具', dataIndex: 'tools_called', width: 200,
      render: (v: string[]) => v?.length ? v.map((t) => <Tag key={t} style={{ marginInlineEnd: 4 }}>{t}</Tag>) : '-',
    },
    { title: '轮数', dataIndex: 'tool_rounds', width: 60, align: 'center' },
    { title: 'token', dataIndex: 'total_tokens', width: 80, align: 'right' },
    { title: '耗时', dataIndex: 'duration_ms', width: 80, align: 'right', render: (v: number) => v != null ? `${(v / 1000).toFixed(1)}s` : '-' },
    {
      title: '状态', dataIndex: 'is_success', width: 80,
      render: (v: boolean, row) => v ? <Tag color="success">成功</Tag> :
        <Tag color="error" title={row.error_message || ''}>失败</Tag>,
    },
    { title: '', width: 70, render: (_v, row) => <a onClick={() => openDetail(row.trace_id)}>trace</a> },
  ]

  return (
    <>
      <Table rowKey="id" size="small" columns={columns} dataSource={rows} loading={loading}
             pagination={{ current: page, pageSize, total, showSizeChanger: true,
                           onChange: (p, s) => { setPage(p); setPageSize(s) } }}/>
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

function ConfigTab() {
  const [form] = Form.useForm()
  const [tools, setTools] = useState<ToolItem[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await api.get('/system/ai-assistant/config')
      const d = res.data
      form.setFieldsValue(d.config)
      setTools(d.tools)
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }, [form])

  useEffect(() => { refresh() }, [refresh])

  const save = async () => {
    const values = await form.validateFields()
    const disabled = tools.filter((t) => t.disabled).map((t) => t.name)
    setSaving(true)
    try {
      const res: any = await api.put('/system/ai-assistant/config', {
        config: { ...values, disabled_tools: disabled },
      })
      message.success(`已保存（版本 v${res.data.version}，即时生效）`)
      if (res.data.warning) message.warning(res.data.warning)
      refresh()
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Spin spinning={loading}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 960 }}>
        <Alert type="info" showIcon
               message={'系统提示词支持 {{TOOLS}} 占位符：构建对话时自动注入当前启用工具清单；两段提示词留空即恢复内置默认。'}/>
        <Card size="small" title="提示词">
          <Form form={form} layout="vertical">
            <Form.Item name="system_prompt" label="系统提示词">
              <Input.TextArea rows={12}/>
            </Form.Item>
            <Form.Item name="intent_prompt" label="意图识别提示词">
              <Input.TextArea rows={8}/>
            </Form.Item>
          </Form>
        </Card>
        <Card size="small" title="模型参数">
          <Form form={form} layout="vertical">
            <Row gutter={16}>
              <Col span={8}>
                <Form.Item name="model_name" label="模型名（留空用 .env 默认）">
                  <Input allowClear placeholder="如 glm-4.6 / gpt-4o-mini"/>
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="temperature" label="温度" initialValue={0.1}>
                  <InputNumber min={0} max={2} step={0.1} style={{ width: '100%' }}/>
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="max_tokens" label="最大输出 token" initialValue={4096}>
                  <InputNumber min={256} max={32768} step={256} style={{ width: '100%' }}/>
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="max_tool_rounds" label="工具循环轮数上限" initialValue={5}>
                  <InputNumber min={1} max={20} style={{ width: '100%' }}/>
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="tool_execute_timeout" label="工具执行超时（秒）" initialValue={30}>
                  <InputNumber min={5} max={300} style={{ width: '100%' }}/>
                </Form.Item>
              </Col>
            </Row>
          </Form>
        </Card>
        <Card size="small" title={`工具启停（${tools.filter((t) => !t.disabled).length}/${tools.length} 启用）`}>
          <Table rowKey="name" size="small" pagination={false}
                 dataSource={tools}
                 columns={[
                   { title: '工具', dataIndex: 'display_name', width: 220 },
                   { title: '说明', dataIndex: 'description', ellipsis: true },
                   {
                     title: '启用', dataIndex: 'disabled', width: 90,
                     render: (v: boolean, row: ToolItem) => (
                       <Switch checked={!v} onChange={(checked) => {
                         setTools((prev) => prev.map((t) =>
                           t.name === row.name ? { ...t, disabled: !checked } : t))
                       }}/>
                     ),
                   },
                 ]}/>
        </Card>
        <div>
          <Button type="primary" loading={saving} onClick={save}>保存配置</Button>
        </div>
      </div>
    </Spin>
  )
}

export default function AssistantManagement() {
  const hasPermission = useAuthStore((s: any) => s.hasPermission) as (r: string, a: string) => boolean
  const canConfig = hasPermission('ai.assistant_config', 'update')
  const [days] = useState(30)

  const tabs = [
    { key: 'overview', label: '概览', children: <OverviewTab days={days}/> },
    { key: 'runs', label: '运行记录', children: <RunsTab days={days}/> },
  ]
  if (canConfig) tabs.push({ key: 'config', label: '配置', children: <ConfigTab/> })

  return (
    <div style={{ padding: 16 }}>
      <Tabs defaultActiveKey="overview" items={tabs}/>
    </div>
  )
}
