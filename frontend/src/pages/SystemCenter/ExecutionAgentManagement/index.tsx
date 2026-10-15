import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Badge, Button, Card, Col, Form, Input, InputNumber, Modal, Row, Select, Space,
  Spin, Table, Tag, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { api } from '../../../services/api'
import { useAuthStore } from '../../../store/auth'

interface AgentStatus {
  agent: { online: boolean; registered?: boolean; currentRunId?: string | null
           configVersion?: number; uptimeS?: number; agentId?: string; reason?: string
           capabilities?: string[] }
  db_version: number
  config_pending_restart: boolean
  recent_reasoning_tasks: {
    task_id: string; task_type: string | null; status: string; llm_called: number
    error_code: number | null; duration_ms: string | null; created_at: string
  }[]
}

const STATUS_TAG: Record<string, { color: string; label: string }> = {
  running: { color: 'processing', label: '运行中' },
  succeeded: { color: 'success', label: '成功' },
  failed: { color: 'error', label: '失败' },
  cancelled: { color: 'default', label: '已取消' },
  timeout: { color: 'warning', label: '超时' },
}

export default function ExecutionAgentManagement() {
  const hasPermission = useAuthStore((s: any) => s.hasPermission) as (r: string, a: string) => boolean
  const canManage = hasPermission('ai.execution_agent', 'update')
  const [form] = Form.useForm()
  const [status, setStatus] = useState<AgentStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [restarting, setRestarting] = useState(false)
  const pollRef = useRef<number | null>(null)

  const refresh = useCallback(async (): Promise<AgentStatus | null> => {
    try {
      const res: any = await api.get('/system/execution-agent/status')
      const data = res.data as AgentStatus
      setStatus(data)
      return data
    } catch (e: any) {
      message.error(String(e?.message || e))
      return null
    }
  }, [])

  const loadConfig = useCallback(async () => {
    setLoading(true)
    try {
      await refresh()
      const res: any = await api.get('/system/execution-agent/config')
      form.setFieldsValue(res.data.config)
    } catch (e: any) {
      message.error(String(e?.message || e))
    } finally {
      setLoading(false)
    }
  }, [form, refresh])

  useEffect(() => { loadConfig() }, [loadConfig])
  useEffect(() => () => { if (pollRef.current) window.clearInterval(pollRef.current) }, [])

  const save = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      const res: any = await api.put('/system/execution-agent/config', {
        config: Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v ?? ''])),
      })
      message.success(`已保存 v${res.data.version}，agent 重启后生效`)
      refresh()
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
        setRestarting(true)
        try {
          await api.post('/system/execution-agent/restart')
          message.success('重启指令已下发')
          let ticks = 0
          if (pollRef.current) window.clearInterval(pollRef.current)
          pollRef.current = window.setInterval(async () => {
            ticks += 1
            const latest = await refresh()
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

  if (loading && !status) return <Spin style={{ padding: 48 }}/>
  const agent = status?.agent
  const pending = status?.config_pending_restart

  const taskColumns: ColumnsType<AgentStatus['recent_reasoning_tasks'][number]> = [
    { title: 'runId / task_id', dataIndex: 'task_id', width: 200, ellipsis: true },
    { title: '类型', dataIndex: 'task_type', width: 180, ellipsis: true },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: string) => <Tag color={STATUS_TAG[v]?.color || 'default'}>{STATUS_TAG[v]?.label || v}</Tag>,
    },
    { title: '真实 LLM', dataIndex: 'llm_called', width: 90, render: (v: number) => v ? <Tag color="green">是</Tag> : <Tag>否</Tag> },
    { title: '耗时', dataIndex: 'duration_ms', width: 90, align: 'right', render: (v: string | null) => v ? `${(Number(v) / 1000).toFixed(1)}s` : '-' },
    { title: '时间', dataIndex: 'created_at', width: 170, render: (v: string) => new Date(v).toLocaleString() },
  ]

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card size="small" title="状态">
        <Row gutter={16}>
          <Col span={4}>
            <Badge status={agent?.online ? 'success' : 'error'}
                   text={agent?.online ? (agent.registered ? '已注册在线' : '在线未注册') : '不可达'}/>
          </Col>
          <Col span={4}>AgentID：{agent?.agentId || '-'}</Col>
          <Col span={4}>当前 run：{agent?.currentRunId || '-'}</Col>
          <Col span={4}>uptime：{agent?.uptimeS != null ? `${Math.floor(agent.uptimeS / 60)} 分钟` : '-'}</Col>
          <Col span={4}>
            配置版本：
            <Tag color={pending ? 'orange' : 'green'}>
              v{agent?.configVersion ?? '-'}{pending ? ` ≠ v${status?.db_version}，需重启` : ''}
            </Tag>
          </Col>
          {canManage && (
            <Col span={2} offset={0}>
              <Button danger loading={restarting} onClick={restart}>远程重启</Button>
            </Col>
          )}
        </Row>
        {!agent?.online && <div style={{ marginTop: 8, opacity: 0.65, fontSize: 12 }}>{agent?.reason || ''}</div>}
      </Card>

      <Card size="small" title="配置（保存后 agent 重启生效；留空项沿用 .env）">
        <Form form={form} layout="vertical" style={{ maxWidth: 860 }}>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="agent_name" label="注册显示名"><Input allowClear placeholder="留空用 env"/></Form.Item></Col>
            <Col span={12}><Form.Item name="agent_id" label="Agent ID"><Input allowClear placeholder="留空用 env"/></Form.Item></Col>
            <Col span={12}><Form.Item name="ws_url" label="Hub WebSocket 地址"><Input allowClear placeholder="留空用 env"/></Form.Item></Col>
            <Col span={4}><Form.Item name="query_timeout_ms" label="查询超时(ms)"><InputNumber min={1000} max={120000} step={1000} style={{ width: '100%' }}/></Form.Item></Col>
            <Col span={4}><Form.Item name="reasoning_timeout_ms" label="推理超时(ms)"><InputNumber min={10000} max={600000} step={10000} style={{ width: '100%' }}/></Form.Item></Col>
            <Col span={4}>
              <Form.Item name="log_level" label="日志级别">
                <Select options={['debug', 'info', 'warn', 'error'].map((v) => ({ value: v, label: v }))}/>
              </Form.Item>
            </Col>
          </Row>
        </Form>
        {canManage && (
          <Space>
            <Button type="primary" loading={saving} onClick={save}>保存配置</Button>
            {pending && <Button danger onClick={restart}>配置未生效，立即重启</Button>}
          </Space>
        )}
      </Card>

      <Card size="small" title="最近推理任务（reasoning_task 审计）">
        <Table rowKey="task_id" size="small" columns={taskColumns}
               dataSource={status?.recent_reasoning_tasks || []} pagination={false}/>
      </Card>
    </div>
  )
}
