import React, { useCallback, useEffect, useState } from 'react'
import {
  Button, Card, Descriptions, Drawer, Empty, List, Row, Col, Space, Statistic, Table, Tag, Typography,
} from 'antd'
import { MessageOutlined, PlusOutlined, RobotOutlined, TeamOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { agentApi, AgentCall } from '../../../services/agent'
import Markdown from '../../../components/Markdown'

const { Text, Title } = Typography

interface Conversation {
  id: number
  title?: string
  status: string
  last_message_at?: string
}

export default function MyAgent() {
  const navigate = useNavigate()
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [conversationOpen, setConversationOpen] = useState(false)
  const [conversationDetail, setConversationDetail] = useState<any>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [me, convs]: any = await Promise.all([agentApi.me(), agentApi.conversations({ page_size: 50 })])
      setData(me.data)
      setConversations(convs.data?.items || [])
    } catch (e: any) {
      setError(e?._apiData?.message || e?.message || '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const openAssistant = () => {
    window.dispatchEvent(new CustomEvent('spc:open-assistant', { detail: {} }))
  }

  const newConversation = () => {
    window.dispatchEvent(new CustomEvent('spc:open-assistant', { detail: { newConversation: true } }))
  }

  const continueConversation = (id: number) => {
    window.dispatchEvent(new CustomEvent('spc:open-assistant', { detail: { conversationId: id } }))
  }

  const openConversation = async (id: number) => {
    const res: any = await agentApi.conversation(id)
    setConversationDetail(res.data)
    setConversationOpen(true)
  }

  if (error) {
    return (
      <div className="agent-center-page">
        <Card><Empty description={error}><Button onClick={load}>重试</Button></Empty></Card>
      </div>
    )
  }

  if (!data) {
    return <div className="agent-center-page"><Card loading={loading}>加载中...</Card></div>
  }

  const agent = data.agent || {}
  const calls: AgentCall[] = data.recent_calls || []

  return (
    <div className="agent-center-page">
      <Card className="ac-hero">
        <Row align="middle" gutter={14}>
          <Col flex="none">
            <div style={{
              width: 52, height: 52, borderRadius: 15, display: 'flex', alignItems: 'center',
              justifyContent: 'center', background: 'linear-gradient(135deg,#6366f1,#a855f7)', color: '#fff',
              fontSize: 24,
            }}>
              <RobotOutlined />
            </div>
          </Col>
          <Col flex="auto">
            <Title level={4} style={{ margin: 0 }}>{data.display_name}</Title>
            <Space size={8} wrap style={{ marginTop: 4 }}>
              <Tag color={agent.status === 'active' ? 'green' : 'default'}>
                {agent.status === 'active' ? '启用' : '禁用'}
              </Tag>
              <Text type="secondary" style={{ fontSize: 12 }}>{agent.agent_no}</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>绑定用户 {agent.username}</Text>
              {data.is_supervisor && <Tag color="blue" icon={<TeamOutlined />}>主管</Tag>}
            </Space>
          </Col>
          <Col>
            <Space>
              {!data.is_supervisor && (
                <Button onClick={() => navigate('/agents/team')}>添加成员</Button>
              )}
              <Button icon={<MessageOutlined />} onClick={openAssistant}>打开助手</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={newConversation}>新建对话</Button>
            </Space>
          </Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 10 }}>
          <Col span={6}><Statistic title="直属成员" value={data.children_count || 0} /></Col>
          <Col span={6}><Statistic title="近 7 天对话" value={data.usage_7d?.runs || 0} /></Col>
          <Col span={6}><Statistic title="近 7 天 Token" value={data.usage_7d?.total_tokens || 0} /></Col>
          <Col span={6}><Statistic title="最近委派" value={calls.length} /></Col>
        </Row>
      </Card>

      <div className="ac-grid" style={{ gridTemplateColumns: '0.95fr 1.15fr 0.9fr' }}>
        <div className="ac-col">
          <Card title="智能体概况">
            <Descriptions column={1} size="small" colon={false}>
              <Descriptions.Item label="上级">{data.parent_display_name || '无'}</Descriptions.Item>
            </Descriptions>
            <div style={{ marginTop: 6, fontSize: 12, color: '#94a3b8' }}>有效能力</div>
            <Space wrap size={[4, 4]} style={{ marginTop: 4 }}>
              {(data.effective_capabilities || []).map((cap: any) => (
                <Tag key={cap.code} color="blue" style={{ marginInlineEnd: 0 }}>{cap.name}</Tag>
              ))}
              {(!data.effective_capabilities || data.effective_capabilities.length === 0) && <Text type="secondary">无</Text>}
            </Space>
          </Card>
        </div>

        <div className="ac-col">
          <Card title="最近委派" extra={<Text type="secondary" style={{ fontSize: 12 }}>父 Agent → 直属子 Agent</Text>}>
            {calls.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无委派" /> : (
              <Table
                size="small"
                rowKey="id"
                dataSource={calls}
                tableLayout="fixed"
                pagination={{ pageSize: 4, size: 'small', showSizeChanger: false }}
                columns={[
                  {
                    title: '子智能体', key: 'target', width: 110, ellipsis: true,
                    render: (_: any, row: AgentCall) => {
                      const target = row.direction === 'outgoing' ? row.callee : row.caller
                      return target?.name || target?.username || target?.agent_id || '-'
                    },
                  },
                  { title: '能力', dataIndex: 'capability', width: 120, ellipsis: true },
                  { title: '状态', dataIndex: 'status', width: 76, render: (value: string) => <Tag>{value}</Tag> },
                  {
                    title: '结果', dataIndex: 'result_summary', ellipsis: true,
                    render: (value: string | null, row: AgentCall) => value || row.error || '-',
                  },
                ]}
              />
            )}
          </Card>
        </div>

        <div className="ac-col">
          <Card
            title="会话历史"
            extra={<Button size="small" onClick={newConversation}>新建</Button>}
          >
            {conversations.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无会话" /> : (
              <Table
                size="small"
                rowKey="id"
                dataSource={conversations}
                tableLayout="fixed"
                pagination={{ pageSize: 4, size: 'small', showSizeChanger: false }}
                columns={[
                  {
                    title: '标题', dataIndex: 'title', ellipsis: true,
                    render: (value: string, row: Conversation) => value || `会话 #${row.id}`,
                  },
                  {
                    title: '最后消息', dataIndex: 'last_message_at', width: 120,
                    render: (value: string) => value ? new Date(value).toLocaleString('zh-CN') : '-',
                  },
                  {
                    title: '操作', width: 92,
                    render: (_: any, row: Conversation) => (
                      <Space size={0}>
                        <Button type="link" size="small" onClick={() => continueConversation(row.id)}>继续</Button>
                        <Button type="link" size="small" onClick={() => openConversation(row.id)}>查看</Button>
                      </Space>
                    ),
                  },
                ]}
              />
            )}
          </Card>
        </div>
      </div>

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
    </div>
  )
}
