import React, { useRef, useEffect, useState } from 'react'
import { Input, Button, Space, Tag, Typography, Collapse, Descriptions } from 'antd'
import { SendOutlined, ClearOutlined, ThunderboltOutlined, RobotOutlined, BugOutlined, LoadingOutlined, PauseCircleOutlined } from '@ant-design/icons'
import Markdown from '../Markdown'
import { ChatMessage, AssistantCard, Skill, ToolCallStatus } from './useAssistantChat'
import SummaryCard from './cards/SummaryCard'
import OrderListCard from './cards/OrderListCard'
import TextCard from './cards/TextCard'
// Import new card components
import SearchResultListCard from './SearchResultListCard'
import MaterialListCard from './MaterialListCard'
import ProductionListCard from './ProductionListCard'
import ExceptionListCard from './ExceptionListCard'
import BasicDataCard from './BasicDataCard'
import ActionListCard from './ActionListCard'

const { Text } = Typography

// Format timestamp
const formatTimestamp = (timestamp: number) => {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (minutes < 1440) return `${Math.floor(minutes / 60)}小时前`
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

// Provider label mapping
const getProviderLabel = (provider?: string) => {
  if (!provider || provider === 'rule_based') return null
  const labels: Record<string, string> = {
    openai: 'AI',
    dashscope: '通义千问',
  }
  return labels[provider] || provider
}

interface Props {
  messages: ChatMessage[]
  loading: boolean
  skills: Skill[]
  onSend: (text: string) => void
  onClear: () => void
  onStop?: () => void
}

const renderCard = (card: AssistantCard, index: number, onSend?: (text: string) => void) => {
  switch (card.type) {
    case 'summary':
      return <SummaryCard key={index} title={card.title} payload={card.payload} />
    case 'order_list':
      return <OrderListCard key={index} title={card.title} payload={card.payload} />
    case 'text':
      return <TextCard key={index} title={card.title} payload={card.payload} />
    case 'search_result_list':
      return <SearchResultListCard key={index} title={card.title} items={card.payload.items} total={card.payload.total} />
    case 'material_list':
      return <MaterialListCard key={index} title={card.title} items={card.payload.items} total={card.payload.total} />
    case 'production_list':
      return <ProductionListCard key={index} title={card.title} items={card.payload.items} total={card.payload.total} />
    case 'exception_list':
      return <ExceptionListCard key={index} title={card.title} items={card.payload.items} total={card.payload.total} />
    case 'basicdata_list':
      return <BasicDataCard key={index} title={card.title} items={card.payload.items} total={card.payload.total} />
    case 'action_list':
      return (
        <ActionListCard
          key={index}
          title={card.title}
          actions={card.payload.actions}
          context={card.payload.context}
          onActionClick={(action) => {
            if (action.action_type === 'query' && action.action_params?.tool && onSend) {
              // 将行动建议转化为查询指令
              onSend(action.title)
            }
          }}
        />
      )
    default:
      return null
  }
}

// 工具调用状态指示器
const ToolCallIndicator: React.FC<{ toolCalls: ToolCallStatus[] }> = ({ toolCalls }) => {
  if (!toolCalls || toolCalls.length === 0) return null

  const toolNameMap: Record<string, string> = {
    search_orders: '订单',
    search_purchase_orders: '采购单',
    search_materials: '物料',
    search_production: '生产进度',
    search_exceptions: '异常',
    search_basicdata: '基础数据',
    search_run_orders: '跑单',
    search_invoices: '开票',
    search_eta_updates: '交期变更',
    search_users: '用户',
    get_dashboard_summary: '概览',
    suggest_actions: '行动建议',
  }

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
      {toolCalls.map((tc, i) => (
        <Tag
          key={i}
          color={tc.status === 'running' ? 'processing' : tc.status === 'done' ? 'success' : 'error'}
          style={{ fontSize: 10, lineHeight: '16px', margin: 0 }}
          icon={tc.status === 'running' ? <LoadingOutlined spin /> : undefined}
        >
          {toolNameMap[tc.name] || tc.name}
          {tc.status === 'done' && tc.itemCount !== undefined ? ` (${tc.itemCount})` : ''}
        </Tag>
      ))}
    </div>
  )
}

