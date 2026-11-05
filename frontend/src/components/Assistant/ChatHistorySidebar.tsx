import React from 'react'
import { Button, Empty, Spin } from 'antd'
import { PlusOutlined, TeamOutlined } from '@ant-design/icons'

interface ConversationItem {
  id: number
  title?: string
  last_message_at?: string
}

interface Props {
  conversations: ConversationItem[]
  loading: boolean
  activeId: number | null
  teamCount: number
  onNew: () => void
  onOpen: (id: number) => void
  onManageTeam: () => void
}

function startOfToday(): number {
  const now = new Date()
  return new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
}

function formatTime(value?: string): string {
  if (!value) return ''
  const date = new Date(value)
  const time = date.getTime()
  if (Number.isNaN(time)) return ''
  if (time >= startOfToday()) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' })
}

export default function ChatHistorySidebar({
  conversations, loading, activeId, teamCount, onNew, onOpen, onManageTeam,
}: Props) {
  const todayStart = startOfToday()
  const today = conversations.filter(item => item.last_message_at && new Date(item.last_message_at).getTime() >= todayStart)
  const earlier = conversations.filter(item => !item.last_message_at || new Date(item.last_message_at).getTime() < todayStart)

  const renderGroup = (title: string, items: ConversationItem[]) => {
    if (items.length === 0) return null
    return (
      <div className="ai-side-group">
        <div className="ai-side-group-title">{title}</div>
        {items.map(item => (
          <button
            key={item.id}
            type="button"
            className={`ai-side-item ${activeId === item.id ? 'active' : ''}`}
            onClick={() => onOpen(item.id)}
            title={item.title || `会话 #${item.id}`}
          >
            <span className="ai-side-item-title">{item.title || `会话 #${item.id}`}</span>
            <span className="ai-side-item-time">{formatTime(item.last_message_at)}</span>
          </button>
        ))}
      </div>
    )
  }

  return (
    <aside className="ai-chat-side">
      <div className="ai-side-head">
        <h2>历史会话</h2>
        <Button size="small" type="primary" icon={<PlusOutlined />} onClick={onNew}>
          新建
        </Button>
      </div>
      <div className="ai-side-list">
        {loading ? (
          <div className="ai-side-loading"><Spin size="small" /></div>
        ) : conversations.length === 0 ? (
          <div className="ai-side-empty">
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无历史会话" />
          </div>
        ) : (
          <>
            {renderGroup('今天', today)}
            {renderGroup('更早', earlier)}
          </>
        )}
      </div>
      <button type="button" className="ai-side-foot" onClick={onManageTeam}>
        <TeamOutlined />
        <span>团队成员 {teamCount} 位</span>
        <span className="ai-side-foot-link">管理</span>
      </button>
    </aside>
  )
}
