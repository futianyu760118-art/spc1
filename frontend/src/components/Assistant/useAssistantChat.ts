import { useState, useCallback, useRef } from 'react'
import { assistantApi } from '../../services/api'
import { agentApi } from '../../services/agent'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  cards?: AssistantCard[]
  suggestions?: string[]
  intent?: string
  provider?: string
  timestamp: number
  traceId?: string
  diagnostics?: any
  steps?: OrchestrationStep[]
  plan?: AssistantPlan
  confirmation?: WriteConfirmation
  // 流式状态
  streaming?: boolean
  thinkingStage?: string
  // 确认请求进行中
  confirming?: boolean
}

export interface AssistantCard {
  type: 'summary' | 'order_list' | 'text' | 'search_result_list' | 'material_list' | 'production_list' | 'exception_list' | 'basicdata_list' | 'action_list'
  title: string
  payload: any
}

export interface AssistantPlan {
  status: 'planning' | 'ready'
  steps: string[]
}

export interface OrchestrationStep {  step_id: number
  tool: string
  agent_label?: string
  capability?: string
  path?: string
  task_type?: string
  order_no?: string
  status: 'running' | 'completed' | 'failed' | 'blocked' | 'pending_confirmation' | 'cancelled'
  summary?: string
  error?: string
  item_count?: number
  duration_ms?: number
}

export interface WriteConfirmationField {
  field: string
  old_value?: string | null
  new_value?: string | null
}

export interface WriteConfirmation {
  confirmation_id: string
  action_type?: string
  order_no?: string
  fields: WriteConfirmationField[]
  preview?: Record<string, any>
  created_at?: string
  expires_at?: string
  status: 'pending' | 'cancelled' | 'executed' | 'failed'
  write_result?: any
  error?: string
}

const CONFIRM_COMMANDS = new Set(['确认', '确认执行', '确定', '确定执行'])
const CANCEL_COMMANDS = new Set(['取消', '取消操作', '不确认'])
const NO_PENDING_CONFIRMATION_REPLY = '当前没有待确认的操作。如需修改订单或执行任务动作，请先发起。'

function parseConfirmationCommand(text: string): 'confirm' | 'cancel' | null {
  const command = text.trim().replace(/[。！!?]+$/g, '')
  if (CONFIRM_COMMANDS.has(command)) return 'confirm'
  if (CANCEL_COMMANDS.has(command)) return 'cancel'
  return null
}

const CHOICE_HEADING_RE = /(下一步|请选择|请选一项|可选项|可选方案|你可以选择|选择一项)/
const NUMBERED_OPTION_RE = /^\s*(\d{1,2})[.、)）]\s*(.+?)\s*$/

export function extractChoiceSuggestions(text: string): string[] {
  const lines = (text || '').split(/\r?\n/)
  let start = -1
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    if (CHOICE_HEADING_RE.test(lines[index])) {

      start = index + 1
      break
    }
  }
  if (start < 0) return []

  const options: string[] = []
  for (let index = start; index < lines.length; index += 1) {
    const line = lines[index].trim()
    if (!line) {
      if (options.length > 0) break
      continue
    }
    const match = line.match(NUMBERED_OPTION_RE)
    if (!match) {
      if (options.length > 0) break
      continue
    }
    const label = match[2].replace(/[。；;]+$/, '').trim()
    if (label) options.push(`${match[1]}. ${label}`)
    if (options.length >= 8) break
  }
  return options.length >= 2 ? options : []
}

function mergeConfirmation(
  current: WriteConfirmation | undefined,
  incoming?: Partial<WriteConfirmation> | null,
): WriteConfirmation | undefined {
  if (!incoming) return current
  return {
    ...(current || {}),
    ...incoming,
    status: incoming.status || current?.status || 'pending',
  } as WriteConfirmation
}

