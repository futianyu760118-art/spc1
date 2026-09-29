import type { CreateBusinessEntry } from '../engine/types'
import { purchaseRequisitionBusiness } from './purchaseRequisition'
import { supplierClaimBusiness } from './supplierClaim'

const BUSINESSES: CreateBusinessEntry[] = [supplierClaimBusiness, purchaseRequisitionBusiness]

export function listBusinesses(): CreateBusinessEntry[] {
  return BUSINESSES
}

export function getBusiness(bizType: string): CreateBusinessEntry | undefined {
  return BUSINESSES.find(item => item.bizType === bizType)
}
