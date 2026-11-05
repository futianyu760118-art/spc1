import React, { useCallback, useEffect, useState } from 'react'
import { Button, Drawer } from 'antd'
import { AppstoreOutlined, ClearOutlined, HistoryOutlined } from '@ant-design/icons'
import { useLocation, useNavigate } from 'react-router-dom'
import ChatPanel from '../../components/Assistant/ChatPanel'
import ChatHistorySidebar from '../../components/Assistant/ChatHistorySidebar'
import AssistantContextRail from '../../components/Assistant/AssistantContextRail'
import { useAssistantChat } from '../../components/Assistant/useAssistantChat'
import { TeamAgent } from '../../components/Assistant/types'
import { agentApi } from '../../services/agent'
import '../../components/Assistant/assistant.css'
import '../AgentCenter/agent-center.css'
import '../AgentCenter/agent-center-v3.css'

interface ConversationItem {
  id: number
  title?: string
  last_message_at?: string
}

export default function AssistantPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [teamAgents, setTeamAgents] = useState<TeamAgent[]>([])
  const [conversations, setConversations] = useState<ConversationItem[]>([])
  const [loadingConversations, setLoadingConversations] = useState(false)
  const [activeConversationId, setActiveConversationId] = useState<number | null>(null)
  const [contextOpen, setContextOpen] = useState(() => window.innerWidth >= 1200)
  const [historyOpen, setHistoryOpen] = useState(false)
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

  const manageTeam = () => navigate('/agents')

  return (
    <div className="sc-page ai-center ai-chat-page ac-page">
      <div className="ai-chat">
        <ChatHistorySidebar
          conversations={conversations}
          loading={loadingConversations}
          activeId={activeConversationId}
          teamCount={teamAgents.length}
          onNew={newChat}
          onOpen={openConversation}
          onManageTeam={manageTeam}
        />

        <div className="ai-chat-main">
          <div className="ai-chat-head">
            <strong>AI 智能助手</strong>
            <span className="ai-online"><i />在线</span>
            <span className="ai-chat-head-hint">{teamAgents.length} 位团队成员</span>
            <div className="ai-chat-head-actions">
              <Button
                type="text"
                size="small"
                icon={<HistoryOutlined />}
                className="ai-history-toggle"
                onClick={() => setHistoryOpen(true)}
                title="历史会话"
              >
                历史
              </Button>
              <Button
                type="text"
                size="small"
                icon={<ClearOutlined />}
                disabled={messages.length === 0}
                onClick={newChat}
                title="清空对话"
              >
                清空
              </Button>
              <Button
                type="text"
                size="small"
                icon={<AppstoreOutlined />}
                className="ai-context-toggle"
                onClick={() => setContextOpen(value => !value)}
                title={contextOpen ? '收起上下文' : '展开上下文'}
              >
                上下文
              </Button>
            </div>
          </div>

          <ChatPanel
            messages={messages}
            loading={loading}
            teamAgents={teamAgents}
            onSend={text => send(text)}
            onStop={stopStreaming}
            onConfirm={confirmWrite}
            onCancelConfirmation={cancelWrite}
          />
        </div>

        {contextOpen && (
          <AssistantContextRail
            teamAgents={teamAgents}
            messages={messages}
            onCollapse={() => setContextOpen(false)}
          />
        )}
      </div>

      <Drawer
        placement="left"
        width={300}
        open={historyOpen}
        onClose={() => setHistoryOpen(false)}
        className="sc-page ai-center"
        styles={{ body: { padding: 0 } }}
      >
        <ChatHistorySidebar
          conversations={conversations}
          loading={loadingConversations}
          activeId={activeConversationId}
          teamCount={teamAgents.length}
          onNew={() => { setHistoryOpen(false); newChat() }}
          onOpen={(id) => { setHistoryOpen(false); openConversation(id) }}
          onManageTeam={() => { setHistoryOpen(false); manageTeam() }}
        />
      </Drawer>
    </div>
  )
}
