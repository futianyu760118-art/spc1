import React, { useCallback, useEffect, useState } from 'react'
import { Button, Card, Drawer, Empty, Input, List, Popconfirm, Space, Table, Tag, Typography, message } from 'antd'
import { PlusOutlined, RobotOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { agentApi, TeamMember } from '../../../services/agent'
import { CapabilityTags } from '../../../components/Agent/CapabilityTags'

const { Text } = Typography

interface Candidate {
  id: number
  agent_no: string
  name: string
  capabilities: Array<{ code: string; name: string }>
  description?: string | null
}

export default function TeamConfig() {
  const navigate = useNavigate()
  const [rows, setRows] = useState<TeamMember[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [addOpen, setAddOpen] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [loadingCandidates, setLoadingCandidates] = useState(false)
  const [addingId, setAddingId] = useState<number | null>(null)

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

  const loadCandidates = useCallback(async (value: string) => {
    setLoadingCandidates(true)
    try {
      const res: any = await agentApi.candidates(value)
      setCandidates(res.data?.items || [])
    } finally {
      setLoadingCandidates(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (addOpen) loadCandidates(keyword)
  }, [addOpen, keyword, loadCandidates])

  const addMember = async (agentId: number) => {
    setAddingId(agentId)
    try {
      await agentApi.addMember(agentId)
      message.success('已加入团队')
      await Promise.all([load(), loadCandidates(keyword)])
    } finally {
      setAddingId(null)
    }
  }

  const removeMember = async (agentId: number) => {
    await agentApi.removeMember(agentId)
    message.success('已移出团队')
    await load()
  }

  const openAssistant = () => {
    navigate('/ai-assistant')
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
          <Text type="secondary" className="ac-fs-xs">
            团队成员 {rows.length} 个。团队成员的能力决定了智能助手能帮你做什么。
          </Text>
        </div>
        {error ? (
          <Empty description={error}><Button onClick={load}>重试</Button></Empty>
        ) : rows.length === 0 && !loading ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有团队成员">
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
                title: '名称', dataIndex: 'name', width: 200, ellipsis: true,
                render: (value: string) => <span style={{ fontWeight: 500 }}>{value}</span>,
              },
              { title: '编号', dataIndex: 'agent_no', width: 150, ellipsis: true },
              {
                title: '能力', dataIndex: 'capabilities', width: 200,
                render: (value: TeamMember['capabilities']) => <CapabilityTags items={value} max={2} />,
              },
              {
                title: '技能', dataIndex: 'skills', width: 160,
                render: (value: TeamMember['skills']) => (
                  value && value.length > 0
                    ? <Space size={2} wrap>
                        {value.slice(0, 2).map(skill => (
                          <Tag key={skill.id} color="purple">{skill.name}</Tag>
                        ))}
                        {value.length > 2 && <Text type="secondary">+{value.length - 2}</Text>}
                      </Space>
                    : <Text type="secondary">-</Text>
                ),
              },
              {
                title: '状态', dataIndex: 'status', width: 86,
                render: (value: string) => <Tag color={value === 'active' ? 'green' : 'default'}>{value === 'active' ? '启用' : '停用'}</Tag>,
              },
              {
                title: '说明', dataIndex: 'description', ellipsis: true,
                render: (value: string | null) => value || <Text type="secondary">-</Text>,
              },
              {
                title: '操作', width: 80,
                render: (_: any, row: TeamMember) => (
                  <Popconfirm
                    title="移除该成员？"
                    description="移除后智能助手将失去该成员对应的能力。"
                    okText="移除"
                    cancelText="取消"
                    okButtonProps={{ danger: true }}
                    onConfirm={() => removeMember(row.id)}
                  >
                    <Button type="link" size="small" danger>移除</Button>
                  </Popconfirm>
                ),
              },
            ]}
          />
        )}
      </Card>

      <Drawer
        title="添加成员"
        width={520}
        open={addOpen}
        onClose={() => setAddOpen(false)}
        destroyOnClose
      >
        <Space direction="vertical" style={{ width: '100%' }} size={12}>
          <Input.Search
            placeholder="搜索名称 / 编号"
            allowClear
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
          />
          <List
            loading={loadingCandidates}
            dataSource={candidates}
            locale={{ emptyText: '没有可添加的智能体' }}
            renderItem={(item: Candidate) => (
              <List.Item
                actions={[
                  <Button
                    key="add"
                    type="link"
                    size="small"
                    loading={addingId === item.id}
                    onClick={() => addMember(item.id)}
                  >
                    加入
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={<span>{item.name} <Text type="secondary" className="ac-fs-xs">{item.agent_no}</Text></span>}
                  description={(
                    <Space size={4} wrap>
                      <CapabilityTags items={item.capabilities} max={3} />
                      {item.description && <Text type="secondary" className="ac-fs-xs">{item.description}</Text>}
                    </Space>
                  )}
                />
              </List.Item>
            )}
          />
        </Space>
      </Drawer>
    </div>
  )
}
