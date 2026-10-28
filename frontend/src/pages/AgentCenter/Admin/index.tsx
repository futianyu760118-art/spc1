import React, { useCallback, useEffect, useState } from 'react'
import {
  Button, Card, Col, Drawer, Input, List, Modal, Row, Select, Space, Statistic, Table, Tabs, Tag, Typography, message,
} from 'antd'
import { agentApi } from '../../../services/agent'
import { CapabilityPolicyDrawer } from '../../../components/Agent/CapabilityPolicyDrawer'

const { Text } = Typography
const PAGE_SIZE = 6

export default function AgentAdmin() {
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

  const [hierarchyAgent, setHierarchyAgent] = useState<any>(null)
  const [hierarchyAction, setHierarchyAction] = useState('reparent')
  const [newParentId, setNewParentId] = useState('')
  const [hierarchyReason, setHierarchyReason] = useState('')

  const [policyDetail, setPolicyDetail] = useState<any>(null)
  const [policyOpen, setPolicyOpen] = useState(false)
  const [policyLoading, setPolicyLoading] = useState(false)
  const [policySaving, setPolicySaving] = useState(false)

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
    loadAgents()
    loadStats()
  }

  const openPolicy = async (row: any) => {
    setPolicyOpen(true)
    setPolicyLoading(true)
    try {
      const res: any = await agentApi.adminAgent(row.id)
      setPolicyDetail(res.data)
    } finally {
      setPolicyLoading(false)
    }
  }

  const savePolicy = async (data: { granted: string[]; disabled: string[] }) => {
    if (!policyDetail?.agent?.id) return
    setPolicySaving(true)
    try {
      await agentApi.adminPolicy(policyDetail.agent.id, data)
      message.success('配置已保存')
      setPolicyOpen(false)
      loadAgents()
    } finally {
      setPolicySaving(false)
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
        <Col span={6}><Card styles={{ body: { padding: '10px 14px' } }}><Statistic title="委派调用" value={callTotalAll} /></Card></Col>
        <Col span={6}><Card styles={{ body: { padding: '10px 14px' } }}><Statistic title="失败/超时/拒绝" value={callFailed} valueStyle={{ color: callFailed ? '#dc2626' : undefined }} /></Card></Col>
      </Row>

      <Card className="ac-fill ac-admin-main">
        <Tabs
          className="ac-tabs"
          items={[
            {
              key: 'agents', label: '智能体与层级',
              children: (
                <Space direction="vertical" style={{ width: '100%', height: '100%' }} size={8}>
                  <Space wrap>
                    <Input.Search
                      placeholder="用户名 / 显示名 / 智能体编号" allowClear style={{ width: 300 }}
                      onSearch={v => { setAgentKeyword(v); setAgentPage(1) }}
                    />
                    <Select
                      value={agentStatus} style={{ width: 130 }} onChange={v => { setAgentStatus(v); setAgentPage(1) }}
                      options={[{ value: '', label: '全部状态' }, { value: 'active', label: '启用' }, { value: 'disabled', label: '禁用' }]}
                    />
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
                      { title: '编号', dataIndex: 'agent_no', width: 110, ellipsis: true },
                      { title: '名称', dataIndex: 'display_name', ellipsis: true },
                      { title: '用户', dataIndex: 'username', width: 110, ellipsis: true },
                      { title: '状态', dataIndex: 'status', width: 76, render: (v: string) => <Tag color={v === 'active' ? 'green' : 'default'}>{v === 'active' ? '启用' : '禁用'}</Tag> },
                      { title: '上级', dataIndex: 'parent_agent_id', width: 70, render: (v: number | null) => v || '-' },
                      { title: '子成员', dataIndex: 'children_count', width: 70 },
                      {
                        title: '操作', width: 120,
                        render: (_: any, row: any) => (
                          <Space size={0}>
                            <Button type="link" size="small" onClick={() => openHierarchy(row)}>层级</Button>
                            <Button type="link" size="small" onClick={() => openPolicy(row)}>能力</Button>
                          </Space>
                        ),
                      },
                    ]}
                  />
                </Space>
              ),
            },
            {
              key: 'calls', label: '委派审计',
              children: (
                <Space direction="vertical" style={{ width: '100%', height: '100%' }} size={8}>
                  <Space wrap>
                    <Input.Search placeholder="能力 / 指令 / 结果关键字" allowClear style={{ width: 280 }} onSearch={v => { setCallKeyword(v); setCallPage(1) }} />
                    <Select
                      value={callStatus} style={{ width: 140 }} onChange={v => { setCallStatus(v); setCallPage(1) }}
                      options={[
                        { value: '', label: '全部状态' }, { value: 'success', label: '成功' },
                        { value: 'failed', label: '失败' }, { value: 'timeout', label: '超时' },
                        { value: 'rejected', label: '拒绝' }, { value: 'running', label: '进行中' },
                      ]}
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
                      { title: '调用方', dataIndex: 'caller', width: 120, ellipsis: true, render: (v: any) => v?.name || v?.username || v?.agent_id || '-' },
                      { title: '被调用方', dataIndex: 'callee', width: 120, ellipsis: true, render: (v: any) => v?.name || v?.username || v?.agent_id || '-' },
                      { title: '能力', dataIndex: 'capability', width: 130, ellipsis: true },
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

      <CapabilityPolicyDrawer
        open={policyOpen}
        detail={policyDetail}
        loading={policyLoading}
        saving={policySaving}
        onClose={() => setPolicyOpen(false)}
        onSave={savePolicy}
      />

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
    </div>
  )
}
