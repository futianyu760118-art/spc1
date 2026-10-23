import api from './api'

export type ApprovalWaitLevel = 'normal' | 'soon' | 'overdue'

export type ApprovalItem = {
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
  timeout_hours?: number | null
  wait_hours?: number | null
  wait_level?: ApprovalWaitLevel
  version?: number
  status?: string
  deep_link: string
  can_act?: boolean
  can_recall?: boolean
  my_action?: 'approve' | 'reject'
  my_comment?: string
  acted_at?: string
}

export type ApprovalStats = {
  total?: number
  today?: number
  soon?: number
  overdue?: number
  by_biz?: Record<string, number>
  processed?: number
  passed?: number
  rejected?: number
  avg_hours?: number | null
  draft?: number
  pending?: number
  approved?: number
  recalled?: number
}

export type ApprovalProgressNode = {
  seq: number
  label?: string
  approver_label?: string
  state: 'done' | 'current' | 'todo'
  acted_at?: string
  comment?: string
}

export type ApprovalLog = {
  time?: string
  who?: string
  action?: string
  action_label?: string
  comment?: string
}

export type ApprovalPreview = ApprovalItem & {
  fields?: Array<{ label: string; value?: string; emphasis?: boolean }>
  progress?: ApprovalProgressNode[]
  logs?: ApprovalLog[]
  action_hint?: string
  attachments?: Array<{ name?: string; key: string }>
}

export type ApprovalUserOption = {
  id: number
  username: string
  display_name?: string | null
  role_name?: string | null
}

export type ApprovalCondition = {
  field: string
  op: '>=' | '<=' | '>' | '<' | '==' | '!=' | 'in'
  value: number | string | Array<number | string>
}

export type ApprovalApprover = { user_id?: number; username?: string }

export type ApprovalNodeConfig = {
  seq?: number
  label: string
  role?: string
  approvers?: ApprovalApprover[]
  condition?: ApprovalCondition
  conditions?: ApprovalCondition[]
  timeout_hours?: number | null
  paper_slot?: string
}

export type ApprovalConfigItem = {
  biz_type: string
  biz_name: string
  nodes: ApprovalNodeConfig[]
  is_active?: boolean
  mode?: 'builtin' | 'sql'
  condition_field_options?: Array<{ value: string; label: string }>
  pending_count?: number | null
  updated_by?: string | null
  updated_at?: string | null
}

export type ApprovalFieldMapping = Partial<Record<
  'id' | 'no' | 'title' | 'summary' | 'applicant' | 'submitted_at' | 'current_node' | 'amount', string
>>

export type ApprovalConditionField = { value: string; label: string }

export type ApprovalWriteback = {
  table?: string
  id_column?: string
  status_column?: string
  status_map?: Record<string, string>
}

export type ApprovalBusinessItem = {
  biz_type: string
  biz_name: string
  mode: 'builtin' | 'sql'
  is_active: boolean
  description?: string | null
  pending_count?: number | null
  chain_node_count?: number
  has_sql?: boolean
  updated_by?: string | null
  updated_at?: string | null
  // 列表端点（管理员专用）额外返回，供向导编辑回填；内置业务为空
  sql_text?: string | null
  field_mapping?: ApprovalFieldMapping
  condition_fields?: ApprovalConditionField[]
  deep_link_template?: string | null
  writeback?: ApprovalWriteback | null
}

export type ApprovalBusinessPayload = {
  biz_type?: string
  biz_name: string
  sql_text: string
  field_mapping: ApprovalFieldMapping
  condition_fields: ApprovalConditionField[]
  deep_link_template?: string
  description?: string
  is_active?: boolean
  writeback?: ApprovalWriteback
}

export type TestSqlResult = { columns: string[]; rows: Record<string, any>[]; elapsed_ms: number }

export interface ApprovalMappingField { key: string; label: string; required: boolean }

export const approvalApi = {
  pending: (params?: Record<string, any>) => api.get('/approvals/pending', { params }),
  approved: (params?: Record<string, any>) => api.get('/approvals/approved', { params }),
  submitted: (params?: Record<string, any>) => api.get('/approvals/submitted', { params }),
  preview: (bizType: string, id: number) => api.get(`/approvals/items/${bizType}/${id}`),
  approve: (bizType: string, id: number, data: { comment?: string; expected_version?: number }) =>
    api.post(`/approvals/items/${bizType}/${id}/approve`, data),
  reject: (bizType: string, id: number, data: { comment: string; expected_version?: number }) =>
    api.post(`/approvals/items/${bizType}/${id}/reject`, data),
  recall: (bizType: string, id: number) =>
    api.post(`/approvals/items/${bizType}/${id}/recall`, {}),
  batchApprove: (data: { items: Array<{ biz_type: string; id: number; expected_version?: number }>; comment?: string }) =>
    api.post('/approvals/batch-approve', data),
  configs: () => api.get('/approvals/configs'),
  getConfig: (bizType: string) => api.get(`/approvals/configs/${bizType}`),
  saveConfig: (bizType: string, data: Record<string, any>) => api.put(`/approvals/configs/${bizType}`, data),
  roles: () => api.get('/approvals/roles'),
  users: (keyword?: string) => api.get('/approvals/users', { params: keyword ? { keyword } : {} }),
  businesses: () => api.get('/approvals/businesses'),
  createBusiness: (data: ApprovalBusinessPayload) => api.post('/approvals/businesses', data),
  updateBusiness: (bizType: string, data: ApprovalBusinessPayload) =>
    api.put(`/approvals/businesses/${bizType}`, data),
  testSql: (sqlText: string) => api.post('/approvals/businesses/test-sql', { sql_text: sqlText }),
}
