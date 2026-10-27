import api from './api'

export type AgentTaskStatus = 'pending' | 'in_progress' | 'blocked' | 'completed' | 'cancelled'
export type AgentTaskPriority = 'low' | 'normal' | 'high' | 'urgent'
export type AgentAnalysisStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped'

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

export interface AgentScope {
  summary: string
  org_ids: number[]
  org_names: string[]
  include_self_owned: boolean
  mode?: string
  include_sub?: boolean
}

export interface AgentPolicy {
  granted: string[]
  disabled: string[]
  data_scope: { mode: string; org_ids: number[]; include_sub: boolean; include_self_owned: boolean }
}

export interface AgentTask {
  id: number
  task_no: string
  title: string
  description?: string
  task_type: 'business' | 'general'
  biz_type?: string | null
  biz_id?: string | null
  biz_no?: string | null
  biz_title?: string | null
  biz_url?: string | null
  biz_context?: Record<string, any> | null
  assigner_agent_id: number
  assigner_user_id: number
  assigner_name?: string
  assignee_agent_id: number
  assignee_user_id: number
  assignee_name?: string
  priority: AgentTaskPriority
  status: AgentTaskStatus
  source: string
  due_at: string
  started_at?: string | null
  completed_at?: string | null
  cancelled_at?: string | null
  analysis_status: AgentAnalysisStatus
  analysis_error?: string | null
  latest_report_id?: number | null
  reopen_count: number
  is_overdue: boolean
  latest_report?: { summary: string; version: number } | null
  created_at?: string
  updated_at?: string
}

export interface AgentTaskDetail extends AgentTask {
  analysis_result?: Record<string, any> | null
  can_act: boolean
  can_manage: boolean
  reports: AgentTaskReport[]
  events: AgentTaskEvent[]
}

export interface AgentTaskReport {
  id: number
  version: number
  summary: string
  result_data?: Record<string, any> | null
  evidence?: any[] | null
  submitted_by_user_id: number
  submitted_at: string
}

export interface AgentTaskEvent {
  id: number
  event_type: string
  actor_agent_id?: number | null
  actor_user_id?: number | null
  from_status?: string | null
  to_status?: string | null
  payload?: Record<string, any> | null
  created_at: string
}

export interface AgentTaskSummary {
  total: number
  by_status: Record<string, number>
  open: number
  overdue: number
  completed_week: number
}

export interface TeamTaskSummary {
  total: number
  open: number
  overdue: number
  blocked: number
  completed_week: number
  analysis_failed: number
  by_assignee: Array<{
    assignee_user_id: number
    assignee_name: string
    open: number
    overdue: number
    blocked: number
    completed_week: number
  }>
}

export const agentApi = {
  me: () => api.get('/agents/me', { skipErrorToast: true }) as any,
  conversations: (params: Record<string, any> = {}, skipErrorToast = false) =>
    api.get('/agents/me/conversations', { params, skipErrorToast }) as any,
  conversation: (id: number) => api.get(`/agents/me/conversations/${id}`) as any,
  archiveConversation: (id: number) => api.post(`/agents/me/conversations/${id}/archive`) as any,
  myTasks: (params: Record<string, any> = {}, skipErrorToast = false) =>
    api.get('/agents/me/tasks', { params, skipErrorToast }) as any,
  myTasksSummary: () => api.get('/agents/me/tasks/summary', { skipErrorToast: true }) as any,
  team: () => api.get('/agents/me/team') as any,
  addMember: (data: { user_id?: number; username?: string }) => api.post('/agents/me/team', data) as any,
  candidates: (keyword = '') => api.get('/agents/me/team/candidates', { params: { keyword } }) as any,
  teamMember: (agentId: number) => api.get(`/agents/me/team/${agentId}`) as any,
  updatePolicy: (agentId: number, data: Record<string, any>) =>
    api.put(`/agents/me/team/${agentId}/policy`, data) as any,
  teamTasks: (params: Record<string, any> = {}) => api.get('/agents/me/team/tasks', { params }) as any,
  teamTasksSummary: () => api.get('/agents/me/team/tasks/summary') as any,
  task: (id: number) => api.get(`/agents/tasks/${id}`) as any,
  taskEvents: (id: number) => api.get(`/agents/tasks/${id}/events`) as any,
  taskReports: (id: number) => api.get(`/agents/tasks/${id}/reports`) as any,
  startTask: (id: number) => api.post(`/agents/tasks/${id}/start`) as any,
  blockTask: (id: number, reason: string) => api.post(`/agents/tasks/${id}/block`, { reason }) as any,
  resumeTask: (id: number) => api.post(`/agents/tasks/${id}/resume`) as any,
  submitTask: (id: number, data: Record<string, any>) => api.post(`/agents/tasks/${id}/submit`, data) as any,
  analyzeTask: (id: number) => api.post(`/agents/tasks/${id}/analyze`) as any,
  remindTask: (id: number) => api.post(`/agents/tasks/${id}/remind`) as any,
  patchTask: (id: number, data: Record<string, any>) => api.patch(`/agents/tasks/${id}`, data) as any,
  reassignTask: (id: number, newAssigneeUserId: number) =>
    api.post(`/agents/tasks/${id}/reassign`, { new_assignee_user_id: newAssigneeUserId }) as any,
  cancelTask: (id: number, reason: string) => api.post(`/agents/tasks/${id}/cancel`, { reason }) as any,
  returnTask: (id: number, reason: string) => api.post(`/agents/tasks/${id}/return`, { reason }) as any,
  taskConversation: (id: number) => api.post(`/agents/tasks/${id}/conversation`) as any,
  adminAgents: (params: Record<string, any> = {}) => api.get('/agents/admin/agents', { params }) as any,
  adminTasks: (params: Record<string, any> = {}) => api.get('/agents/admin/tasks', { params }) as any,
  adminStats: () => api.get('/agents/admin/stats') as any,
  adminHierarchy: (agentId: number, data: Record<string, any>) =>
    api.put(`/agents/admin/agents/${agentId}/hierarchy`, data) as any,
  adminPolicy: (agentId: number, data: Record<string, any>) =>
    api.put(`/agents/admin/agents/${agentId}/policy`, data) as any,
  adminConversation: (id: number, reason: string) =>
    api.get(`/agents/admin/conversations/${id}`, { params: { reason } }) as any,
}
