import api from './api'

export interface AgentInfo {
  id: number
  agent_no: string
  user_id: number
  username: string
  display_name: string
  status: 'active' | 'disabled'
  parent_agent_id?: number | null
  config_version: number
  created_at?: string
  children_count?: number
}

export interface AgentCapability {
  code: string
  name: string
  category: string
  description?: string
  read_only?: boolean
  effective?: boolean
  role_owned?: boolean
  granted?: boolean
  disabled?: boolean
  grantable_now?: boolean
  grantable?: boolean
  structural?: boolean
}

export interface AgentPolicy {
  granted: string[]
  disabled: string[]
}

export interface AgentCallParty {
  agent_id?: number
  name?: string
  username?: string
  user_id?: number
}

export interface AgentCall {
  id: number
  trace_id: string
  caller: AgentCallParty
  callee: AgentCallParty
  direction: 'outgoing' | 'incoming'
  capability: string
  instruction_summary?: string | null
  status: string
  result_summary?: string | null
  error?: string | null
  duration_ms?: number | null
  depth: number
  created_at?: string | null
}

export interface TeamMember extends AgentInfo {
  name: string
  capabilities: Array<{ code: string; name: string }>
}

export const agentApi = {
  me: () => api.get('/agents/me', { skipErrorToast: true }) as any,
  calls: (limit = 20) => api.get('/agents/me/calls', { params: { limit }, skipErrorToast: true }) as any,
  conversations: (params: Record<string, any> = {}, skipErrorToast = false) =>
    api.get('/agents/me/conversations', { params, skipErrorToast }) as any,
  conversation: (id: number) => api.get(`/agents/me/conversations/${id}`) as any,
  archiveConversation: (id: number) => api.post(`/agents/me/conversations/${id}/archive`) as any,
  team: () => api.get('/agents/me/team') as any,
  addMember: (data: { user_id?: number; username?: string }) => api.post('/agents/me/team', data) as any,
  removeMember: (agentId: number) => api.delete(`/agents/me/team/${agentId}`) as any,
  candidates: (keyword = '') => api.get('/agents/me/team/candidates', { params: { keyword } }) as any,
  teamMember: (agentId: number) => api.get(`/agents/me/team/${agentId}`) as any,
  updatePolicy: (agentId: number, data: Record<string, any>) =>
    api.put(`/agents/me/team/${agentId}/policy`, data) as any,
  adminAgents: (params: Record<string, any> = {}) => api.get('/agents/admin/agents', { params }) as any,
  adminAgent: (agentId: number) => api.get(`/agents/admin/agents/${agentId}`) as any,
  adminCalls: (params: Record<string, any> = {}) => api.get('/agents/admin/calls', { params }) as any,
  adminStats: () => api.get('/agents/admin/stats') as any,
  adminHierarchy: (agentId: number, data: Record<string, any>) =>
    api.put(`/agents/admin/agents/${agentId}/hierarchy`, data) as any,
  adminPolicy: (agentId: number, data: Record<string, any>) =>
    api.put(`/agents/admin/agents/${agentId}/policy`, data) as any,
  adminConversation: (id: number, reason: string) =>
    api.get(`/agents/admin/conversations/${id}`, { params: { reason } }) as any,
}