const ChatPanel: React.FC<Props> = ({ messages, loading, skills, onSend, onClear, onStop }) => {
  const [inputValue, setInputValue] = useState('')
  const shouldAutoScrollRef = useRef(true)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const list = listRef.current
    if (!list) return

    const lastMsg = messages[messages.length - 1]
    if (lastMsg?.role === 'user') {
      shouldAutoScrollRef.current = true
    }

    if (shouldAutoScrollRef.current) {
      list.scrollTop = list.scrollHeight
    }
  }, [messages, loading])

  // 流式内容变化时也自动滚动
  useEffect(() => {
    const list = listRef.current
    if (!list) return
    if (shouldAutoScrollRef.current) {
      list.scrollTop = list.scrollHeight
    }
  })

  const handleScroll = () => {
    const list = listRef.current
    if (!list) return

    const distanceToBottom = list.scrollHeight - list.scrollTop - list.clientHeight
    shouldAutoScrollRef.current = distanceToBottom < 40
  }

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
      {/* 消息列表 */}
      <div
        ref={listRef}
        onScroll={handleScroll}
        style={{
          flex: 1,
          overflow: 'auto',
          padding: '12px 14px',
        }}
      >
        {messages.length === 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100%', textAlign: 'center', padding: '24px 8px' }}>
            <div style={{
              width: 64, height: 64, borderRadius: 20,
              background: 'linear-gradient(135deg, #3b82f6 0%, #6366f1 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 12px 28px rgba(59,130,246,.35)',
              marginBottom: 16,
            }}>
              <RobotOutlined style={{ fontSize: 32, color: '#fff' }} />
            </div>
            <div style={{ fontSize: 16, fontWeight: 600, color: '#1e293b' }}>您好，我是 AI 智能助手</div>
            <div style={{ fontSize: 12, marginTop: 6, color: '#94a3b8' }}>
              不仅能查询数据，还能给出行动建议
            </div>

            {/* 推荐提问 */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 18, width: '100%', maxWidth: 320 }}>
              {[
                { icon: '📋', text: '今日简报', q: '今天有什么需要关注的？' },
                { icon: '⚠️', text: '逾期订单', q: '有哪些逾期订单？' },
                { icon: '🔔', text: '采购预警', q: '采购有什么风险？' },
              ].map(item => (
                <div
                  key={item.text}
                  onClick={() => onSend(item.q)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '10px 12px', borderRadius: 12,
                    background: '#fff', border: '1px solid #e2e8f0',
                    cursor: 'pointer', textAlign: 'left',
                    transition: 'all .15s ease',
                  }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = '#93c5fd'; e.currentTarget.style.background = '#f0f9ff' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = '#e2e8f0'; e.currentTarget.style.background = '#fff' }}
                >
                  <span style={{ fontSize: 18 }}>{item.icon}</span>
                  <span style={{ fontSize: 13, color: '#334155' }}>{item.text}</span>
                </div>
              ))}
            </div>

            {/* 技能快捷指令 */}
            {skills.length > 0 && (
              <>
                <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 18, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <ThunderboltOutlined style={{ color: '#f59e0b' }} /> 快捷指令
                </div>
                <Space wrap size={[6, 6]} style={{ justifyContent: 'center', maxWidth: 320 }}>
                  {skills.map(s => (
                    <Tag
                      key={s.intent}
                      style={{ cursor: 'pointer', fontSize: 12, borderRadius: 12, padding: '2px 10px', border: '1px solid #dbeafe', background: '#eff6ff', color: '#1d4ed8', margin: 0 }}
                      onClick={() => onSend(s.keywords[0] || s.name)}
                    >
                      {s.name}
                    </Tag>
                  ))}
                </Space>
              </>
            )}
          </div>
        )}
        {messages.map((msg) => {
          const providerLabel = getProviderLabel(msg.provider)

          return (
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
                  maxWidth: '88%',
                  padding: '10px 14px',
                  borderRadius: msg.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
                  background: msg.role === 'user' ? 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)' : '#fff',
                  color: msg.role === 'user' ? '#fff' : '#1e293b',
                  fontSize: 13,
                  lineHeight: 1.65,
                  wordBreak: 'break-word',
                  minHeight: msg.streaming && !msg.content ? 36 : undefined,
                  boxShadow: msg.role === 'user' ? '0 4px 12px rgba(59,130,246,.25)' : '0 1px 3px rgba(15,23,42,.06)',
                  border: msg.role === 'user' ? 'none' : '1px solid #eef2f7',
                }}
              >
                {/* 流式思考状态 */}
                {msg.streaming && msg.thinkingStage && !msg.content && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#999' }}>
                    <LoadingOutlined spin style={{ fontSize: 12 }} />
                    <span style={{ fontSize: 12 }}>{msg.thinkingStage}</span>
                  </div>
                )}

                {/* 消息内容 */}
                {msg.role === 'assistant' && msg.content ? (
                  <Markdown>{msg.content}</Markdown>
                ) : msg.role === 'user' ? (
                  msg.content
                ) : null}

                {/* 流式光标 */}
                {msg.streaming && msg.content && (
                  <span
                    style={{
                      display: 'inline-block',
                      width: 2,
                      height: 14,
                      background: '#6366f1',
                      marginLeft: 2,
                      animation: 'blink 1s infinite',
                      verticalAlign: 'text-bottom',
                    }}
                  />
                )}
              </div>

              {/* 工具调用状态 */}
              {msg.toolCalls && msg.toolCalls.length > 0 && (
                <div style={{ maxWidth: '85%', marginTop: 4 }}>
                  <ToolCallIndicator toolCalls={msg.toolCalls} />
                </div>
              )}

              {/* 时间戳和Provider标签 */}
              {!msg.streaming && (
                <div style={{ marginTop: 4, display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    {formatTimestamp(msg.timestamp)}
                  </Text>
                  {providerLabel && (
                    <Tag
                      icon={<RobotOutlined />}
                      color="blue"
                      style={{ fontSize: 10, lineHeight: '16px', margin: 0 }}
                    >
                      {providerLabel}
                    </Tag>
                  )}
                </div>
              )}

              {/* 卡片 */}
              {msg.cards && msg.cards.length > 0 && (
                <div style={{ maxWidth: '100%', marginTop: 8 }}>
                  {msg.cards.map((card, i) => renderCard(card, i, onSend))}
                </div>
              )}

              {/* 建议按钮 */}
              {msg.suggestions && msg.suggestions.length > 0 && (
                <Space wrap size={[6, 6]} style={{ marginTop: 8, maxWidth: '88%' }}>
                  {msg.suggestions.map((s, i) => (
                    <Tag
                      key={i}
                      style={{ cursor: 'pointer', fontSize: 12, borderRadius: 12, padding: '2px 10px', border: '1px solid #c7d2fe', background: '#eef2ff', color: '#4338ca', margin: 0 }}
                      onClick={() => onSend(s)}
                    >
                      {s}
                    </Tag>
                  ))}
                </Space>
              )}

              {/* 诊断信息 */}
              {msg.diagnostics && (
                <Collapse
                  ghost
                  size="small"
                  style={{ marginTop: 8, fontSize: 11 }}
                  items={[
                    {
                      key: 'diagnostics',
                      label: (
                        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          <BugOutlined style={{ fontSize: 10 }} />
                          诊断信息
                        </span>
                      ),
                      children: (
                        <Descriptions size="small" column={1} bordered style={{ fontSize: 11 }}>
                          {msg.diagnostics.trace_id && (
                            <Descriptions.Item label="Trace ID">
                              <code style={{ fontSize: 10 }}>{msg.diagnostics.trace_id}</code>
                            </Descriptions.Item>
                          )}
                          {msg.diagnostics.total_duration_ms && (
                            <Descriptions.Item label="总耗时">
                              {msg.diagnostics.total_duration_ms} ms
                            </Descriptions.Item>
                          )}
                          {msg.diagnostics.provider && (
                            <Descriptions.Item label="Provider">
                              {msg.diagnostics.provider}
                            </Descriptions.Item>
                          )}
                          {msg.diagnostics.path && (
                            <Descriptions.Item label="执行路径">
                              {msg.diagnostics.path}
                            </Descriptions.Item>
                          )}
                          {msg.diagnostics.fallback && (
                            <Descriptions.Item label="降级">
                              <Tag color="orange" style={{ fontSize: 10 }}>是</Tag>
                            </Descriptions.Item>
                          )}
                          {msg.diagnostics.skills && msg.diagnostics.skills.length > 0 && (
                            <Descriptions.Item label="技能调用">
                              {msg.diagnostics.skills.map((s: any, i: number) => (
                                <Tag key={i} color={s.status === 'success' ? 'green' : 'red'} style={{ fontSize: 10, marginBottom: 2 }}>
                                  {s.name} ({s.attempts}次, {s.duration_ms}ms)
                                </Tag>
                              ))}
                            </Descriptions.Item>
                          )}
                          {msg.diagnostics.tools && msg.diagnostics.tools.length > 0 && (
                            <Descriptions.Item label="工具调用">
                              {msg.diagnostics.tools.slice(0, 5).map((t: any, i: number) => (
                                <Tag key={i} color={t.status === 'success' ? 'blue' : 'red'} style={{ fontSize: 10, marginBottom: 2 }}>
                                  {t.name} ({t.duration_ms}ms)
                                </Tag>
                              ))}
                              {msg.diagnostics.tools.length > 5 && (
                                <span style={{ fontSize: 10, color: '#999' }}>...共 {msg.diagnostics.tools.length} 个工具</span>
                              )}
                            </Descriptions.Item>
                          )}
                          {msg.diagnostics.errors && msg.diagnostics.errors.length > 0 && (
                            <Descriptions.Item label="错误">
                              {msg.diagnostics.errors.map((e: any, i: number) => (
                                <div key={i} style={{ fontSize: 10, color: '#ff4d4f', marginBottom: 2 }}>
                                  [{e.stage}] {e.message}
                                </div>
                              ))}
                            </Descriptions.Item>
                          )}
                        </Descriptions>
                      ),
                    },
                  ]}
                />
              )}
            </div>
          )
        })}

        {/* 已移除旧的 loading 指示器，流式状态直接在消息气泡中显示 */}
      </div>

      {/* 输入区 */}
      <div style={{ padding: '10px 12px', borderTop: '1px solid #eef2f7', background: '#fff' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, background: '#f1f5f9', borderRadius: 12, padding: '4px 4px 4px 12px', border: '1px solid #e2e8f0' }}>
          <Input
            value={inputValue}
            onChange={e => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={'输入问题，如"今天有什么需要关注的？"'}
            variant="borderless"
            style={{ flex: 1, background: 'transparent' }}
            disabled={loading}
          />
          {loading && onStop ? (
            <Button
              shape="circle"
              size="small"
              icon={<PauseCircleOutlined />}
              onClick={onStop}
              danger
              title="停止生成"
            />
          ) : (
            <Button
              type="primary"
              shape="circle"
              size="small"
              icon={<SendOutlined />}
              onClick={handleSend}
              disabled={!inputValue.trim() || loading}
              style={{ background: 'linear-gradient(135deg, #3b82f6 0%, #6366f1 100%)', border: 'none' }}
            />
          )}
        </div>
        {messages.length > 0 && !loading && (
          <div style={{ display: 'flex', justifyContent: 'center', marginTop: 6 }}>
            <Button
              type="text"
              size="small"
              icon={<ClearOutlined />}
              onClick={onClear}
              style={{ fontSize: 11, color: '#94a3b8', height: 24, padding: '0 8px' }}
            >
              清空对话
            </Button>
          </div>
        )}
      </div>

      {/* 光标闪烁动画 */}
      <style>{`
        @keyframes blink {
          0%, 50% { opacity: 1; }
          51%, 100% { opacity: 0; }
        }
      `}</style>
    </div>
  )
}

export default ChatPanel
