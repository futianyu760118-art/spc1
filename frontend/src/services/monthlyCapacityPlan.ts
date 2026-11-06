import api from './api'

export const monthlyCapacityPlanApi = {
  getScenario: () => api.get('/production/monthly-capacity-plan/scenario'),
  saveScenario: (data: Record<string, any>) =>
    api.put('/production/monthly-capacity-plan/scenario', data),
  getMonthlyCapacityPlan: (params: Record<string, any>) =>
    api.get('/production/monthly-capacity-plan', { params }),
  getAllocationPreview: (params: Record<string, any>) =>
    api.get('/production/monthly-capacity-plan/allocation-preview', { params }),
  getAiAllocationPreview: (params: Record<string, any>) =>
    api.get('/production/monthly-capacity-plan/ai-allocation-preview', {
      params,
      timeout: 120000,
    }),
  generateMonthlyPlans: (params: Record<string, any>) =>
    api.post('/production/monthly-capacity-plan/plans/generate', null, { params }),
  generateAiMonthlyPlans: (params: Record<string, any>, orderSequence: Array<{ order_no: string; line_no: string }>) =>
    api.post(
      '/production/monthly-capacity-plan/plans/generate-ai',
      { order_sequence: orderSequence },
      { params },
    ),
  listMonthlyPlans: (params: Record<string, any>) =>
    api.get('/production/monthly-capacity-plan/plans', { params }),
  listMonthlyPlanBatches: (params: Record<string, any>) =>
    api.get('/production/monthly-capacity-plan/plans/batches', { params }),
  activateMonthlyPlanBatch: (batchNo: string, params: Record<string, any>) =>
    api.post(
      `/production/monthly-capacity-plan/plans/batches/${encodeURIComponent(batchNo)}/activate`,
      null,
      { params },
    ),
  updateMonthlyPlan: (planId: number, data: Record<string, any>) =>
    api.put(`/production/monthly-capacity-plan/plans/${planId}`, data),
  getWeeklyCapacity: (params?: Record<string, any>) =>
    api.get('/production/weekly-capacity/next', { params }),
  pushWeeklyCapacity: () => api.post('/production/weekly-capacity/push'),
}
