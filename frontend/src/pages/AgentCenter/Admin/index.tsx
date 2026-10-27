import React, { useCallback, useEffect, useState } from 'react'
import {
  Button, Card, Col, Drawer, Input, List, Modal, Row, Select, Space, Statistic, Table, Tabs, Tag, Typography, message,
} from 'antd'
import { useNavigate } from 'react-router-dom'
import { agentApi } from '../../../services/agent'
import { TaskAnalysisTag, TaskPriorityTag, TaskStatusTag } from '../../../components/Agent/TaskStatusTag'

const { Text } = Typography

export default function AgentAdmin() {
  const navigate = useNavigate()
  const [stats, setStats] = useState<any>(null)
  const [agents, setAgents] = useState<any[]>([])
  const [tasks, setTasks] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [agentKeyword, setAgentKeyword] = useState('')
  const [taskKeyword, setTaskKeyword] = useState('')
  const [taskStatus, setTaskStatus] = useState('')

  const [hierarchyAgent, setHierarchyAgent] = useState<any>(null)
  const [hierarchyAction, setHierarchyAction] = useState('reparent')
  const [newParentId, setNewParentId] = useState('')
  const [hierarchyReason, setHierarchyReason] = useState('')

  const [policyAgent, setPolicyAgent] = useState<any>(null)
  const [policyJson, setPolicyJson] = useState('{}')

  const [auditId, setAuditId] = useState('')
  const [auditReason, setAuditReason] = useState('')
  const [auditOpen, setAuditOpen] = useState(false)
  const [auditData, setAuditData] = useState<any>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, a, t]: any = await Promise.all([
        agentApi.adminStats(),
        agentApi.adminAgents({ keyword: agentKeyword, page_size: 100 }),
        agentApi.adminTasks({ keyword: taskKeyword, status: taskStatus, page_size: 50 }),
      ])
      setStats(s.data)
      setAgents(a.data?.items || [])
      setTasks(t.data?.items || [])
    } finally {
      setLoading(false)
    }
  }, [agentKeyword, taskKeyword, taskStatus])

  useEffect(() => { load() }, [load])

  const openHierarchy = (row: any) => {
    setHierarchyAgent(row)
    setHierarchyAction('reparent')
    setNewParentId(String(row.parent_agent_id || ''))
    setHierarchyReason('')
  }

  const submitHierarchy = async () => {
    if (!hierarchyAgent) return
    await agentApi.adminHierarchy(hierarchyAgent.id, {
      action: hierarchyAction,
      new_parent_id: hierarchyAction === 'reparent' && newParentId ? Number(newParentId) : undefined,
      reason: hierarchyReason,
    })
    message.success('层级已更新')
    setHierarchyAgent(null)
    load()
  }

  const openPolicy = (row: any) => {
    setPolicyAgent(row)
    setPolicyJson(JSON.stringify({
      granted: row.policy?.granted || [],
      disabled: row.policy?.disabled || [],
      data_scope: row.policy?.data_scope || { mode: 'org', org_ids: [], include_sub: true },
    }, null, 2))
  }

  const submitPolicy = async () => {
    if (!policyAgent) return
    try {
      const body = JSON.parse(policyJson)
      await agentApi.adminPolicy(policyAgent.id, body)
      message.success('配置已保存')
      setPolicyAgent(null)
      load()
    } catch (e: any) {
      message.error(e.message || 'JSON 格式错误')
    }
  }

  const loadAudit = async () => {
    if (!auditId || !auditReason.trim()) {
      message.warning('会话 ID 与查看原因必填')
      return
    }
    const res: any = await agentApi.adminConversation(Number(auditId), auditReason)
    setAuditData(res.data)
    setAuditOpen(true)
  }

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Row gutter={16}>
        <Col span={6}><Card><Statistic title="智能体总数" value={stats?.agents || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="启用智能体" value={stats?.active_agents || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="分析失败" value={stats?.analysis_failed || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="任务总数" value={Object.values(stats?.tasks_by_status || {}).reduce((a: number, b: any) => a + Number(b), 0)} /></Card></Col>
      </Row>

      <Card>
        <Tabs
          items={[
            {
              key: 'agents', label: '智能体与层级',
              children: (
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Input.Search
                    placeholder="用户名 / 显示名 / 智能体编号" allowClear style={{ width: 320 }}
                    onSearch={v => setAgentKeyword(v)}
                  />
                  <Table
                    size="small" rowKey="id" loading={loading} dataSource={agents} pagination={{ pageSize: 15 }}
                    columns={[
                      { title: '编号', dataIndex: 'agent_no', width: 110 },
                      { title: '名称', dataIndex: 'display_name' },
                      { title: '用户', dataIndex: 'username', width: 120 },
                      { title: '状态', dataIndex: 'status', width: 90, render: (v: string) => <Tag color={v === 'active' ? 'green' : 'default'}>{v}</Tag> },
                      { title: '上级', dataIndex: 'parent_agent_id', width: 90, render: (v: number | null) => v || '-' },
                      { title: '子成员', dataIndex: 'children_count', width: 90 },
                      {
                        title: '操作', width: 220,
                        render: (_: any, row: any) => (
                          <Space>
                            <Button type="link" onClick={() => openHierarchy(row)}>层级</Button>
                            <Button type="link" onClick={() => openPolicy(row)}>配置</Button>
                          </Space>
                        ),
                      },
                    ]}
                  />
                </Space>
              ),
            },
            {
              key: 'tasks', label: '任务审计',
              children: (
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Space>
                    <Input.Search placeholder="任务号 / 标题 / 业务单号" allowClear style={{ width: 280 }} onSearch={setTaskKeyword} />
                    <Select
                      value={taskStatus} style={{ width: 140 }} onChange={setTaskStatus}
                      options={[
                        { value: '', label: '全部状态' }, { value: 'pending', label: '待处理' },
                        { value: 'in_progress', label: '处理中' }, { value: 'blocked', label: '阻塞' },
                        { value: 'completed', label: '已完成' }, { value: 'cancelled', label: '已取消' },
                      ]}
                    />
                  </Space>
                  <Table
                    size="small" rowKey="id" loading={loading} dataSource={tasks} pagination={{ pageSize: 15 }}
                    onRow={record => ({
                      onClick: () => navigate(`/agents/tasks/${record.id}`),
                      style: { cursor: 'pointer' },
                    })}
                    columns={[
                      { title: '任务号', dataIndex: 'task_no', width: 110 },
                      { title: '标题', dataIndex: 'title' },
                      { title: '接收人', dataIndex: 'assignee_name', width: 110 },
                      { title: '截止', dataIndex: 'due_at', width: 160, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
                      { title: '优先级', dataIndex: 'priority', width: 90, render: (v: any) => <TaskPriorityTag priority={v} /> },
                      { title: '状态', dataIndex: 'status', width: 150, render: (v: any, row: any) => <TaskStatusTag status={v} isOverdue={row.is_overdue} /> },
                      { title: '分析', dataIndex: 'analysis_status', width: 100, render: (v: any) => <TaskAnalysisTag status={v} /> },
                    ]}
                  />
                </Space>
              ),
            },
            {
              key: 'audit', label: '会话审计',
              children: (
                <Space direction="vertical" style={{ width: '100%' }}>
                  <Text type="secondary">管理员查看私人会话必须填写原因并留痕。</Text>
                  <Space>
                    <Input placeholder="会话 ID" value={auditId} onChange={e => setAuditId(e.target.value)} style={{ width: 160 }} />
                    <Input placeholder="查看原因（必填）" value={auditReason} onChange={e => setAuditReason(e.target.value)} style={{ width: 300 }} />
                    <Button type="primary" onClick={loadAudit}>查看并留痕</Button>
                  </Space>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={`层级调整 · ${hierarchyAgent?.display_name || ''}`}
        open={!!hierarchyAgent} onCancel={() => setHierarchyAgent(null)} onOk={submitHierarchy} okText="保存"
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Select
            value={hierarchyAction} onChange={setHierarchyAction} style={{ width: '100%' }}
            options={[
              { value: 'reparent', label: '改挂到上级智能体' },
              { value: 'unbind', label: '解绑（无上级）' },
              { value: 'lock', label: '锁定（禁用）' },
              { value: 'unlock', label: '解锁（启用）' },
            ]}
          />
          {hierarchyAction === 'reparent' && (
            <Input placeholder="新上级智能体 ID" value={newParentId} onChange={e => setNewParentId(e.target.value)} />
          )}
          <Input.TextArea rows={3} placeholder="原因（审计用）" value={hierarchyReason} onChange={e => setHierarchyReason(e.target.value)} />
        </Space>
      </Modal>

      <Modal
        title={`能力/范围配置 · ${policyAgent?.display_name || ''}`}
        open={!!policyAgent} onCancel={() => setPolicyAgent(null)} onOk={submitPolicy}
        okText="保存" width={640}
      >
        <Input.TextArea
          rows={14} value={policyJson} onChange={e => setPolicyJson(e.target.value)}
          style={{ fontFamily: 'monospace', fontSize: 12 }}
        />
      </Modal>

      <Drawer title="会话审计" width={640} open={auditOpen} onClose={() => setAuditOpen(false)}>
        {auditData && (
          <>
            <Text type="secondary">原因：{auditData.reason}；查看人：{auditData.viewed_by}</Text>
            <List
              dataSource={auditData.messages || []}
              renderItem={(item: any) => (
                <List.Item style={{ display: 'block' }}>
                  <Text type="secondary" style={{ fontSize: 12 }}>{item.role} · {item.created_at}</Text>
                  <div style={{ whiteSpace: 'pre-wrap' }}>{item.content}</div>
                </List.Item>
              )}
            />
          </>
        )}
      </Drawer>
    </Space>
  )
}
