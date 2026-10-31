import api from '@/services/api'

export interface EnqueueWritebackRequest {
  writeback_type: string
  business_table?: string
  business_pk: string
  target_keys: Record<string, any>
  payload: Record<string, any>
  reason?: string
}

export const writebackApi = {
  enqueue: (data: EnqueueWritebackRequest) =>
    api.post('/writeback/enqueue', data).then(r => r.data),

  listQueue: (params?: Record<string, any>) =>
    api.get('/writeback/queue', { params }).then(r => r.data),

  getQueueDetail: (id: number) =>
    api.get(`/writeback/queue/${id}`).then(r => r.data),

  retryQueue: (id: number) =>
    api.post(`/writeback/queue/${id}/retry`).then(r => r.data),

  abandonQueue: (id: number) =>
    api.post(`/writeback/queue/${id}/abandon`).then(r => r.data),

  listLog: (params?: Record<string, any>) =>
    api.get('/writeback/log', { params }).then(r => r.data),

  getStats: () =>
    api.get('/writeback/stats').then(r => r.data),

  listConfig: () =>
    api.get('/writeback/config').then(r => r.data),

  upsertConfig: (data: any) =>
    api.post('/writeback/config', data).then(r => r.data),

  testConfig: (writebackType: string) =>
    api.post(`/writeback/config/${writebackType}/test`).then(r => r.data),
}
