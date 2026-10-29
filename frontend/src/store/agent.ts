import { create } from 'zustand'
import { agentApi } from '../services/agent'

interface AgentState {
  me: any | null
  loaded: boolean
  loading: boolean
  enabled: boolean
  fetchMe: () => Promise<void>
}

export const useAgentStore = create<AgentState>((set, get) => ({
  me: null,
  loaded: false,
  loading: false,
  enabled: true,

  fetchMe: async () => {
    if (get().loading) return
    set({ loading: true })
    try {
      const res: any = await agentApi.me()
      const data = res.data || null
      set({
        me: data,
        loaded: true,
        loading: false,
        enabled: !!data,
      })
    } catch (error: any) {
      const explicitlyDisabled = error?._apiData?.code === 403
      set({
        loaded: true, loading: false, enabled: !explicitlyDisabled,
        me: null,
      })
    }
  },
}))
