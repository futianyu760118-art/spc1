import type { CreateBusinessEntry } from '../engine/types'
import { priceChangeBusiness } from './priceChange'
import { purchaseRequisitionBusiness } from './purchaseRequisition'
import { supplierClaimBusiness } from './supplierClaim'

const BUSINESSES: CreateBusinessEntry[] = [
  supplierClaimBusiness,
  purchaseRequisitionBusiness,
  priceChangeBusiness,
]

export function listBusinesses(): CreateBusinessEntry[] {
  return BUSINESSES
}

export function getBusiness(bizType: string): CreateBusinessEntry | undefined {
  return BUSINESSES.find(item => item.bizType === bizType)
}
