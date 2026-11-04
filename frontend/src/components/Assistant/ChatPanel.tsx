import React, { useCallback, useRef, useEffect, useState } from 'react'
import { Alert, Button, Collapse, Descriptions, Tag, Tooltip } from 'antd'
import {
  AppstoreOutlined, BugOutlined, CheckOutlined, CloseOutlined, EditOutlined,
  LoadingOutlined, RobotOutlined, SwapRightOutlined, UnorderedListOutlined, WarningOutlined,
} from '@ant-design/icons'
import Markdown from '../Markdown'
import { AssistantPlan, ChatMessage, OrchestrationStep, WriteConfirmation } from './useAssistantChat'
import { scalePx } from '../../utils/fontSize'
import { stripDsmlMarkup } from '../../utils/dsml'
import ClarificationCard from './ClarificationCard'
import { parseClarification, stripClarificationBlock } from './clarification'
import ChatComposer from './ChatComposer'
import { TeamAgent } from './types'

const formatTimestamp = (timestamp: number) => {
  const date = new Date(timestamp)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (minutes < 1440) return `${Math.floor(minutes / 60)} 小时前`
  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

const getProviderLabel = (provider?: string) => {
  if (!provider || provider === 'rule_based') return null
  const labels: Record<string, string> = {
    openai: 'AI',
    dashscope: '通义千问',
  }
  return labels[provider] || provider
}

const SCENES = [
  {
    icon: <WarningOutlined />,
    title: '查交付风险',
    hint: '哪些订单快延期了？',
    prompt: '今天有哪些订单存在交付风险？',
  },
  {
    icon: <AppstoreOutlined />,
    title: '看物料齐套',
    hint: '齐套率与缺料',
    prompt: '当前齐套率怎么样？缺哪些料？',
  },
  {
    icon: <BugOutlined />,
    title: '分析异常',
    hint: '异常池与品质问题',
    prompt: '帮我分析当前未闭环的异常。',
  },
  {
    icon: <EditOutlined />,
    title: '修改交期',
    hint: '确认后写回订单',
    prompt: '帮我修改订单的交期。',
  },
]

const STEP_STATUS_META: Record<string, { cls: string; text: string }> = {
  running: { cls: 'running', text: '执行中' },
  completed: { cls: 'done', text: '完成' },
  failed: { cls: 'failed', text: '失败' },
  blocked: { cls: 'blocked', text: '已拦截' },
  pending_confirmation: { cls: 'pending', text: '待确认' },
  cancelled: { cls: 'muted', text: '已取消' },
}

interface Props {
  messages: ChatMessage[]
  loading: boolean
  teamAgents: TeamAgent[]
  onSend: (text: string) => void
  onStop?: () => void
  onConfirm?: (confirmationId: string) => void
  onCancelConfirmation?: (confirmationId: string) => void
}

const StepTimeline: React.FC<{ steps: OrchestrationStep[] }> = ({ steps }) => {
  if (!steps || steps.length === 0) return null

  return (
    <div className="ai-steps">
      {steps.map(step => {
        const meta = STEP_STATUS_META[step.status] || { cls: 'muted', text: step.status }
        const label = step.agent_label || (step.tool?.startsWith('call_') ? '' : step.tool)
        const node = (
          <div className="ai-step">
            <span className={`ai-step-dot ${meta.cls}`} />
            {label && <span className="ai-step-label">{label}</span>}
            {step.summary && <span>{step.summary}</span>}
            <span className={`ai-step-state ${meta.cls}`}>{meta.text}</span>
            {step.duration_ms != null && <span className="ai-step-time">{Math.round(step.duration_ms)}ms</span>}
          </div>
        )
        return step.error ? (
          <Tooltip key={step.step_id} title={step.error} placement="top">
            {node}
          </Tooltip>
        ) : (
          <React.Fragment key={step.step_id}>{node}</React.Fragment>
        )
      })}
    </div>
  )
}

const PlanCard: React.FC<{ plan: AssistantPlan }> = ({ plan }) => (
  <div className="ai-plan">
    <div className="ai-plan-title">
      {plan.status === 'planning'
        ? <LoadingOutlined spin style={{ fontSize: scalePx(12) }} />
        : <UnorderedListOutlined style={{ fontSize: scalePx(12) }} />}
      执行计划
      {plan.status === 'ready' && <span className="ai-muted">· {plan.steps.length} 步</span>}
      {plan.status === 'planning' && <span className="ai-muted">正在规划…</span>}
    </div>
    {plan.status === 'ready' && (
      <ol className="ai-plan-list">
        {plan.steps.map((step, index) => <li key={index}>{step}</li>)}
      </ol>
    )}
  </div>
)

const WRITE_FIELD_LABELS: Record<string, string> = {
  promised_date: '合同交期',
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
  const isOrder = !confirmation.action_type || confirmation.action_type === 'order_update'
  const preview = confirmation.preview || {}
  const previewRows: Array<[string, any]> = [
    ['接收人', preview.assignee_name],
    ['任务标题', preview.task_title],
    ['截止时间', preview.due_at],
    ['优先级', preview.priority],
    ['业务对象', preview.biz_title],
    ['新接收人', preview.new_assignee_name],
    ['成员', preview.target_name || preview.agent_name],
    ['原因', preview.reason],
    ['汇报摘要', preview.summary],
    ['授予能力', Array.isArray(preview.granted) ? preview.granted.join(', ') : preview.granted],
    ['禁用能力', Array.isArray(preview.disabled) ? preview.disabled.join(', ') : preview.disabled],
  ].filter(([, value]) => value !== undefined && value !== null && value !== '') as Array<[string, any]>

  return (
    <div className="ai-confirm">
      <div className="ai-confirm-title">
        {isOrder ? `写操作确认 — 订单 ${confirmation.order_no}` : `操作确认 — ${preview.title || confirmation.action_type}`}
        <span>（服务端将再次校验权限与状态）</span>
      </div>
      {isOrder ? confirmation.fields.map(field => (
        <div key={field.field} className="ai-confirm-row">
          <span className="ai-confirm-label">{WRITE_FIELD_LABELS[field.field] || field.field}</span>
          <code className="ai-confirm-old">{field.old_value ?? '（空）'}</code>
          <SwapRightOutlined style={{ fontSize: scalePx(10), color: '#b45309' }} />
          <code className="ai-confirm-new">{field.new_value ?? '（空）'}</code>
        </div>
      )) : previewRows.map(([label, value]) => (
        <div key={label} className="ai-confirm-row">
          <span className="ai-confirm-label">{label}</span>
          <span style={{ wordBreak: 'break-all' }}>{String(value)}</span>
        </div>
      ))}

      {pending && (
        <div className="ai-confirm-actions">
          <Button
            type="primary"
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
        </div>
      )}
      {confirmation.status === 'executed' && (
        <Alert
          type="success"
          showIcon
          style={{ marginTop: 8, fontSize: scalePx(12) }}
          message={confirmation.write_result?.updated_at
            ? `已执行（更新于 ${confirmation.write_result.updated_at}）`
            : '已执行'}
        />
      )}
      {confirmation.status === 'failed' && (
        <Alert
          type="error"
          showIcon
          style={{ marginTop: 8, fontSize: scalePx(12) }}
          message={confirmation.error || '写操作执行失败，请重新发起'}
        />
      )}
      {confirmation.status === 'cancelled' && (
        <div className="ai-muted" style={{ marginTop: 8 }}>已取消，未产生任何变更</div>
      )}
    </div>
  )
}

const ChatPanel: React.FC<Props> = ({ messages, loading, teamAgents, onSend, onStop, onConfirm, onCancelConfirmation }) => {
  const [inputValue, setInputValue] = useState('')
  const inputRef = useRef<any>(null)
  const shouldAutoScrollRef = useRef(true)
  const listRef = useRef<HTMLDivElement>(null)
  const previousFirstMessageIdRef = useRef<number | string | null>(null)

  const scrollToBottom = useCallback(() => {
    const scroll = () => {
      const list = listRef.current
      if (list) list.scrollTop = list.scrollHeight
    }
    requestAnimationFrame(() => {
      scroll()
      requestAnimationFrame(scroll)
    })
  }, [])

  useEffect(() => {
    const firstMessageId = messages[0]?.id ?? null
    const conversationChanged = firstMessageId !== previousFirstMessageIdRef.current
    previousFirstMessageIdRef.current = firstMessageId
    const lastMessage = messages[messages.length - 1]

    // 发送新消息、切换会话时强制回到底部；其余消息更新只在用户原本接近底部时跟随
    if (conversationChanged || lastMessage?.role === 'user' || shouldAutoScrollRef.current) {
      shouldAutoScrollRef.current = true
      scrollToBottom()
    }
  }, [messages, loading, scrollToBottom])

  useEffect(() => {
    const list = listRef.current
    if (!list || typeof ResizeObserver === 'undefined') return
    const stream = list.firstElementChild
    if (!stream) return
    const observer = new ResizeObserver(() => {
      if (shouldAutoScrollRef.current) {
        list.scrollTop = list.scrollHeight
      }
    })
    observer.observe(stream)
    return () => observer.disconnect()
  }, [])

  const handleScroll = () => {
    const list = listRef.current
    if (!list) return
    const distanceToBottom = list.scrollHeight - list.scrollTop - list.clientHeight
    shouldAutoScrollRef.current = distanceToBottom < 40
  }

  const sendMessage = (text: string) => {
    shouldAutoScrollRef.current = true
    scrollToBottom()
    onSend(text)
  }

  const handleSend = () => {
    if (inputValue.trim()) {
      sendMessage(inputValue)
      setInputValue('')
    }
  }

  const fillInput = (text: string) => {
    setInputValue(text)
    inputRef.current?.focus()
  }

  const hasPendingConfirmation = messages.some(message => message.confirmation?.status === 'pending')
  const placeholder = hasPendingConfirmation
    ? '请先点击上方确认卡片中的「确认执行」或「取消」'
    : '输入问题，如“今天有什么需要关注的？”'

  return (
    <div className="ai-chat-panel">
      <div className="ai-chat-body" ref={listRef} onScroll={handleScroll}>
        <div className="ai-chat-stream">
          {messages.length === 0 && (
            <div className="ai-chat-empty">
              <div className="ai-chat-empty-mark"><RobotOutlined /></div>
              <div className="ai-chat-empty-title">今天想让助手做什么？</div>
              <div className="ai-chat-empty-sub">查订单、看齐套、分析异常，或直接让我执行修改</div>

              <div className="ai-scene-grid">
                {SCENES.map(scene => (
                  <button
                    key={scene.title}
                    type="button"
                    className="ai-scene-card"
                    onClick={() => fillInput(scene.prompt)}
                  >
                    <span className="ai-scene-icon">{scene.icon}</span>
                    <span>
                      <span className="ai-scene-title">{scene.title}</span>
                      <span className="ai-scene-hint">{scene.hint}</span>
                    </span>
                  </button>
                ))}
              </div>

              {teamAgents.length > 0 && (
                <div className="ai-team-chips">
                  {teamAgents.map(agent => (
                    <button
                      key={agent.id}
                      type="button"
                      className="ai-team-chip"
                      title={(agent.capabilities || []).map(capability => capability.name).join('、')}
                      onClick={() => fillInput(`请用「${agent.name}」`)}
                    >
                      {agent.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {messages.map(message => {
            const providerLabel = getProviderLabel(message.provider)
            const clarification = message.role === 'assistant' ? parseClarification(message.content) : null
            const displayContent = message.role === 'assistant'
              ? stripClarificationBlock(stripDsmlMarkup(message.content))
              : message.content

            if (message.role === 'user') {
              return (
                <div key={message.id} className="ai-msg user">
                  <div className="ai-bubble-user">{message.content}</div>
                </div>
              )
            }

            return (
              <div key={message.id} className="ai-msg assistant">
                <div className="ai-msg-avatar">AI</div>
                <div className="ai-msg-main">
                  {message.streaming && message.thinkingStage && !displayContent && (
                    <div className="ai-thinking">
                      <LoadingOutlined spin style={{ fontSize: scalePx(12) }} />
                      <span>{message.thinkingStage}</span>
                    </div>
                  )}

                  {displayContent ? (
                    <>
                      <Markdown>{displayContent}</Markdown>
                      {message.streaming && <span className="ai-stream-cursor" />}
                    </>
                  ) : message.content && !clarification && !message.streaming ? (
                    <span className="ai-muted">工具调用未执行，请重试</span>
                  ) : null}

                  {clarification && (
                    <div className="ai-clarification">
                      <ClarificationCard spec={clarification} onSubmit={sendMessage} />
                    </div>
                  )}

                  {message.plan && <PlanCard plan={message.plan} />}
                  {message.steps && message.steps.length > 0 && <StepTimeline steps={message.steps} />}

                  {message.confirmation && (
                    <ConfirmationCard
                      confirmation={message.confirmation}
                      confirming={message.confirming || false}
                      onConfirm={onConfirm}
                      onCancel={onCancelConfirmation}
                    />
                  )}

                  {!clarification && message.suggestions && message.suggestions.length > 0 && (
                    <div className="ai-suggestions">
                      {message.suggestions.map((suggestion, index) => (
                        <button
                          key={index}
                          type="button"
                          className="ai-suggestion"
                          onClick={() => sendMessage(suggestion)}
                        >
                          {suggestion}
                        </button>
                      ))}
                    </div>
                  )}

                  {message.diagnostics && (
                    <Collapse
                      ghost
                      size="small"
                      className="ai-diagnostic"
                      items={[
                        {
                          key: 'diagnostics',
                          label: (
                            <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: scalePx(11) }}>
                              <BugOutlined style={{ fontSize: scalePx(10) }} />
                              诊断信息
                            </span>
                          ),
                          children: (
                            <Descriptions size="small" column={1} bordered style={{ fontSize: scalePx(11) }}>
                              {message.diagnostics.trace_id && (
                                <Descriptions.Item label="Trace ID">
                                  <code style={{ fontSize: scalePx(10) }}>{message.diagnostics.trace_id}</code>
                                </Descriptions.Item>
                              )}
                              {message.diagnostics.total_duration_ms && (
                                <Descriptions.Item label="总耗时">{message.diagnostics.total_duration_ms} ms</Descriptions.Item>
                              )}
                              {message.diagnostics.provider && (
                                <Descriptions.Item label="Provider">{message.diagnostics.provider}</Descriptions.Item>
                              )}
                              {message.diagnostics.path && (
                                <Descriptions.Item label="执行路径">{message.diagnostics.path}</Descriptions.Item>
                              )}
                              {message.diagnostics.fallback && (
                                <Descriptions.Item label="降级"><Tag color="orange" style={{ fontSize: scalePx(10) }}>是</Tag></Descriptions.Item>
                              )}
                              {message.diagnostics.skills && message.diagnostics.skills.length > 0 && (
                                <Descriptions.Item label="技能调用">
                                  {message.diagnostics.skills.map((skill: any, index: number) => (
                                    <Tag key={index} color={skill.status === 'success' ? 'green' : 'red'} style={{ fontSize: scalePx(10), marginBottom: 2 }}>
                                      {skill.name} ({skill.attempts}次, {skill.duration_ms}ms)
                                    </Tag>
                                  ))}
                                </Descriptions.Item>
                              )}
                              {message.diagnostics.tools && message.diagnostics.tools.length > 0 && (
                                <Descriptions.Item label="工具调用">
                                  {message.diagnostics.tools.slice(0, 5).map((tool: any, index: number) => (
                                    <Tag key={index} color={tool.status === 'success' ? 'blue' : 'red'} style={{ fontSize: scalePx(10), marginBottom: 2 }}>
                                      {tool.name} ({tool.duration_ms}ms)
                                    </Tag>
                                  ))}
                                  {message.diagnostics.tools.length > 5 && (
                                    <span style={{ fontSize: scalePx(10), color: '#999' }}>...共 {message.diagnostics.tools.length} 个工具</span>
                                  )}
                                </Descriptions.Item>
                              )}
                              {message.diagnostics.errors && message.diagnostics.errors.length > 0 && (
                                <Descriptions.Item label="错误">
                                  {message.diagnostics.errors.map((error: any, index: number) => (
                                    <div key={index} style={{ fontSize: scalePx(10), color: '#ff4d4f', marginBottom: 2 }}>
                                      [{error.stage}] {error.message}
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

                  {!message.streaming && (
                    <div className="ai-msg-meta">
                      <span>{formatTimestamp(message.timestamp)}</span>
                      {providerLabel && <span className="sc-tag sc-tag-plain">{providerLabel}</span>}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      <ChatComposer
        value={inputValue}
        onChange={setInputValue}
        onSend={handleSend}
        loading={loading}
        onStop={onStop}
        placeholder={placeholder}
        inputRef={inputRef}
      />
    </div>
  )
}

export default ChatPanel
