import api from './api'

export interface AgentCapabilityItem {
  code: string
  name: string
}

export interface AgentSkillBrief {
  id: number
  skill_key?: string | null
  name: string
  description: string
  executor_name?: string | null
  source?: 'builtin' | 'imported'
  status: 'active' | 'disabled'
}

export interface AgentSkillFile {
  path: string
  size: number
  kind: 'skill' | 'script' | 'reference' | 'asset' | 'file'
}

export interface AgentInfo {
  id: number
  agent_no: string
  name: string
  capabilities: AgentCapabilityItem[]
  skills?: AgentSkillBrief[]
  skill_count?: number
  scope_type?: 'all' | 'roles'
  scope_role_ids?: number[]
  description?: string | null
  status: 'active' | 'disabled'
  created_at?: string
  teams_count?: number
}

export interface AgentSkill extends AgentSkillBrief {
  instructions?: string
  files?: AgentSkillFile[]
  file_count?: number
  has_scripts?: boolean
  folder_exists?: boolean
  executor_available?: boolean
  script_execution_available?: boolean
  bound_agents_count?: number
  created_at?: string | null
  updated_at?: string | null
}

export interface SkillExecutor {
  name: string
  display_name: string
  description: string
  parameters: Record<string, any>
  required_capabilities: string[]
  timeout_s: number
  read_only: boolean
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
  skills?: AgentSkillBrief[]
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
  adminSkills: (params: Record<string, any> = {}) => api.get('/agents/admin/skills', { params }) as any,
  adminSkill: (skillId: number) => api.get(`/agents/admin/skills/${skillId}`) as any,
  adminSkillFile: (skillId: number, path: string) =>
    api.get(`/agents/admin/skills/${skillId}/file`, { params: { path } }) as any,
  importSkill: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/agents/admin/skills/import', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }) as any
  },
  syncSkills: () => api.post('/agents/admin/skills/sync') as any,
  updateSkillStatus: (skillId: number, status: 'active' | 'disabled') =>
    api.put(`/agents/admin/skills/${skillId}/status`, { status }) as any,
  deleteSkill: (skillId: number) => api.delete(`/agents/admin/skills/${skillId}`) as any,
  skillExecutors: () => api.get('/agents/admin/skill-executors') as any,
  adminConversation: (id: number, reason: string) =>
    api.get(`/agents/admin/conversations/${id}`, { params: { reason } }) as any,
  assistantStats: (params: Record<string, any> = {}) => api.get('/agents/admin/assistant/stats', { params }) as any,
  assistantRuns: (params: Record<string, any> = {}) => api.get('/agents/admin/assistant/runs', { params }) as any,
  assistantConfig: () => api.get('/agents/admin/assistant/config') as any,
  saveAssistantConfig: (data: { config: Record<string, any> }) =>
    api.put('/agents/admin/assistant/config', data) as any,
}
