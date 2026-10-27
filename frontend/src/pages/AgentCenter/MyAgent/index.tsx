import React, { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Card, Col, Descriptions, Drawer, Empty, List, Row, Space, Statistic, Table, Tag, Typography,
} from 'antd'
import { MessageOutlined, RobotOutlined, TeamOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { agentApi } from '../../../services/agent'
import Markdown from '../../../components/Markdown'

const { Text, Title } = Typography

interface Conversation {
  id: number
  title?: string
  task_id?: number | null
  status: string
  last_message_at?: string
}

export default function MyAgent() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversationOpen, setConversationOpen] = useState(false)
  const [conversationDetail, setConversationDetail] = useState<any>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [me, convs]: any = await Promise.all([agentApi.me(), agentApi.conversations({ page_size: 50 })])
      setData(me.data)
      setConversations(convs.data?.items || [])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const openConversation = async (id: number) => {
    const res: any = await agentApi.conversation(id)
    setConversationDetail(res.data)
    setConversationOpen(true)
  }

  const openAssistant = () => {
    window.dispatchEvent(new CustomEvent('spc:open-assistant', { detail: {} }))
  }

  if (!data) return <Card loading={loading}>加载中...</Card>

  const agent = data.agent || {}
  const summary = data.task_summary || {}

  return (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Card>
        <Row gutter={16} align="middle">
          <Col flex="none">
            <div style={{
              width: 64, height: 64, borderRadius: 18, display: 'flex', alignItems: 'center',
              justifyContent: 'center', background: 'linear-gradient(135deg,#6366f1,#a855f7)', color: '#fff',
              fontSize: 28,
            }}>
              <RobotOutlined />
            </div>
          </Col>
          <Col flex="auto">
            <Title level={4} style={{ margin: 0 }}>{data.display_name}</Title>
            <Space size={8} wrap style={{ marginTop: 6 }}>
              <Tag color={agent.status === 'active' ? 'green' : 'default'}>
                {agent.status === 'active' ? '启用' : '禁用'}
              </Tag>
              <Text type="secondary">智能体编号 {agent.agent_no}</Text>
              <Text type="secondary">绑定用户 {agent.username}</Text>
              {data.is_supervisor && <Tag color="blue" icon={<TeamOutlined />}>主管</Tag>}
            </Space>
          </Col>
          <Col>
            <Space>
              <Button icon={<MessageOutlined />} onClick={openAssistant}>打开助手</Button>
              <Button type="primary" icon={<ThunderboltOutlined />} onClick={openAssistant}>和智能体对话</Button>
            </Space>
          </Col>
        </Row>
      </Card>

      <Row gutter={16}>
        <Col span={6}><Card><Statistic title="未完成任务" value={summary.open || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="逾期任务" value={summary.overdue || 0} valueStyle={{ color: '#dc2626' }} /></Card></Col>
        <Col span={6}><Card><Statistic title="近 7 天完成" value={summary.completed_week || 0} /></Card></Col>
        <Col span={6}><Card><Statistic title="直属成员" value={data.children_count || 0} /></Card></Col>
      </Row>

      <Card title="智能体概况">
        <Descriptions column={2} size="small" bordered>
          <Descriptions.Item label="上级智能体">{data.parent_display_name || '无'}</Descriptions.Item>
          <Descriptions.Item label="有效数据范围">{data.scope?.summary || '本人数据'}</Descriptions.Item>
          <Descriptions.Item label="近 7 天对话">{data.usage_7d?.runs || 0} 次</Descriptions.Item>
          <Descriptions.Item label="近 7 天 Token">{data.usage_7d?.total_tokens || 0}</Descriptions.Item>
          <Descriptions.Item label="有效能力" span={2}>
            <Space wrap>
              {(data.effective_capabilities || []).map((cap: any) => (
                <Tag key={cap.code} color="blue">{cap.name}</Tag>
              ))}
              {(!data.effective_capabilities || data.effective_capabilities.length === 0) && <Text type="secondary">无</Text>}
            </Space>
          </Descriptions.Item>
        </Descriptions>
        {!data.is_supervisor && (
          <Alert
            style={{ marginTop: 12 }}
            type="info"
            showIcon
            message="当前没有直属子智能体。团队入口在有成员后自动出现；添加成员请调用助手或联系管理员。"
          />
        )}
      </Card>

      <Card title="会话历史" extra={<Button onClick={openAssistant}>新建对话</Button>}>
        {conversations.length === 0 ? <Empty description="暂无会话" /> : (
          <Table
            size="small"
            rowKey="id"
            dataSource={conversations}
            pagination={{ pageSize: 8 }}
            columns={[
              { title: '标题', dataIndex: 'title', render: (v: string) => v || '（未命名会话）' },
              { title: '关联任务', dataIndex: 'task_id', width: 100, render: (v: number | null) => v ? `#${v}` : '-' },
              { title: '状态', dataIndex: 'status', width: 90, render: (v: string) => <Tag>{v === 'active' ? '进行中' : '已归档'}</Tag> },
              { title: '最后消息', dataIndex: 'last_message_at', width: 180, render: (v: string) => v ? new Date(v).toLocaleString('zh-CN') : '-' },
              { title: '操作', width: 80, render: (_: any, row: Conversation) => <Button type="link" onClick={() => openConversation(row.id)}>查看</Button> },
            ]}
          />
        )}
      </Card>

      <Drawer
        title={conversationDetail?.title || '会话内容'}
        width={560}
        open={conversationOpen}
        onClose={() => setConversationOpen(false)}
      >
        <List
          dataSource={conversationDetail?.messages || []}
          locale={{ emptyText: '暂无消息' }}
          renderItem={(item: any) => (
            <List.Item style={{ display: 'block' }}>
              <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 4 }}>
                {item.role === 'user' ? '我' : '智能体'} · {item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : ''}
              </div>
              {item.role === 'assistant'
                ? <Markdown>{item.content || ''}</Markdown>
                : <div style={{ whiteSpace: 'pre-wrap' }}>{item.content}</div>}
            </List.Item>
          )}
        />
      </Drawer>
    </Space>
  )
}
