import api from './api'

export const monthlyCapacityPlanApi = {
  getScenario: () => api.get('/production/monthly-capacity-plan/scenario'),
  saveScenario: (data: Record<string, any>) =>
    api.put('/production/monthly-capacity-plan/scenario', data),
  getMonthlyCapacityPlan: (params: Record<string, any>) =>
    api.get('/production/monthly-capacity-plan', { params }),
  getAllocationPreview: (params: Record<string, any>) =>
    api.get('/production/monthly-capacity-plan/allocation-preview', { params }),
  generateMonthlyPlans: (params: Record<string, any>) =>
    api.post('/production/monthly-capacity-plan/plans/generate', null, { params }),
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
}
