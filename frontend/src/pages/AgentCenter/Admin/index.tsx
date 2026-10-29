import React, { useCallback, useEffect, useState } from 'react'
import {
  Button, Card, Col, Drawer, Form, Input, List, Modal, Radio, Row, Select, Space, Statistic, Switch, Table, Tabs, Tag, Typography, message,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { userApi } from '../../../services/api'
import { agentApi, AgentCapability } from '../../../services/agent'
import { CapabilityTags } from '../../../components/Agent/CapabilityTags'

const { Text } = Typography
const PAGE_SIZE = 6

interface RoleOption {
  id: number
  role_name: string
}

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'active', label: '启用' },
  { value: 'disabled', label: '停用' },
]

const CALL_STATUS_OPTIONS = [
  { value: '', label: '全部状态' }, { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' }, { value: 'timeout', label: '超时' },
  { value: 'rejected', label: '拒绝' }, { value: 'running', label: '进行中' },
]

export default function AgentAdmin() {
  const [form] = Form.useForm()
  const [stats, setStats] = useState<any>(null)
  const [agents, setAgents] = useState<any[]>([])
  const [agentTotal, setAgentTotal] = useState(0)
  const [agentPage, setAgentPage] = useState(1)
  const [agentKeyword, setAgentKeyword] = useState('')
  const [agentStatus, setAgentStatus] = useState('')
  const [loadingAgents, setLoadingAgents] = useState(false)

  const [calls, setCalls] = useState<any[]>([])
  const [callTotal, setCallTotal] = useState(0)
  const [callPage, setCallPage] = useState(1)
  const [callKeyword, setCallKeyword] = useState('')
  const [callStatus, setCallStatus] = useState('')
  const [loadingCalls, setLoadingCalls] = useState(false)

  const [capabilities, setCapabilities] = useState<AgentCapability[]>([])
  const [roles, setRoles] = useState<RoleOption[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const [editingAgent, setEditingAgent] = useState<any>(null)
  const [saving, setSaving] = useState(false)
  const scopeType = Form.useWatch('scope_type', form)

  const [auditId, setAuditId] = useState('')
  const [auditReason, setAuditReason] = useState('')
  const [auditOpen, setAuditOpen] = useState(false)
  const [auditData, setAuditData] = useState<any>(null)

  const loadStats = useCallback(async () => {
    const res: any = await agentApi.adminStats()
    setStats(res.data)
  }, [])

  const loadAgents = useCallback(async () => {
    setLoadingAgents(true)
    try {
      const res: any = await agentApi.adminAgents({
        keyword: agentKeyword, status: agentStatus, page: agentPage, page_size: PAGE_SIZE,
      })
      setAgents(res.data?.items || [])
      setAgentTotal(res.data?.total || 0)
    } finally {
      setLoadingAgents(false)
    }
  }, [agentKeyword, agentStatus, agentPage])

  const loadCalls = useCallback(async () => {
    setLoadingCalls(true)
    try {
      const res: any = await agentApi.adminCalls({
        keyword: callKeyword, status: callStatus, page: callPage, page_size: PAGE_SIZE,
      })
      setCalls(res.data?.items || [])
      setCallTotal(res.data?.total || 0)
    } finally {
      setLoadingCalls(false)
    }
  }, [callKeyword, callStatus, callPage])

  useEffect(() => { loadStats() }, [loadStats])
  useEffect(() => { loadAgents() }, [loadAgents])
  useEffect(() => { loadCalls() }, [loadCalls])

  const loadFormOptions = async () => {
    const [capRes, roleRes]: any = await Promise.all([
      agentApi.capabilities(),
      userApi.roles({ page_size: 500 }).catch(() => {
        message.warning('角色列表加载失败，无法按角色开放')
        return { data: { items: [] } }
      }),
    ])
    setCapabilities((capRes.data?.items || []).filter((cap: AgentCapability) => cap.grantable))
    setRoles(roleRes.data?.items || [])
  }

  const openCreate = () => {
    setEditingAgent(null)
    form.resetFields()
    form.setFieldsValue({ scope_type: 'all', status: true })
    setModalOpen(true)
    loadFormOptions()
  }

  const openEdit = (row: any) => {
    setEditingAgent(row)
    form.resetFields()
    form.setFieldsValue({
      name: row.name,
      capabilities: (row.capabilities || []).map((cap: { code: string }) => cap.code),
      scope_type: row.scope_type || 'all',
      scope_role_ids: row.scope_role_ids || [],
      description: row.description || '',
      status: row.status === 'active',
    })
    setModalOpen(true)
    loadFormOptions()
  }

  const submitAgent = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      const payload = {
        name: values.name.trim(),
        capabilities: values.capabilities,
        scope_type: values.scope_type,
        scope_role_ids: values.scope_type === 'roles' ? values.scope_role_ids : null,
        description: values.description || null,
        status: values.status ? 'active' : 'disabled',
      }
      if (editingAgent) {
        await agentApi.updateAgent(editingAgent.id, payload)
        message.success('已保存')
      } else {
        await agentApi.createAgent(payload)
        message.success('已创建')
      }
      setModalOpen(false)
      await Promise.all([loadAgents(), loadStats()])
    } finally {
      setSaving(false)
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

  const callTotalAll = Object.values(stats?.calls_by_status || {}).reduce((a: number, b: any) => a + Number(b), 0)
  const callFailed = ['failed', 'timeout', 'rejected'].reduce(
    (sum, key) => sum + Number((stats?.calls_by_status || {})[key] || 0), 0,
  )

  return (
    <div className="agent-center-page">
      <Row gutter={12}>
        <Col span={6}><Card styles={{ body: { padding: '10px 14px' } }}><Statistic title="智能体总数" value={stats?.agents || 0} /></Card></Col>
        <Col span={6}><Card styles={{ body: { padding: '10px 14px' } }}><Statistic title="启用智能体" value={stats?.active_agents || 0} /></Card></Col>
        <Col span={6}><Card styles={{ body: { padding: '10px 14px' } }}><Statistic title="能力调用" value={callTotalAll} /></Card></Col>
        <Col span={6}><Card styles={{ body: { padding: '10px 14px' } }}><Statistic title="失败/超时/拒绝" value={callFailed} valueStyle={{ color: callFailed ? '#dc2626' : undefined }} /></Card></Col>
      </Row>

      <Card className="ac-fill ac-admin-main">
        <Tabs
          className="ac-tabs"
          items={[
            {
              key: 'agents', label: '智能体目录',
              children: (
                <Space direction="vertical" style={{ width: '100%', height: '100%' }} size={8}>
                  <Space wrap>
                    <Input.Search
                      placeholder="名称 / 编号" allowClear style={{ width: 300 }}
                      onSearch={v => { setAgentKeyword(v); setAgentPage(1) }}
                    />
                    <Select
                      value={agentStatus} style={{ width: 130 }} onChange={v => { setAgentStatus(v); setAgentPage(1) }}
                      options={STATUS_OPTIONS}
                    />
                    <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建智能体</Button>
                  </Space>
                  <Table
                    size="small" rowKey="id" loading={loadingAgents} dataSource={agents}
                    tableLayout="fixed"
                    pagination={{
                      current: agentPage, pageSize: PAGE_SIZE, total: agentTotal,
                      size: 'small', showSizeChanger: false,
                      onChange: page => setAgentPage(page),
                    }}
                    columns={[
                      { title: '编号', dataIndex: 'agent_no', width: 130, ellipsis: true },
                      { title: '名称', dataIndex: 'name', width: 150, ellipsis: true },
                      {
                        title: '能力', dataIndex: 'capabilities', width: 190,
                        render: (value: any) => <CapabilityTags items={value} max={2} />,
                      },
                      {
                        title: '开放范围', dataIndex: 'scope_type', width: 110,
                        render: (v: string, row: any) => v === 'roles'
                          ? <Tag color="blue">指定角色 × {row.scope_role_ids?.length || 0}</Tag>
                          : <Tag color="green">所有人</Tag>,
                      },
                      { title: '状态', dataIndex: 'status', width: 76, render: (v: string) => <Tag color={v === 'active' ? 'green' : 'default'}>{v === 'active' ? '启用' : '停用'}</Tag> },
                      { title: '勾选团队数', dataIndex: 'teams_count', width: 96 },
                      { title: '说明', dataIndex: 'description', ellipsis: true, render: (v: string | null) => v || '-' },
                      {
                        title: '操作', width: 70,
                        render: (_: any, row: any) => (
                          <Button type="link" size="small" onClick={() => openEdit(row)}>编辑</Button>
                        ),
                      },
                    ]}
                  />
                </Space>
              ),
            },
            {
              key: 'calls', label: '调用审计',
              children: (
                <Space direction="vertical" style={{ width: '100%', height: '100%' }} size={8}>
                  <Space wrap>
                    <Input.Search placeholder="能力 / 指令 / 结果关键字" allowClear style={{ width: 280 }} onSearch={v => { setCallKeyword(v); setCallPage(1) }} />
                    <Select
                      value={callStatus} style={{ width: 140 }} onChange={v => { setCallStatus(v); setCallPage(1) }}
                      options={CALL_STATUS_OPTIONS}
                    />
                  </Space>
                  <Table
                    size="small" rowKey="id" loading={loadingCalls} dataSource={calls}
                    tableLayout="fixed"
                    pagination={{
                      current: callPage, pageSize: PAGE_SIZE, total: callTotal,
                      size: 'small', showSizeChanger: false,
                      onChange: page => setCallPage(page),
                    }}
                    columns={[
                      { title: '成员', dataIndex: 'callee', width: 130, ellipsis: true, render: (v: any) => v?.name || '-' },
                      { title: '能力', dataIndex: 'capability', width: 150, ellipsis: true },
                      { title: '指令', dataIndex: 'instruction_summary', width: 200, ellipsis: true, render: (v: string | null) => v || '-' },
                      { title: '状态', dataIndex: 'status', width: 76, render: (v: string) => <Tag>{v}</Tag> },
                      {
                        title: '结果 / 错误', dataIndex: 'result_summary', ellipsis: true,
                        render: (v: string | null, row: any) => v || row.error || '-',
                      },
                      { title: '耗时', dataIndex: 'duration_ms', width: 76, render: (v: number | null) => v ? `${v}ms` : '-' },
                      { title: '时间', dataIndex: 'created_at', width: 140, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
                    ]}
                  />
                </Space>
              ),
            },
            {
              key: 'audit', label: '会话审计',
              children: (
                <Space direction="vertical" style={{ width: '100%' }} size={8}>
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
        title={editingAgent ? `编辑智能体 · ${editingAgent.name}` : '新建智能体'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={submitAgent}
        confirmLoading={saving}
        okText="保存"
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="名称" rules={[{ required: true, message: '请输入智能体名称' }]}>
            <Input maxLength={64} placeholder="全局唯一，如：订单查询员" />
          </Form.Item>
          <Form.Item name="capabilities" label="能力" rules={[{ required: true, message: '请至少选择一个能力' }]}>
            <Select
              mode="multiple"
              placeholder="选择该智能体具备的能力（可多选）"
              options={capabilities.map(cap => ({
                value: cap.code,
                label: `${cap.name}（${cap.code}）`,
              }))}
            />
          </Form.Item>
          <Form.Item name="scope_type" label="开放范围" rules={[{ required: true }]}>
            <Radio.Group
              options={[
                { value: 'all', label: '所有人可勾选' },
                { value: 'roles', label: '指定角色' },
              ]}
            />
          </Form.Item>
          {scopeType === 'roles' && (
            <Form.Item
              name="scope_role_ids" label="开放角色"
              rules={[{ required: true, message: '请选择至少一个角色' }]}
            >
              <Select
                mode="multiple"
                placeholder="选择可勾选该智能体的角色"
                options={roles.map(role => ({ value: role.id, label: role.role_name }))}
              />
            </Form.Item>
          )}
          <Form.Item name="description" label="说明">
            <Input.TextArea rows={3} maxLength={500} placeholder="展示给用户，并帮助助手选择合适成员" />
          </Form.Item>
          <Form.Item name="status" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer title="会话审计" width={640} open={auditOpen} onClose={() => setAuditOpen(false)}>
        {auditData && (
          <>
            <Text type="secondary">原因：{auditData.reason}；查看人：{auditData.viewed_by}</Text>
            <List
              dataSource={auditData.messages || []}
              renderItem={(item: any) => (
                <List.Item style={{ display: 'block' }}>
                  <Text type="secondary" className="ac-fs-xs">{item.role} · {item.created_at}</Text>
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
