import React, { useCallback, useEffect, useState } from 'react'
import { Alert, Button, Card, Space, Table, Tag, Typography, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { agentApi } from '../../../services/agent'
import { AddMemberModal } from '../../../components/Agent/AddMemberModal'
import { CapabilityPolicyDrawer } from '../../../components/Agent/CapabilityPolicyDrawer'

const { Text } = Typography

export default function TeamConfig() {
  const [rows, setRows] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [addOpen, setAddOpen] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerLoading, setDrawerLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [detail, setDetail] = useState<any>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await agentApi.team()
      setRows(res.data?.items || [])
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

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card
        title="直属子智能体"
        extra={<Button type="primary" icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>添加成员</Button>}
      >
        <Alert
          type="info" showIcon style={{ marginBottom: 12 }}
          message="添加成员立即生效并通知对方；只能绑定无上级且无子智能体的叶子。P1 主管只能配置能力，数据范围由管理员配置。"
        />
        <Table
          size="small" rowKey="id" loading={loading} dataSource={rows}
          pagination={false}
          columns={[
            { title: '成员', dataIndex: 'name', render: (v: string, row: any) => (
              <div>
                <div style={{ fontWeight: 500 }}>{v || row.username}</div>
                <Text type="secondary" style={{ fontSize: 12 }}>{row.username} · {row.agent_no}</Text>
              </div>
            ) },
            { title: '状态', dataIndex: 'status', width: 100, render: (v: string) => <Tag color={v === 'active' ? 'green' : 'default'}>{v === 'active' ? '启用' : '禁用'}</Tag> },
            {
              title: '能力', dataIndex: 'effective_capabilities', width: 220,
              render: (caps: any[]) => (
                <Space wrap>
                  {(caps || []).slice(0, 3).map(cap => <Tag key={cap.code}>{cap.name}</Tag>)}
                  {(caps || []).length > 3 && <Tag>+{caps.length - 3}</Tag>}
                </Space>
              ),
            },
            { title: '数据范围', dataIndex: 'scope', width: 220, render: (scope: any) => <Text type="secondary">{scope?.summary || '-'}</Text> },
            { title: '未完成', dataIndex: 'open_task_count', width: 90 },
            { title: '逾期', dataIndex: 'overdue_task_count', width: 90, render: (v: number) => <Text type={v ? 'danger' : undefined}>{v}</Text> },
            {
              title: '操作', width: 100,
              render: (_: any, row: any) => <Button type="link" onClick={() => openConfig(row.id)}>配置</Button>,
            },
          ]}
        />
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
    </Space>
  )
}