export function useAssistantChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const sessionIdRef = useRef<string>('')
  const conversationIdRef = useRef<number | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  const handleSSEEvent = useCallback((msgId: string, event: string, data: any) => {
    setMessages(prev =>
      prev.map(m => {
        if (m.id !== msgId) return m

        switch (event) {
          case 'session':
            sessionIdRef.current = data.session_id || ''
            if (data.conversation_id) conversationIdRef.current = Number(data.conversation_id)
            return m

          case 'thinking':
            return { ...m, thinkingStage: data.message || '思考中...' }

          case 'plan_started':
            return {
              ...m,
              thinkingStage: '正在规划执行步骤...',
              plan: { status: 'planning', steps: [] },
            }

          case 'plan':
            return {
              ...m,
              thinkingStage: undefined,
              plan: (data.steps || []).length > 0
                ? { status: 'ready', steps: data.steps }
                : undefined,
            }

          case 'step_started':
            return {
              ...m,
              thinkingStage: data.step?.agent_label
                ? `正在调用${data.step.agent_label}...`
                : '正在调用智能体...',
              steps: [...(m.steps || []), data.step],
            }

          case 'step_completed':
            return {
              ...m,
              thinkingStage: undefined,
              steps: (m.steps || []).map(s =>
                s.step_id === data.step?.step_id ? data.step : s
              ),
            }

          case 'confirmation_required':
            return {
              ...m,
              thinkingStage: undefined,
              confirmation: { ...data, status: 'pending' },
            }

          case 'delta':
            return {
              ...m,
              content: m.content + (data.text || ''),
              thinkingStage: undefined,
            }

          case 'cards':
            return {
              ...m,
              cards: [...(m.cards || []), ...(data.cards || [])],
            }

          case 'suggestions':
            return {
              ...m,
              suggestions: data.suggestions || [],
            }

          case 'done': {
            const suggestions = data.suggestions?.length
              ? data.suggestions
              : (m.suggestions?.length ? m.suggestions : extractChoiceSuggestions(m.content))
            return {
              ...m,
              streaming: false,
              thinkingStage: undefined,
              provider: data.provider,
              intent: data.intent,
              steps: data.steps ?? m.steps,
              confirmation: mergeConfirmation(m.confirmation, data.confirmation),
              suggestions,
            }
          }

          case 'error':
            return {
              ...m,
              content: m.content || data.message || '处理请求时出现错误。',
              streaming: false,
              thinkingStage: undefined,
            }

          default:
            return m
        }
      })
    )
  }, [])

  const appendFollowUpReply = useCallback((reply: any) => {
    if (!reply?.text) return
    const followMsg: ChatMessage = {
      id: `bot-${Date.now()}`,
      role: 'assistant',
      content: reply.text,
      cards: reply.cards || [],
      steps: reply.steps || [],
      timestamp: Date.now(),
      provider: reply.provider,
    }
    setMessages(prev => [...prev, followMsg])
  }, [])

  const confirmWrite = useCallback(async (confirmationId: string) => {
    setMessages(prev =>
      prev.map(m =>
        m.confirmation?.confirmation_id === confirmationId
          ? { ...m, confirming: true }
          : m
      )
    )
    try {
      const res: any = await assistantApi.confirmConfirmation(confirmationId)
      const data = res.data
      setMessages(prev =>
        prev.map(m => {
          if (m.confirmation?.confirmation_id !== confirmationId) return m
          return {
            ...m,
            confirming: false,
            confirmation: mergeConfirmation(m.confirmation, data.confirmation),
          }
        })
      )
      appendFollowUpReply(data.reply)
    } catch (e: any) {
      const error = e?._apiData?.message || e?.message || '确认请求失败，请稍后重试'
      setMessages(prev =>
        prev.map(m =>
          m.confirmation?.confirmation_id === confirmationId
            ? {
                ...m,
                confirming: false,
                confirmation: {
                  ...m.confirmation!,
                  status: 'failed',
                  error,
                },
              }
            : m
        )
      )
    }
  }, [appendFollowUpReply])

  const cancelWrite = useCallback(async (confirmationId: string) => {
    try {
      const res: any = await assistantApi.cancelConfirmation(confirmationId)
      const confirmation = res?.data?.confirmation
      setMessages(prev =>
        prev.map(m =>
          m.confirmation?.confirmation_id === confirmationId
            ? {
                ...m,
                confirmation: mergeConfirmation(m.confirmation, confirmation || { status: 'cancelled' }),
              }
            : m
        )
      )
      appendFollowUpReply(res?.data?.reply)
    } catch (e: any) {
      const error = e?._apiData?.message || e?.message || '取消失败，请稍后重试'
      setMessages(prev =>
        prev.map(m =>
          m.confirmation?.confirmation_id === confirmationId
            ? { ...m, confirmation: { ...m.confirmation!, status: 'failed', error } }
            : m
        )
      )
    }
  }, [appendFollowUpReply])

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || loading) return

    const command = parseConfirmationCommand(trimmed)
    if (command) {
      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content: trimmed,
        timestamp: Date.now(),
      }
      setMessages(prev => [...prev, userMsg])

      const pending = [...messages]
        .reverse()
        .find(m => m.confirmation?.status === 'pending')
        ?.confirmation
      if (!pending) {
        setMessages(prev => [...prev, {
          id: `bot-${Date.now()}`,
          role: 'assistant',
          content: NO_PENDING_CONFIRMATION_REPLY,
          timestamp: Date.now(),
        }])
        return
      }

      if (command === 'confirm') {
        await confirmWrite(pending.confirmation_id)
      } else {
        await cancelWrite(pending.confirmation_id)
      }
      return
    }

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: Date.now(),
    }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)

    // 创建一个占位的 assistant 消息用于流式更新
    const botMsgId = `bot-${Date.now()}`
    const botMsg: ChatMessage = {
      id: botMsgId,
      role: 'assistant',
      content: '',
      cards: [],
      suggestions: [],
      timestamp: Date.now(),
      streaming: true,
      thinkingStage: '正在连接...',
      steps: [],
    }
    setMessages(prev => [...prev, botMsg])

    try {
      const abortController = new AbortController()
      abortControllerRef.current = abortController

      const conversationHistory = messages.slice(-10)
      const response = await assistantApi.chatStream(
        trimmed,
        sessionIdRef.current || undefined,
        conversationHistory,
        conversationIdRef.current || undefined,
      )

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })

        // 按双换行分割 SSE 事件
        const events = buffer.split('\n\n')
        buffer = events.pop() || '' // 最后一个可能不完整

        for (const eventBlock of events) {
          if (!eventBlock.trim()) continue

          let eventType = ''
          let eventData = ''

          for (const line of eventBlock.split('\n')) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7)
            } else if (line.startsWith('data: ')) {
              eventData = line.slice(6)
            }
          }

          if (!eventType || !eventData) continue

          try {
            const data = JSON.parse(eventData)
            handleSSEEvent(botMsgId, eventType, data)
          } catch (e) {
            console.warn('SSE parse error:', e, eventData)
          }
        }
      }

      // 流式结束，标记完成
      setMessages(prev =>
        prev.map(m =>
          m.id === botMsgId
            ? { ...m, streaming: false, thinkingStage: undefined }
            : m
        )
      )
    } catch (e: any) {
      if (e.name === 'AbortError') return

      // 流式失败，回退到非流式
      console.warn('SSE failed, falling back to non-stream:', e)
      try {
        const conversationHistory = messages.slice(-10)
        const res: any = await assistantApi.chat(
          trimmed, sessionIdRef.current || undefined, conversationHistory,
          conversationIdRef.current || undefined,
        )
        const data = res.data
        sessionIdRef.current = data.session_id || ''
        if (data.conversation_id) conversationIdRef.current = Number(data.conversation_id)

        setMessages(prev =>
          prev.map(m =>
            m.id === botMsgId
              ? {
                  ...m,
                  content: data.text || '',
                  cards: data.cards || [],
                  suggestions: data.suggestions?.length
                    ? data.suggestions
                    : extractChoiceSuggestions(data.text || ''),
                  intent: data.intent,
                  provider: data.provider,
                  streaming: false,
                  thinkingStage: undefined,
                  traceId: data.trace_id,
                  diagnostics: data.diagnostics,
                  steps: data.steps || [],
                  confirmation: mergeConfirmation(undefined, data.confirmation),
                }
              : m
          )
        )
      } catch (fallbackErr) {
        setMessages(prev =>
          prev.map(m =>
            m.id === botMsgId
              ? {
                  ...m,
                  content: '抱歉，处理请求时出现错误，请稍后重试。',
                  streaming: false,
                  thinkingStage: undefined,
                }
              : m
          )
        )
      }
    } finally {
      setLoading(false)
      abortControllerRef.current = null
    }
  }, [loading, messages, confirmWrite, cancelWrite, handleSSEEvent])

  const loadConversation = useCallback(async (conversationId: number) => {
    const res: any = await agentApi.conversation(conversationId)
    const historyMessages = (res.data?.messages || [])
      .filter((item: any) => item.role === 'user' || item.role === 'assistant')
      .map((item: any, index: number): ChatMessage => {
        const steps: OrchestrationStep[] = Array.isArray(item.tool_calls) && item.tool_calls.length > 0
          ? item.tool_calls.map((step: any, i: number) => ({
              step_id: step.step_id ?? i + 1,
              tool: step.tool,
              agent_label: step.agent_label,
              capability: step.capability,
              path: step.path,
              task_type: step.task_type,
              status: step.status || 'completed',
              summary: step.summary,
              error: step.error,
              duration_ms: step.duration_ms,
            }))
          : []
        const results = item.tool_results && typeof item.tool_results === 'object' ? item.tool_results : {}
        const planSteps = Array.isArray(results.plan)
          ? results.plan.filter((step: unknown): step is string => typeof step === 'string')
          : []
        const plan: AssistantPlan | undefined = planSteps.length > 0
          ? { status: 'ready', steps: planSteps }
          : undefined
        const confirmation: WriteConfirmation | undefined =
          results.confirmation && typeof results.confirmation === 'object'
            ? {
                ...results.confirmation,
                fields: Array.isArray(results.confirmation.fields)
                  ? results.confirmation.fields.filter((f: any) => f && typeof f === 'object')
                  : [],
              }
            : undefined
        return {
          id: `history-${item.id ?? index}`,
          role: item.role === 'user' ? 'user' : 'assistant',
          content: item.content || '',
          timestamp: item.created_at ? new Date(item.created_at).getTime() : Date.now(),
          cards: [],
          suggestions: item.role === 'assistant' ? extractChoiceSuggestions(item.content || '') : [],
          steps: steps.length > 0 ? steps : undefined,
          plan,
          confirmation,
        }
      })
    conversationIdRef.current = conversationId
    sessionIdRef.current = ''
    setMessages(historyMessages)
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    sessionIdRef.current = ''
    conversationIdRef.current = null
    // 取消正在进行的流式请求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
  }, [])

  const stopStreaming = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setLoading(false)
    setMessages(prev =>
      prev.map(m => m.streaming ? { ...m, streaming: false, thinkingStage: undefined } : m)
    )
  }, [])

  return {
    messages, loading, send, clearMessages, stopStreaming,
    confirmWrite, cancelWrite, loadConversation,
  }
}
