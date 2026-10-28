import React, { useCallback, useEffect, useState } from 'react'
import { Button, Card, Empty, Popconfirm, Space, Table, Tag, Typography, message } from 'antd'
import { PlusOutlined, RobotOutlined } from '@ant-design/icons'
import { agentApi } from '../../../services/agent'
import { AddMemberModal } from '../../../components/Agent/AddMemberModal'
import { CapabilityPolicyDrawer } from '../../../components/Agent/CapabilityPolicyDrawer'

const { Text } = Typography

export default function TeamConfig() {
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerLoading, setDrawerLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [detail, setDetail] = useState<any>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res: any = await agentApi.team()
      setRows(res.data?.items || [])
    } catch (e: any) {
      setError(e?._apiData?.message || e?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const openConfig = async (agentId: number) => {
    setDrawerOpen(true)
    setDrawerLoading(true)
    try {
      const res: any = await agentApi.teamMember(agentId)
      setDetail(res.data)
    } finally {
      setDrawerLoading(false)
    }
  }

  const savePolicy = async (data: { granted: string[]; disabled: string[] }) => {
    if (!detail?.agent?.id) return
    setSaving(true)
    try {
      await agentApi.updatePolicy(detail.agent.id, data)
      message.success('配置已保存并通知对方，最多 5 分钟内生效')
      setDrawerOpen(false)
      await load()
    } finally {
      setSaving(false)
    }
  }

  const removeMember = async (agentId: number) => {
    await agentApi.removeMember(agentId)
    message.success('已移除并通知对方')
    await load()
  }

  const openAssistant = () => {
    window.dispatchEvent(new CustomEvent('spc:open-assistant', { detail: {} }))
  }

  return (
    <div className="agent-center-page">
      <Card
        className="ac-fill"
        title="我的团队"
        extra={(
          <Space>
            <Button size="small" icon={<RobotOutlined />} onClick={openAssistant}>问助手</Button>
            <Button size="small" type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>添加成员</Button>
          </Space>
        )}
      >
        <div className="ac-team-toolbar">
          <Text type="secondary" style={{ fontSize: 12 }}>
            直属成员 {rows.length} 人。子智能体具备哪些只读能力，父智能体就可以把对应任务委派给它。
          </Text>
        </div>
        {error ? (
          <Empty description={error}><Button onClick={load}>重试</Button></Empty>
        ) : rows.length === 0 && !loading ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有直属成员">
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>添加第一个成员</Button>
          </Empty>
        ) : (
          <Table
            size="small"
            rowKey="id"
            loading={loading}
            dataSource={rows}
            tableLayout="fixed"
            pagination={{ pageSize: 7, size: 'small', showSizeChanger: false }}
            columns={[
              {
                title: '成员', dataIndex: 'name', width: 230,
                render: (value: string, row: any) => (
                  <div>
                    <div style={{ fontWeight: 500 }}>{value || row.username}</div>
                    <Text type="secondary" style={{ fontSize: 11 }}>{row.username} · {row.agent_no}</Text>
                  </div>
                ),
              },
              {
                title: '状态', dataIndex: 'status', width: 86,
                render: (value: string) => <Tag color={value === 'active' ? 'green' : 'default'}>{value === 'active' ? '启用' : '禁用'}</Tag>,
              },
              {
                title: '可委派能力', dataIndex: 'capabilities',
                render: (caps: Array<{ code: string; name: string }>) => {
                  const list = caps || []
                  const text = list.map(cap => cap.name).join('、') || '暂无'
                  return (
                    <div title={text} style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {list.slice(0, 2).map(cap => (
                        <Tag key={cap.code} style={{ marginInlineEnd: 4 }}>{cap.name}</Tag>
                      ))}
                      {list.length > 2 && <Tag>+{list.length - 2}</Tag>}
                      {list.length === 0 && <Text type="secondary" style={{ fontSize: 12 }}>暂无</Text>}
                    </div>
                  )
                },
              },
              {
                title: '操作', width: 170,
                render: (_: any, row: any) => (
                  <Space size={0}>
                    <Button type="link" size="small" onClick={() => openConfig(row.id)}>配置能力</Button>
                    <Popconfirm
                      title="移除直属成员？"
                      description="仅解除团队关系，用户和智能体保留。"
                      okText="移除"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                      onConfirm={() => removeMember(row.id)}
                    >
                      <Button type="link" size="small" danger>移除</Button>
                    </Popconfirm>
                  </Space>
                ),
              },
            ]}
          />
        )}
      </Card>

      <AddMemberModal open={addOpen} onClose={() => setAddOpen(false)} onAdded={load} />
      <CapabilityPolicyDrawer
        open={drawerOpen}
        detail={detail}
        loading={drawerLoading}
        saving={saving}
        onClose={() => setDrawerOpen(false)}
        onSave={savePolicy}
      />
    </div>
  )
}
