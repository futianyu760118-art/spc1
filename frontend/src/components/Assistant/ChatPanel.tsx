import React, { useRef, useEffect, useState } from 'react'
import { Input, Button, Space, Tag, Spin, Typography } from 'antd'
import { SendOutlined, ClearOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { ChatMessage, AssistantCard, Skill } from './useAssistantChat'
import SummaryCard from './cards/SummaryCard'
import OrderListCard from './cards/OrderListCard'
import TextCard from './cards/TextCard'

const { Text } = Typography

interface Props {
  messages: ChatMessage[]
  loading: boolean
  skills: Skill[]
  onSend: (text: string) => void
  onClear: () => void
}

const renderCard = (card: AssistantCard, index: number) => {
  switch (card.type) {
    case 'summary':
      return <SummaryCard key={index} title={card.title} payload={card.payload} />
    case 'order_list':
      return <OrderListCard key={index} title={card.title} payload={card.payload} />
    case 'text':
      return <TextCard key={index} title={card.title} payload={card.payload} />
    default:
      return null
  }
}

const ChatPanel: React.FC<Props> = ({ messages, loading, skills, onSend, onClear }) => {
  const [inputValue, setInputValue] = useState('')
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [messages, loading])

  const handleSend = () => {
    if (inputValue.trim()) {
      onSend(inputValue)
      setInputValue('')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 快捷指令 */}
      {messages.length === 0 && skills.length > 0 && (
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #f0f0f0' }}>
          <Text type="secondary" style={{ fontSize: 12, marginBottom: 8, display: 'block' }}>
            <ThunderboltOutlined /> 快捷指令
          </Text>
          <Space wrap size={[6, 6]}>
            {skills.map(s => (
              <Tag
                key={s.intent}
                color="blue"
                style={{ cursor: 'pointer', fontSize: 12 }}
                onClick={() => onSend(s.keywords[0] || s.name)}
              >
                {s.name}
              </Tag>
            ))}
          </Space>
        </div>
      )}

      {/* 消息列表 */}
      <div
        ref={listRef}
        style={{
          flex: 1,
          overflow: 'auto',
          padding: '12px 16px',
        }}
      >
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', padding: '40px 0', color: '#999' }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>🤖</div>
            <div>您好！我是智能操作助手</div>
            <div style={{ fontSize: 12, marginTop: 4 }}>试试输入"今日交付"查看今日订单盘点</div>
          </div>
        )}
        {messages.map(msg => (
          <div
            key={msg.id}
            style={{
              marginBottom: 12,
              display: 'flex',
              flexDirection: 'column',
              alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
            }}
          >
            {/* 文本气泡 */}
            <div
              style={{
                maxWidth: '85%',
                padding: '8px 12px',
                borderRadius: msg.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
                background: msg.role === 'user' ? '#1890ff' : '#f5f5f5',
                color: msg.role === 'user' ? '#fff' : '#333',
                fontSize: 13,
                lineHeight: 1.6,
                wordBreak: 'break-word',
              }}
            >
              {msg.content}
            </div>

            {/* 卡片 */}
            {msg.cards && msg.cards.length > 0 && (
              <div style={{ maxWidth: '100%', marginTop: 8 }}>
                {msg.cards.map((card, i) => renderCard(card, i))}
              </div>
            )}

            {/* 建议按钮 */}
            {msg.suggestions && msg.suggestions.length > 0 && (
              <Space wrap size={[4, 4]} style={{ marginTop: 6 }}>
                {msg.suggestions.map((s, i) => (
                  <Tag
                    key={i}
                    color="processing"
                    style={{ cursor: 'pointer', fontSize: 12 }}
                    onClick={() => onSend(s)}
                  >
                    {s}
                  </Tag>
                ))}
              </Space>
            )}
          </div>
        ))}

        {loading && (
          <div style={{ textAlign: 'center', padding: '12px 0' }}>
            <Spin size="small" />
            <Text type="secondary" style={{ marginLeft: 8, fontSize: 12 }}>思考中...</Text>
          </div>
        )}
      </div>

      {/* 输入区 */}
      <div style={{ padding: '8px 12px', borderTop: '1px solid #f0f0f0', display: 'flex', gap: 8 }}>
        <Input
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={'输入问题，如"今日交付"'}
          style={{ flex: 1 }}
          disabled={loading}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSend}
          disabled={!inputValue.trim() || loading}
        />
        {messages.length > 0 && (
          <Button
            icon={<ClearOutlined />}
            onClick={onClear}
            title="清空对话"
          />
        )}
      </div>
    </div>
  )
}

export default ChatPanel
