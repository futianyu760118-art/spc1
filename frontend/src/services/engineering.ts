import api from './api'

export const engineeringApi = {
  listLaborPrices: (params: Record<string, any>) => api.get('/engineering/labor-prices', { params }),
  listLaborPriceBoms: (params: Record<string, any>) => api.get('/engineering/labor-prices/boms', { params }),
  listCurrentLaborPrices: (params: Record<string, any>) =>
    api.get('/engineering/labor-prices/current', { params }),
  listLaborPriceChanges: (params: Record<string, any>) =>
    api.get('/engineering/labor-prices/changes', { params }),
  getLaborPriceChange: (id: number) =>
    api.get(`/engineering/labor-prices/changes/${id}`),
  createLaborPriceChange: (data: Record<string, any>) =>
    api.post('/engineering/labor-prices/changes', data),
  updateLaborPriceChange: (id: number, data: Record<string, any>) =>
    api.put(`/engineering/labor-prices/changes/${id}`, data),
  deleteLaborPriceChange: (id: number) =>
    api.delete(`/engineering/labor-prices/changes/${id}`),
  approveLaborPriceChange: (id: number) =>
    api.post(`/engineering/labor-prices/changes/${id}/approve`),
  rejectLaborPriceChange: (id: number) =>
    api.post(`/engineering/labor-prices/changes/${id}/reject`),
}
