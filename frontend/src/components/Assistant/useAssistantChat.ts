import { useState, useCallback, useRef } from 'react'
import { assistantApi } from '../../services/api'

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
  routing?: RoutingInfo
  // 流式状态
  streaming?: boolean
  thinkingStage?: string
  toolCalls?: ToolCallStatus[]
}

export interface AssistantCard {
  type: 'summary' | 'order_list' | 'text' | 'search_result_list' | 'material_list' | 'production_list' | 'exception_list' | 'basicdata_list' | 'action_list'
  title: string
  payload: any
}

export interface ToolCallStatus {
  name: string
  status: 'running' | 'done' | 'error'
  itemCount?: number
}

export interface RoutingInfo {
  decision: 'local' | 'hub' | 'none'
  capability?: string
  agent_key?: string
  agent_label?: string
  reason?: string
  executed?: boolean
  dispatch_error?: string
}

export interface Skill {
  intent: string
  name: string
  description: string
  keywords: string[]
}

export function useAssistantChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [skills, setSkills] = useState<Skill[]>([])
  const sessionIdRef = useRef<string>('')
  const abortControllerRef = useRef<AbortController | null>(null)

  const send = useCallback(async (text: string) => {
    if (!text.trim() || loading) return

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text.trim(),
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
      toolCalls: [],
    }
    setMessages(prev => [...prev, botMsg])

    try {
      const abortController = new AbortController()
      abortControllerRef.current = abortController

      const conversationHistory = messages.slice(-10)
      const response = await assistantApi.chatStream(
        text.trim(),
        sessionIdRef.current || undefined,
        conversationHistory,
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
        const res: any = await assistantApi.chat(text.trim(), sessionIdRef.current || undefined, conversationHistory)
        const data = res.data
        sessionIdRef.current = data.session_id || ''

        setMessages(prev =>
          prev.map(m =>
            m.id === botMsgId
              ? {
                  ...m,
                  content: data.text || '',
                  cards: data.cards || [],
                  suggestions: data.suggestions || [],
                  intent: data.intent,
                  provider: data.provider,
                  streaming: false,
                  thinkingStage: undefined,
                  traceId: data.trace_id,
                  diagnostics: data.diagnostics,
                  routing: data.routing,
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
  }, [loading, messages])

  const handleSSEEvent = useCallback((msgId: string, event: string, data: any) => {
    setMessages(prev =>
      prev.map(m => {
        if (m.id !== msgId) return m

        switch (event) {
          case 'session':
            sessionIdRef.current = data.session_id || ''
            return m

          case 'routing':
            return { ...m, routing: data, thinkingStage: undefined }

          case 'thinking':
            return { ...m, thinkingStage: data.message || '思考中...' }

          case 'tool_start':
            return {
              ...m,
              thinkingStage: `正在查询: ${data.name}...`,
              toolCalls: [
                ...(m.toolCalls || []),
                { name: data.name, status: 'running' as const },
              ],
            }

          case 'tool_done':
            return {
              ...m,
              thinkingStage: undefined,
              toolCalls: (m.toolCalls || []).map(tc =>
                tc.name === data.name
                  ? { ...tc, status: (data.success ? 'done' : 'error') as 'done' | 'error', itemCount: data.item_count }
                  : tc
              ),
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

          case 'done':
            return {
              ...m,
              streaming: false,
              thinkingStage: undefined,
              provider: data.provider,
              intent: data.intent,
              routing: data.routing ?? m.routing,
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

  const loadSkills = useCallback(async () => {
    try {
      const res: any = await assistantApi.listSkills()
      setSkills(res.data || [])
    } catch { /* ignore */ }
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    sessionIdRef.current = ''
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

  return { messages, loading, send, skills, loadSkills, clearMessages, stopStreaming }
}
