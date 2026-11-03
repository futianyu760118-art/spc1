import api from './api'

export const engineeringApi = {
  listLaborPrices: (params: Record<string, any>) => api.get('/engineering/labor-prices', { params }),
  listLaborPriceBoms: (params: Record<string, any>) => api.get('/engineering/labor-prices/boms', { params }),
  listCurrentLaborPrices: (params: Record<string, any>) =>
    api.get('/engineering/labor-prices/current', { params }),
  listLaborPriceChanges: (params: Record<string, any>) =>
    api.get('/engineering/labor-prices/changes', { params }),
  createLaborPriceChange: (data: Record<string, any>) =>
    api.post('/engineering/labor-prices/changes', data),
}
