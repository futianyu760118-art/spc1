import React, { useRef, useEffect, useState } from 'react'
import { Input, Button, Space, Tag, Typography, Collapse, Descriptions } from 'antd'
import { SendOutlined, ClearOutlined, ThunderboltOutlined, RobotOutlined, BugOutlined, LoadingOutlined, PauseCircleOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
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
        onScroll={handleScroll}
        style={{
          flex: 1,
          overflow: 'auto',
          padding: '12px 16px',
        }}
      >
        {messages.length === 0 && (
          <div style={{ textAlign: 'center', padding: '40px 0', color: '#999' }}>
            <div style={{ fontSize: 36, marginBottom: 12 }}>🤖</div>
            <div>您好！我是AI智能助手</div>
            <div style={{ fontSize: 12, marginTop: 4, color: '#bbb' }}>
              不仅能查询数据，还能给出行动建议
            </div>
            <div style={{ marginTop: 12 }}>
              <Space wrap size={[6, 6]}>
                <Tag color="blue" style={{ cursor: 'pointer' }} onClick={() => onSend('今天有什么需要关注的？')}>
                  📋 今日简报
                </Tag>
                <Tag color="blue" style={{ cursor: 'pointer' }} onClick={() => onSend('有哪些逾期订单？')}>
                  ⚠️ 逾期订单
                </Tag>
                <Tag color="blue" style={{ cursor: 'pointer' }} onClick={() => onSend('采购有什么风险？')}>
                  🔔 采购预警
                </Tag>
              </Space>
            </div>
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
                  maxWidth: '85%',
                  padding: '8px 12px',
                  borderRadius: msg.role === 'user' ? '12px 12px 2px 12px' : '12px 12px 12px 2px',
                  background: msg.role === 'user' ? '#1890ff' : '#f5f5f5',
                  color: msg.role === 'user' ? '#fff' : '#333',
                  fontSize: 13,
                  lineHeight: 1.6,
                  wordBreak: 'break-word',
                  minHeight: msg.streaming && !msg.content ? 32 : undefined,
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
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      p: ({ children }: { children?: React.ReactNode }) => <p style={{ margin: '6px 0' }}>{children}</p>,
                      ul: ({ children }: { children?: React.ReactNode }) => <ul style={{ margin: '6px 0', paddingLeft: '18px' }}>{children}</ul>,
                      ol: ({ children }: { children?: React.ReactNode }) => <ol style={{ margin: '6px 0', paddingLeft: '18px' }}>{children}</ol>,
                      li: ({ children }: { children?: React.ReactNode }) => <li style={{ margin: '3px 0', lineHeight: 1.6 }}>{children}</li>,
                      strong: ({ children }: { children?: React.ReactNode }) => <strong style={{ color: '#1a1a1a' }}>{children}</strong>,
                      em: ({ children }: { children?: React.ReactNode }) => <em>{children}</em>,
                      h1: ({ children }: { children?: React.ReactNode }) => <h4 style={{ margin: '10px 0 6px', fontSize: 14, fontWeight: 600 }}>{children}</h4>,
                      h2: ({ children }: { children?: React.ReactNode }) => <h5 style={{ margin: '8px 0 4px', fontSize: 13, fontWeight: 600 }}>{children}</h5>,
                      h3: ({ children }: { children?: React.ReactNode }) => <h6 style={{ margin: '6px 0 4px', fontSize: 13, fontWeight: 600 }}>{children}</h6>,
                      hr: () => <hr style={{ border: 'none', borderTop: '1px solid #e8e8e8', margin: '8px 0' }} />,
                      table: ({ children }: { children?: React.ReactNode }) => (
                        <div style={{ overflowX: 'auto', margin: '8px 0' }}>
                          <table style={{ borderCollapse: 'collapse', fontSize: 12, width: '100%', minWidth: 280 }}>
                            {children}
                          </table>
                        </div>
                      ),
                      thead: ({ children }: { children?: React.ReactNode }) => (
                        <thead style={{ background: '#fafafa' }}>{children}</thead>
                      ),
                      th: ({ children }: { children?: React.ReactNode }) => (
                        <th style={{ border: '1px solid #e8e8e8', padding: '4px 8px', fontWeight: 600, textAlign: 'left', whiteSpace: 'nowrap' }}>
                          {children}
                        </th>
                      ),
                      td: ({ children }: { children?: React.ReactNode }) => (
                        <td style={{ border: '1px solid #e8e8e8', padding: '4px 8px', whiteSpace: 'nowrap' }}>
                          {children}
                        </td>
                      ),
                      code: ({ children, className }: { children?: React.ReactNode; className?: string }) => {
                        // 区分行内代码和代码块
                        const isBlock = className?.startsWith('language-')
                        if (isBlock) {
                          return (
                            <pre style={{ background: '#f6f6f6', padding: '8px 12px', borderRadius: 4, overflow: 'auto', fontSize: 11, margin: '6px 0' }}>
                              <code>{children}</code>
                            </pre>
                          )
                        }
                        return (
                          <code style={{ background: 'rgba(150, 150, 150, 0.15)', padding: '1px 4px', borderRadius: 3, fontSize: 12 }}>
                            {children}
                          </code>
                        )
                      },
                      blockquote: ({ children }: { children?: React.ReactNode }) => (
                        <blockquote style={{ borderLeft: '3px solid #1890ff', margin: '6px 0', paddingLeft: 10, color: '#555' }}>
                          {children}
                        </blockquote>
                      ),
                    }}
                  >
                    {msg.content}
                  </ReactMarkdown>
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
                      background: '#1890ff',
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
      <div style={{ padding: '8px 12px', borderTop: '1px solid #f0f0f0', display: 'flex', gap: 8 }}>
        <Input
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={'输入问题，如"今天有什么需要关注的？"'}
          style={{ flex: 1 }}
          disabled={loading}
        />
        {loading && onStop ? (
          <Button
            icon={<PauseCircleOutlined />}
            onClick={onStop}
            danger
            title="停止生成"
          />
        ) : (
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            disabled={!inputValue.trim() || loading}
          />
        )}
        {messages.length > 0 && !loading && (
          <Button
            icon={<ClearOutlined />}
            onClick={onClear}
            title="清空对话"
          />
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
