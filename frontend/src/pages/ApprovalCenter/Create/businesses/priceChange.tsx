import PriceChangeForm from '../../../Purchase/PriceChange/PriceChangeForm'
import type { CreateBusinessEntry } from '../engine/types'

export const priceChangeBusiness: CreateBusinessEntry = {
  bizType: 'price_change',
  name: '调价单',
  description: '供应商调价（含 ERP 比价与提交自检），提交后进入采购中心审批链',
  permission: ['purchase.price_change', 'create'],
  component: PriceChangeForm,
}
