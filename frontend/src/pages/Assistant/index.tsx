import React, { useCallback, useEffect, useState } from 'react'
import { Button, Card, Empty, List, Space, Tag, Typography } from 'antd'
import { HistoryOutlined, PlusOutlined, ReloadOutlined, RobotOutlined } from '@ant-design/icons'
import { useLocation, useNavigate } from 'react-router-dom'
import ChatPanel from '../../components/Assistant/ChatPanel'
import { useAssistantChat } from '../../components/Assistant/useAssistantChat'
import { agentApi } from '../../services/agent'
import './assistant.css'
import { scalePx } from '../../utils/fontSize'

const { Text, Title } = Typography

interface ConversationItem {
  id: number
  title?: string
  last_message_at?: string
}

interface TeamAgent {
  id: number
  name: string
  capabilities?: Array<{ code: string; name: string }>
  status?: string
}

export default function AssistantPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [teamAgents, setTeamAgents] = useState<TeamAgent[]>([])
  const [conversations, setConversations] = useState<ConversationItem[]>([])
  const [loadingConversations, setLoadingConversations] = useState(false)
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null)
  const {
    messages, loading, send, clearMessages, stopStreaming,
    confirmWrite, cancelWrite, loadConversation,
  } = useAssistantChat()

  const loadTeam = useCallback(async () => {
    try {
      const res: any = await agentApi.team()
      setTeamAgents(res.data?.items || [])
    } catch {
      setTeamAgents([])
    }
  }, [])

  const loadConversations = useCallback(async () => {
    setLoadingConversations(true)
    try {
      const res: any = await agentApi.conversations({ page_size: 50 }, true)
      setConversations(res.data?.items || [])
    } catch {
      setConversations([])
    } finally {
      setLoadingConversations(false)
    }
  }, [])

  useEffect(() => {
    loadTeam()
    loadConversations()
  }, [loadTeam, loadConversations])

  useEffect(() => {
    const state = location.state as {
      newConversation?: boolean
      conversationId?: number
    } | null
    if (!state) return
    if (state.newConversation) {
      clearMessages()
      setActiveConversationId(null)
    } else if (state.conversationId) {
      const conversationId = Number(state.conversationId)
      setActiveConversationId(conversationId)
      loadConversation(conversationId)
    }
    navigate(location.pathname, { replace: true, state: null })
  }, [location.state, location.pathname, clearMessages, loadConversation, navigate])

  const newChat = () => {
    clearMessages()
    setActiveConversationId(null)
  }

  const openConversation = (conversationId: number) => {
    setActiveConversationId(conversationId)
    loadConversation(conversationId)
  }

  return (
    <div className="assistant-page" style={{ display: 'flex', gap: 16, height: 'calc(100vh - 150px)', minHeight: 520 }}>
      <Card
        title={<Space><HistoryOutlined />历史会话</Space>}
        extra={(
          <Button
            type="text"
            size="small"
            icon={<ReloadOutlined />}
            loading={loadingConversations}
            onClick={loadConversations}
          />
        )}
        style={{ width: 280, flexShrink: 0, display: 'flex', flexDirection: 'column' }}
        styles={{ body: { flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', padding: 12 } }}
      >
        <Button type="primary" icon={<PlusOutlined />} block onClick={newChat}>
          新建对话
        </Button>
        <div style={{ flex: 1, minHeight: 0, overflow: 'auto', marginTop: 12 }}>
          {conversations.length === 0 && !loadingConversations ? (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无历史会话" />
          ) : (
            <List
              size="small"
              dataSource={conversations}
              loading={loadingConversations}
              renderItem={(item: ConversationItem) => (
                <List.Item
                  onClick={() => openConversation(item.id)}
                  style={{
                    cursor: 'pointer',
                    padding: '8px 10px',
                    borderRadius: 8,
                    background: activeConversationId === item.id ? '#eef2ff' : undefined,
                  }}
                >
                  <List.Item.Meta
                    title={<span style={{ fontSize: scalePx(13) }}>{item.title || `会话 #${item.id}`}</span>}
                    description={(
                      <span style={{ fontSize: scalePx(11) }}>
                        {item.last_message_at ? new Date(item.last_message_at).toLocaleString('zh-CN') : ''}
                      </span>
                    )}
                  />
                </List.Item>
              )}
            />
          )}
        </div>
        <Text type="secondary" className="ac-fs-xs">
          团队成员 {teamAgents.length} 个
        </Text>
      </Card>

      <Card
        style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}
        styles={{ body: { flex: 1, minHeight: 0, padding: 0, display: 'flex', flexDirection: 'column' } }}
      >
        <div style={{
          padding: '12px 16px',
          borderBottom: '1px solid #f0f0f0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
        }}>
          <Space>
            <RobotOutlined style={{ color: '#4f46e5' }} />
            <Title level={5} style={{ margin: 0 }}>AI 智能助手</Title>
            <Tag color="blue">{teamAgents.length} 个团队成员</Tag>
          </Space>
          <Text type="secondary" className="ac-fs-xs">
            工具由团队智能体的能力与技能配置决定
          </Text>
        </div>
        <div style={{ flex: 1, minHeight: 0, background: '#f8fafc' }}>
          <ChatPanel
            messages={messages}
            loading={loading}
            teamAgents={teamAgents}
            onSend={(text) => { send(text) }}
            onClear={newChat}
            onStop={stopStreaming}
            onConfirm={confirmWrite}
            onCancelConfirmation={cancelWrite}
          />
        </div>
      </Card>
    </div>
  )
}
