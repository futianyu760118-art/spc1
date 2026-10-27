import { create } from 'zustand'
import { agentApi } from '../services/agent'

interface AgentState {
  me: any | null
  loaded: boolean
  loading: boolean
  enabled: boolean
  isSupervisor: boolean
  openTasks: number
  fetchMe: () => Promise<void>
  refreshTaskSummary: () => Promise<void>
}

export const useAgentStore = create<AgentState>((set, get) => ({
  me: null,
  loaded: false,
  loading: false,
  enabled: true,
  isSupervisor: false,
  openTasks: 0,

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
        isSupervisor: !!data?.is_supervisor,
        openTasks: Number(data?.task_summary?.open || 0),
      })
    } catch (error: any) {
      const explicitlyDisabled = error?._apiData?.code === 403
      set({
        loaded: true, loading: false, enabled: !explicitlyDisabled,
        me: null, isSupervisor: false, openTasks: 0,
      })
    }
  },

  refreshTaskSummary: async () => {
    try {
      const res: any = await agentApi.myTasksSummary()
      set({ openTasks: Number(res.data?.open || 0) })
    } catch {
      set({ openTasks: 0 })
    }
  },
}))
