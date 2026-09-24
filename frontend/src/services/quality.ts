import api from './api'

// 状态 → 中文文案 + 设计系统标签类（台账 chips / 表格状态列 / 详情页头共用）
export type ClaimStatus = 'draft' | 'pending' | 'approved' | 'rejected' | 'recalled'
export const CLAIM_STATUS_MAP: Record<ClaimStatus, { text: string; cls: string }> = {
  draft: { text: '草稿', cls: 'sc-tag-wait' },
  pending: { text: '审批中', cls: 'sc-tag-kit' },
  approved: { text: '已归档', cls: 'sc-tag-done' },
  rejected: { text: '已驳回', cls: 'sc-tag-danger' },
  recalled: { text: '已撤回', cls: 'sc-tag-amber' },
}
// 可编辑/可删除（非归档）的状态集合：操作列与详情页头共用
export const CLAIM_EDITABLE_STATUSES: ClaimStatus[] = ['draft', 'rejected', 'recalled']

export const CLAIM_REASON_OPTIONS = [
  { value: 'field_customer_claim', label: '现场/客户投诉 Field/customer claim' },
  { value: 'supply_performance', label: '供货业绩 Supply performance' },
]

export const CLAIM_ITEM_OPTIONS = [
  { value: 'replacement', label: '替代件费用 Replacement' },
  { value: 'packing_fee', label: '包装费用 Packing fee' },
  { value: 'transporting_fee', label: '运输费用 Transporting fee' },
  { value: 'man_hour_fee', label: '人工费用 Man-hour fee' },
  { value: 'additional_fee', label: '额外费用 Additional fee' },
  { value: 'punishment', label: '处罚 Punishment' },
  { value: 'downgrade_use', label: '降级使用' },
  { value: 'direct_loss', label: '直接损失' },
]

export const CLAIM_RETURN_OPTIONS = [
  { value: 'no_return', label: '无需退回，由恒剑直接处理' },
  { value: 'return_supplier_fee', label: '需退回，供应商承担运费' },
]

export function claimReasonText(v?: string) { return CLAIM_REASON_OPTIONS.find(o => o.value === v)?.label || '-' }
export function claimItemText(v?: string) { return CLAIM_ITEM_OPTIONS.find(o => o.value === v)?.label || v }
export function claimReturnText(v?: string) { return CLAIM_RETURN_OPTIONS.find(o => o.value === v)?.label || '-' }

export interface ClaimStats {
  total: number
  by_status: Record<'draft' | 'pending' | 'approved' | 'rejected' | 'recalled', number>
  month_count: number
  month_amount: number
  pending_mine: number
}

export const qualityApi = {
  stats: () => api.get('/quality/supplier-claims/stats'),
  list: (params: Record<string, any>) => api.get('/quality/supplier-claims', { params }),
  get: (id: number) => api.get(`/quality/supplier-claims/${id}`),
  create: (data: Record<string, any>) => api.post('/quality/supplier-claims', data),
  update: (id: number, data: Record<string, any>) => api.put(`/quality/supplier-claims/${id}`, data),
  delete: (id: number, canArchiveDelete = false) =>
    api.delete(`/quality/supplier-claims/${id}`, { params: { can_archive_delete: canArchiveDelete } }),
  submit: (id: number) => api.post(`/quality/supplier-claims/${id}/submit`, {}),
  approve: (id: number, comment: string, expectedVersion?: number) =>
    api.post(`/quality/supplier-claims/${id}/approve`, { comment, expected_version: expectedVersion }),
  reject: (id: number, comment: string, expectedVersion?: number) =>
    api.post(`/quality/supplier-claims/${id}/reject`, { comment, expected_version: expectedVersion }),
  recall: (id: number) => api.post(`/quality/supplier-claims/${id}/recall`),
  revokeApproval: (id: number) => api.post(`/quality/supplier-claims/${id}/revoke-approval`),
  searchSuppliers: (keyword: string) =>
    api.get('/quality/supplier-claims/suppliers/search', { params: { keyword } }),
}
