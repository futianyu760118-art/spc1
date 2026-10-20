import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Badge, Button, Col, Form, Input, InputNumber, Modal, Row, Select, Space,
  Spin, Table, Tabs, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import {
  ApiOutlined, ClockCircleOutlined, FieldTimeOutlined, PlayCircleOutlined,
  ReloadOutlined, SafetyOutlined, SendOutlined,
} from '@ant-design/icons'
import api from '../../../services/api'
import { useAuthStore } from '../../../store/auth'

type AgentKey = 'query' | 'reasoning' | 'order'

interface AgentSummary {
  key: AgentKey
  label: string
  scope: string
  capability: string
  online: boolean
  registered?: boolean
  agentId?: string
  configVersion?: number
  currentRunId?: string | null
  uptimeS?: number
  capabilities?: string[]
  reason?: string
  db_version: number
  config_pending_restart: boolean
}

interface AgentStatus {
  agent: AgentSummary
  db_version: number
  config_pending_restart: boolean
  recent_reasoning_tasks: {
    task_id: string; task_type: string | null; status: string; llm_called: number
    error_code: number | null; duration_ms: string | null; created_at: string
  }[]
}

interface ConfigDef {
  label: string
  description?: string
  value_type: 'string' | 'int' | 'float' | 'bool' | 'json'
}

interface AgentConfigResponse {
  version: number
  config: Record<string, unknown>
  defs: Record<string, ConfigDef>
}

const AGENT_TABS: { key: AgentKey; label: string }[] = [
  { key: 'query', label: '查询智能体' },
  { key: 'reasoning', label: '推理智能体' },
  { key: 'order', label: '订单智能体' },
]

const NUMBER_PROPS: Record<string, { min: number; max: number; step: number }> = {
  query_timeout_ms: { min: 1000, max: 120000, step: 1000 },
  reasoning_timeout_ms: { min: 10000, max: 600000, step: 10000 },
}

const STATUS_TAG: Record<string, { cls: string; label: string }> = {
  running: { cls: 'sc-tag-kit', label: '运行中' },
  succeeded: { cls: 'sc-tag-done', label: '成功' },
  failed: { cls: 'sc-tag-danger', label: '失败' },
  cancelled: { cls: 'sc-tag-plain', label: '已取消' },
  timeout: { cls: 'sc-tag-warn', label: '超时' },
}

function fmtUptime(s: number | undefined | null): string {
  if (s == null) return '-'
  if (s < 60) return `${s} 秒`
  if (s < 3600) return `${Math.floor(s / 60)} 分钟`
  return `${Math.floor(s / 3600)} 小时 ${Math.floor((s % 3600) / 60)} 分`
}

function StatusStat(props: {
  icon: React.ReactNode; label: string; value: React.ReactNode
  accent: string; accentBg: string; delta?: React.ReactNode
}) {
  return (
    <Col span={6}>
      <div className="sc-card sc-stat-card slim" style={{ ['--accent' as any]: props.accent, ['--accent-bg' as any]: props.accentBg, height: '100%' }}>
        <div className="sc-stat-icon">{props.icon}</div>
        <div className="sc-stat-main" style={{ minWidth: 0 }}>
          <div className="sc-stat-label">{props.label}</div>
          <div className="sc-stat-value" style={{ fontSize: 18 }}>{props.value}</div>
          {props.delta && <span className="sc-stat-delta flat">{props.delta}</span>}
        </div>
      </div>
    </Col>
  )
}

