import api from './api'

export interface AgentCapabilityItem {
  code: string
  name: string
}

export interface AgentInfo {
  id: number
  agent_no: string
  name: string
  capabilities: AgentCapabilityItem[]
  scope_type?: 'all' | 'roles'
  scope_role_ids?: number[]
  description?: string | null
  status: 'active' | 'disabled'
  created_at?: string
  teams_count?: number
}

export interface AgentCapability {
  code: string
  name: string
  category: string
  description?: string
  read_only?: boolean
  grantable?: boolean
  structural?: boolean
}

export interface AgentCall {
  id: number
  trace_id: string
  callee: { agent_id?: number | null; name?: string | null }
  capability: string
  instruction_summary?: string | null
  status: string
  result_summary?: string | null
  error?: string | null
  duration_ms?: number | null
  created_at?: string | null
}

export interface TeamMember {
  id: number
  agent_no: string
  name: string
  capabilities: AgentCapabilityItem[]
  description?: string | null
  status: 'active' | 'disabled'
  created_at?: string
}

export const agentApi = {
  me: () => api.get('/agents/me', { skipErrorToast: true }) as any,
  calls: (limit = 20) => api.get('/agents/me/calls', { params: { limit }, skipErrorToast: true }) as any,
  conversations: (params: Record<string, any> = {}, skipErrorToast = false) =>
    api.get('/agents/me/conversations', { params, skipErrorToast }) as any,
  conversation: (id: number) => api.get(`/agents/me/conversations/${id}`) as any,
  archiveConversation: (id: number) => api.post(`/agents/me/conversations/${id}/archive`) as any,
  capabilities: () => api.get('/agents/capabilities') as any,
  team: () => api.get('/agents/me/team') as any,
  addMember: (agentId: number) => api.post('/agents/me/team', { agent_id: agentId }) as any,
  removeMember: (agentId: number) => api.delete(`/agents/me/team/${agentId}`) as any,
  candidates: (keyword = '') => api.get('/agents/me/team/candidates', { params: { keyword } }) as any,
  adminAgents: (params: Record<string, any> = {}) => api.get('/agents/admin/agents', { params }) as any,
  createAgent: (data: Record<string, any>) => api.post('/agents/admin/agents', data) as any,
  updateAgent: (agentId: number, data: Record<string, any>) =>
    api.put(`/agents/admin/agents/${agentId}`, data) as any,
  adminCalls: (params: Record<string, any> = {}) => api.get('/agents/admin/calls', { params }) as any,
  adminStats: () => api.get('/agents/admin/stats') as any,
  adminConversation: (id: number, reason: string) =>
    api.get(`/agents/admin/conversations/${id}`, { params: { reason } }) as any,
  assistantStats: (params: Record<string, any> = {}) => api.get('/agents/admin/assistant/stats', { params }) as any,
  assistantRuns: (params: Record<string, any> = {}) => api.get('/agents/admin/assistant/runs', { params }) as any,
  assistantConfig: () => api.get('/agents/admin/assistant/config') as any,
  saveAssistantConfig: (data: { config: Record<string, any> }) =>
    api.put('/agents/admin/assistant/config', data) as any,
}
