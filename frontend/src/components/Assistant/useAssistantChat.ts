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
}

export interface AssistantCard {
  type: 'summary' | 'order_list' | 'text'
  title: string
  payload: any
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

    try {
      const res: any = await assistantApi.chat(text.trim(), sessionIdRef.current || undefined)
      const data = res.data
      sessionIdRef.current = data.session_id || ''

      const botMsg: ChatMessage = {
        id: `bot-${Date.now()}`,
        role: 'assistant',
        content: data.text || '',
        cards: data.cards || [],
        suggestions: data.suggestions || [],
        intent: data.intent,
        provider: data.provider,
        timestamp: Date.now(),
      }
      setMessages(prev => [...prev, botMsg])
    } catch (e: any) {
      const errMsg: ChatMessage = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: '抱歉，处理请求时出现错误，请稍后重试。',
        timestamp: Date.now(),
      }
      setMessages(prev => [...prev, errMsg])
    } finally {
      setLoading(false)
    }
  }, [loading])

  const loadSkills = useCallback(async () => {
    try {
      const res: any = await assistantApi.listSkills()
      setSkills(res.data || [])
    } catch { /* ignore */ }
  }, [])

  const clearMessages = useCallback(() => {
    setMessages([])
    sessionIdRef.current = ''
  }, [])

  return { messages, loading, send, skills, loadSkills, clearMessages }
}
