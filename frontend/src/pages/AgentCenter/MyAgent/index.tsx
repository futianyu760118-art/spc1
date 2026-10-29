import React, { useCallback, useEffect, useState } from 'react'
import {
  Button, Card, Drawer, Empty, List, Row, Col, Space, Statistic, Table, Tag, Typography,
} from 'antd'
import { MessageOutlined, PlusOutlined, RobotOutlined } from '@ant-design/icons'
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

  const calls: AgentCall[] = data.recent_calls || []
  const capabilities = data.effective_capabilities || []

  return (
    <div className="agent-center-page">
      <Card className="ac-hero">
        <Row align="middle" gutter={14}>
          <Col flex="none">
            <div style={{
              width: 52, height: 52, borderRadius: 15, display: 'flex', alignItems: 'center',
              justifyContent: 'center', background: 'linear-gradient(135deg,#6366f1,#a855f7)', color: '#fff',
              fontSize: 'var(--ac-icon-lg)',
            }}>
              <RobotOutlined />
            </div>
          </Col>
          <Col flex="auto">
            <Title level={4} style={{ margin: 0 }}>{data.display_name}</Title>
            <Text type="secondary" className="ac-fs-xs">智能助手的能力来自你的团队成员</Text>
          </Col>
          <Col>
            <Space>
              <Button icon={<MessageOutlined />} onClick={openAssistant}>打开助手</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={newConversation}>新建对话</Button>
            </Space>
          </Col>
        </Row>
        <Row gutter={16} style={{ marginTop: 10 }}>
          <Col span={6}><Statistic title="团队成员" value={data.team_size || 0} /></Col>
          <Col span={6}><Statistic title="近 7 天对话" value={data.usage_7d?.runs || 0} /></Col>
          <Col span={6}><Statistic title="近 7 天 Token" value={data.usage_7d?.total_tokens || 0} /></Col>
          <Col span={6}><Statistic title="最近调用" value={calls.length} /></Col>
        </Row>
      </Card>

      <div className="ac-grid" style={{ gridTemplateColumns: '0.95fr 1.15fr 0.9fr' }}>
        <div className="ac-col">
          <Card
            title="我的团队能力"
            extra={<Button size="small" onClick={() => navigate('/agents/team')}>去勾选成员</Button>}
          >
            <Space wrap size={[4, 4]}>
              {capabilities.map((cap: { code: string; name: string }) => (
                <Tag key={cap.code} color="blue" style={{ marginInlineEnd: 0 }}>{cap.name}</Tag>
              ))}
              {capabilities.length === 0 && <Text type="secondary">暂无能力，先去勾选团队成员</Text>}
            </Space>
          </Card>
        </div>

        <div className="ac-col">
          <Card title="最近调用">
            {calls.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无调用" /> : (
              <Table
                size="small"
                rowKey="id"
                dataSource={calls}
                tableLayout="fixed"
                pagination={{ pageSize: 4, size: 'small', showSizeChanger: false }}
                columns={[
                  {
                    title: '成员', dataIndex: 'callee', width: 110, ellipsis: true,
                    render: (callee: AgentCall['callee']) => callee?.name || '-',
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
              <div className="ac-fs-xs" style={{ color: '#94a3b8', marginBottom: 4 }}>
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
