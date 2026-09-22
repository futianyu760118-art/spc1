import api from './api'

export type ApprovalPendingItem = {
  biz_type: string
  biz_name: string
  id: number
  no?: string
  title?: string
  summary?: string
  applicant?: string
  submitted_at?: string
  current_level?: number
  current_node?: string
  deep_link: string
}

export const approvalApi = {
  pending: () => api.get('/approvals/pending'),
  configs: () => api.get('/approvals/configs'),
  getConfig: (bizType: string) => api.get(`/approvals/configs/${bizType}`),
  saveConfig: (bizType: string, data: Record<string, any>) => api.put(`/approvals/configs/${bizType}`, data),
  roles: () => api.get('/approvals/roles'),
}