export default function ExecutionAgentManagement() {
  const hasPermission = useAuthStore((s: any) => s.hasPermission) as (r: string, a: string) => boolean
  const canManage = hasPermission('ai.execution_agent', 'update')
  const [form] = Form.useForm()
  const [activeKey, setActiveKey] = useState<AgentKey>('query')
  const [agents, setAgents] = useState<AgentSummary[]>([])
  const [status, setStatus] = useState<AgentStatus | null>(null)
  const [configDefs, setConfigDefs] = useState<Record<string, ConfigDef>>({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const pollRef = useRef<number | null>(null)
  const activeKeyRef = useRef<AgentKey>('query')

  const loadAgents = useCallback(async () => {
    try {
      const res: any = await api.get('/system/execution-agents')
      setAgents(res.data || [])
    } catch (e: any) {
      message.error(String(e?.message || e))
    }
  }, [])

  const refresh = useCallback(async (key: AgentKey = activeKey): Promise<AgentStatus | null> => {
    try {
      const res: any = await api.get(`/system/execution-agents/${key}/status`)
      const data = res.data as AgentStatus
      setStatus(data)
      return data
    } catch (e: any) {
      message.error(String(e?.message || e))
      return null
    }
  }, [activeKey])

  const loadCurrent = useCallback(async (key: AgentKey) => {
    setLoading(true)
    try {
      const [statusRes, configRes]: any[] = await Promise.all([
        api.get(`/system/execution-agents/${key}/status`),
        api.get(`/system/execution-agents/${key}/config`),
      ])
      setStatus(statusRes.data)
      const configData = configRes.data as AgentConfigResponse
      setConfigDefs(configData.defs || {})
      form.resetFields()
      form.setFieldsValue(configData.config)
      await loadAgents()
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }, [form, loadAgents])

  useEffect(() => {
    activeKeyRef.current = activeKey
    loadCurrent(activeKey)
    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current)
        pollRef.current = null
      }
      setRestarting(false)
    }
  }, [activeKey, loadCurrent])

  const save = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      const config = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v ?? '']))
      const res: any = await api.put(`/system/execution-agents/${activeKey}/config`, { config })
      message.success(`已保存 v${res.data.version}，agent 重启后生效`)
      await refresh(activeKey)
      await loadAgents()
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setSaving(false)
    }
  }

  const restart = () => {
    Modal.confirm({
      title: '远程重启执行面智能体？',
      content: '重启期间 Hub 派单会被忙拒/重连，约持续数秒。',
      okText: '重启', okButtonProps: { danger: true },
      onOk: async () => {
        const key = activeKey
        setRestarting(true)
        try {
          await api.post(`/system/execution-agents/${key}/restart`)
          message.success('重启指令已下发')
          let ticks = 0
          if (pollRef.current) window.clearInterval(pollRef.current)
          pollRef.current = window.setInterval(async () => {
            if (activeKeyRef.current !== key) {
              window.clearInterval(pollRef.current!)
              pollRef.current = null
              setRestarting(false)
              return
            }
            ticks += 1
            const latest = await refresh(key)
            if (latest?.agent.online || ticks > 20) {
              window.clearInterval(pollRef.current!)
              pollRef.current = null
              setRestarting(false)
              if (latest?.agent.online) message.success('agent 已恢复')
            }
          }, 3000)
        } catch (e: any) {
          setRestarting(false)
          message.error(String(e?.message || e))
        }
      },
    })
  }

  if (loading && !status) return <div className="sc-page" style={{ padding: 48, textAlign: 'center' }}><Spin /></div>
  const agent = status?.agent
  const pending = status?.config_pending_restart ?? agent?.config_pending_restart

  const taskColumns: ColumnsType<AgentStatus['recent_reasoning_tasks'][number]> = [
    { title: 'runId / task_id', dataIndex: 'task_id', width: 200, ellipsis: true, render: (v: string) => <span className="sc-mono">{v}</span> },
    { title: '类型', dataIndex: 'task_type', width: 180, ellipsis: true, render: (v: string | null) => v || <span className="sc-sub">-</span> },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: string) => {
        const t = STATUS_TAG[v]
        return t ? <span className={`sc-tag ${t.cls}`}>{t.label}</span> : <span className="sc-tag sc-tag-plain">{v}</span>
      },
    },
    {
      title: '真实 LLM', dataIndex: 'llm_called', width: 90,
      render: (v: number) => v ? <span className="sc-tag sc-tag-done">是</span> : <span className="sc-tag sc-tag-plain">否</span>,
    },
    {
      title: '耗时', dataIndex: 'duration_ms', width: 90, align: 'right',
      render: (v: string | null) => <span className="sc-mono">{v ? `${(Number(v) / 1000).toFixed(1)}s` : '-'}</span>,
    },
    { title: '时间', dataIndex: 'created_at', width: 160, render: (v: string) => <span className="sc-mono">{new Date(v).toLocaleString()}</span> },
  ]

  return (
    <div className="sc-page" style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Tabs
        activeKey={activeKey}
        onChange={(key) => setActiveKey(key as AgentKey)}
        items={AGENT_TABS.map((tab) => ({
          key: tab.key,
          label: (
            <span>
              {tab.label}
              <Badge
                status={agents.find((a) => a.key === tab.key)?.online ? 'success' : 'default'}
                style={{ marginLeft: 6 }}
              />
            </span>
          ),
        }))}
      />

      <div className="sc-card">
        <div className="sc-card-head" style={{ padding: '14px 16px 10px' }}>
          <h3>运行状态</h3>
          <span className="sc-hint">经 backend 代理访问 agent admin 面</span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
            <Button size="small" icon={<ReloadOutlined/>} onClick={() => refresh()}>刷新</Button>
            {canManage && (
              <Button size="small" danger icon={<SendOutlined/>} loading={restarting} onClick={restart}>
                远程重启
              </Button>
            )}
          </div>
        </div>
        <div style={{ padding: '0 16px 14px' }}>
          <Row gutter={[12, 12]}>
            <StatusStat
              icon={<ApiOutlined/>} label="连接状态"
              accent={agent?.online ? '#16a34a' : '#dc2626'}
              accentBg={agent?.online ? '#f0fdf4' : '#fef2f2'}
              value={agent?.online ? (agent.registered ? '在线' : '在线未注册') : '不可达'}
              delta={agent?.online ? (agent.agentId || '') : (agent?.reason || '')}
            />
            <StatusStat
              icon={<SafetyOutlined/>} label="配置版本"
              accent={pending ? '#d97706' : '#5b5bd6'}
              accentBg={pending ? '#fffbeb' : '#eef0fe'}
              value={<span className="sc-mono">v{agent?.configVersion ?? '-'}</span>}
              delta={pending
                ? <span style={{ color: '#d97706' }}>≠ 库内 v{status?.db_version}，需重启生效</span>
                : '与库内一致'}
            />
            <StatusStat
              icon={<FieldTimeOutlined/>} label="运行时长"
              accent="#0284c7" accentBg="#f0f9ff"
              value={fmtUptime(agent?.uptimeS)}
              delta={agent?.capabilities?.length ? `能力 ${agent.capabilities.length} 项` : ''}
            />
            <StatusStat
              icon={<PlayCircleOutlined/>} label="当前任务"
              accent="#8b5cf6" accentBg="#f5f3ff"
              value={agent?.currentRunId ? <span className="sc-mono" style={{ fontSize: 13 }}>{agent.currentRunId}</span> : '空闲'}
            />
          </Row>
        </div>
      </div>

      <div className="sc-card" style={{ padding: '0 16px 16px' }}>
        <div className="sc-card-head" style={{ padding: '14px 0 4px' }}>
          <h3>配置</h3>
          <span className="sc-hint">留空项沿用 agent 容器 .env；保存后重启生效</span>
        </div>
        <Form form={form} layout="vertical" style={{ maxWidth: 960 }}>
          <Row gutter={16}>
            {Object.entries(configDefs).map(([key, def]) => (
              <Col span={key.endsWith('_timeout_ms') ? 6 : 12} key={key}>
                <Form.Item name={key} label={def.label} tooltip={def.description}>
                  {key === 'log_level' ? (
                    <Select options={['debug', 'info', 'warn', 'error'].map((v) => ({ value: v, label: v }))}/>
                  ) : def.value_type === 'int' ? (
                    <InputNumber
                      min={NUMBER_PROPS[key]?.min ?? 0}
                      max={NUMBER_PROPS[key]?.max}
                      step={NUMBER_PROPS[key]?.step ?? 1}
                      style={{ width: '100%' }}
                    />
                  ) : (
                    <Input allowClear/>
                  )}
                </Form.Item>
              </Col>
            ))}
          </Row>
        </Form>
        {canManage && (
          <Space>
            <Button type="primary" loading={saving} onClick={save}>保存配置</Button>
            {pending && <Button danger icon={<ClockCircleOutlined/>} onClick={restart}>配置未生效，立即重启</Button>}
          </Space>
        )}
      </div>

      {activeKey === 'reasoning' && (
        <div className="sc-card" style={{ padding: '0 0 4px' }}>
          <div className="sc-card-head" style={{ padding: '12px 16px' }}>
            <h3>最近推理任务</h3>
            <span className="sc-hint">reasoning_task 审计 · 最近 10 条</span>
          </div>
          <Table rowKey="task_id" size="small" columns={taskColumns}
                 dataSource={status?.recent_reasoning_tasks || []} pagination={false}/>
        </div>
      )}
    </div>
  )
}
