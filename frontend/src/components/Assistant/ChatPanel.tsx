import React, { useRef, useEffect, useState } from 'react'
import { Input, Button, Space, Tag, Typography, Collapse, Descriptions, Tooltip, Alert } from 'antd'
import { SendOutlined, ClearOutlined, ThunderboltOutlined, RobotOutlined, BugOutlined, LoadingOutlined, PauseCircleOutlined, CheckOutlined, CloseOutlined, SwapRightOutlined } from '@ant-design/icons'
import Markdown from '../Markdown'
import { ChatMessage, Skill, OrchestrationStep, WriteConfirmation } from './useAssistantChat'

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
  onConfirm?: (confirmationId: string) => void
  onCancelConfirmation?: (confirmationId: string) => void
}
// 编排步骤时间线：查询/推理/订单智能体，每步状态与耗时
const STEP_STATUS_META: Record<string, { color: string; text: string }> = {
  running: { color: 'processing', text: '执行中' },
  completed: { color: 'success', text: '完成' },
  failed: { color: 'error', text: '失败' },
  blocked: { color: 'warning', text: '已拦截' },
  pending_confirmation: { color: 'gold', text: '待确认' },
}

const StepTimeline: React.FC<{ steps: OrchestrationStep[] }> = ({ steps }) => {
  if (!steps || steps.length === 0) return null

  return (
    <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 2 }}>
      {steps.map((s, i) => {
        const meta = STEP_STATUS_META[s.status] || { color: 'default', text: s.status }
        const node = (
          <div key={s.step_id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: '#64748b', flexWrap: 'wrap' }}>
            <span
              style={{
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                minWidth: 16, height: 16, borderRadius: 8, fontSize: 10,
                background: s.status === 'failed' ? '#fee2e2' : s.status === 'completed' ? '#dcfce7' : '#e2e8f0',
                color: s.status === 'failed' ? '#b91c1c' : s.status === 'completed' ? '#15803d' : '#475569',
                fontWeight: 600,
              }}
            >
              {i + 1}
            </span>
            <span style={{ fontWeight: 600, color: '#334155' }}>{s.agent_label || s.tool}</span>
            {s.summary && <span>{s.summary}</span>}
            <Tag color={meta.color} style={{ fontSize: 10, lineHeight: '16px', margin: 0 }}>
              {meta.text}
            </Tag>
            {s.duration_ms != null && <span>{Math.round(s.duration_ms)}ms</span>}
          </div>
        )
        return s.error ? (
          <Tooltip key={s.step_id} title={s.error} placement="top">
            {node}
          </Tooltip>
        ) : (
          node
        )
      })}
    </div>
  )
}

// 写操作确认卡片：订单号、字段、旧值 → 新值、确认 / 取消
const WRITE_FIELD_LABELS: Record<string, string> = {
  shipping_plan: '出货计划',
  delivery_completed_date: '发货完成时间',
  customer_inspection_date: '客户验货时间',
  planned_start_date: '上线时间',
}

const ConfirmationCard: React.FC<{
  confirmation: WriteConfirmation
  confirming: boolean
  onConfirm?: (id: string) => void
  onCancel?: (id: string) => void
}> = ({ confirmation, confirming, onConfirm, onCancel }) => {
  const pending = confirmation.status === 'pending'

  return (
    <div
      style={{
        marginTop: 8,
        maxWidth: '95%',
        border: '1px solid #fde68a',
        background: '#fffbeb',
        borderRadius: 10,
        padding: '10px 12px',
        fontSize: 12,
      }}
    >
      <div style={{ fontWeight: 600, color: '#92400e', marginBottom: 6 }}>
        写操作确认 — 订单 {confirmation.order_no}
        <span style={{ marginLeft: 6, fontWeight: 400, color: '#b45309', fontSize: 11 }}>（不可撤销）</span>
      </div>
      {confirmation.fields.map(f => (
        <div key={f.field} style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 3, color: '#78350f', flexWrap: 'wrap' }}>
          <span style={{ minWidth: 84, fontWeight: 500 }}>{WRITE_FIELD_LABELS[f.field] || f.field}</span>
          <code style={{ background: '#fef3c7', padding: '1px 6px', borderRadius: 4, fontSize: 11 }}>
            {f.old_value ?? '（空）'}
          </code>
          <SwapRightOutlined style={{ fontSize: 10, color: '#b45309' }} />
          <code style={{ background: '#fde68a', padding: '1px 6px', borderRadius: 4, fontSize: 11, fontWeight: 600 }}>
            {f.new_value ?? '（空）'}
          </code>
        </div>
      ))}

      {pending && (
        <Space size={8} style={{ marginTop: 8 }}>
          <Button
            type="primary"
            danger
            size="small"
            icon={<CheckOutlined />}
            loading={confirming}
            onClick={() => onConfirm?.(confirmation.confirmation_id)}
          >
            确认执行
          </Button>
          <Button size="small" icon={<CloseOutlined />} onClick={() => onCancel?.(confirmation.confirmation_id)}>
            取消
          </Button>
        </Space>
      )}
      {confirmation.status === 'executed' && (
        <Alert
          type="success"
          showIcon
          style={{ marginTop: 6, fontSize: 12 }}
          message={
            confirmation.write_result?.updated_at
              ? `已执行（更新于 ${confirmation.write_result.updated_at}）`
              : '已执行'
          }
        />
      )}
      {confirmation.status === 'failed' && (
        <Alert
          type="error"
          showIcon
          style={{ marginTop: 6, fontSize: 12 }}
          message={confirmation.error || '写操作执行失败，请重新发起'}
        />
      )}
      {confirmation.status === 'cancelled' && (
        <div style={{ marginTop: 6, color: '#94a3b8' }}>已取消，未产生任何写入</div>
      )}
    </div>
  )
}

const ChatPanel: React.FC<Props> = ({ messages, loading, skills, onSend, onClear, onStop, onConfirm, onCancelConfirmation }) => {
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

  const hasPendingConfirmation = messages.some(m => m.confirmation?.status === 'pending')

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

              {/* 编排步骤时间线 */}
              {msg.steps && msg.steps.length > 0 && (
                <div style={{ maxWidth: '88%' }}>
                  <StepTimeline steps={msg.steps} />
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

              {/* 写操作确认卡片 */}
              {msg.confirmation && (
                <div style={{ maxWidth: '88%' }}>
                  <ConfirmationCard
                    confirmation={msg.confirmation}
                    confirming={msg.confirming || false}
                    onConfirm={onConfirm}
                    onCancel={onCancelConfirmation}
                  />
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
            placeholder={hasPendingConfirmation
              ? '请点击上方确认卡片中的「确认执行」或「取消」'
              : '输入问题，如"今天有什么需要关注的？"'}
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
