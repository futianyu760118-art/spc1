import type { JSX } from 'react'
import ClaimPaper from '../../components/ClaimPaper'
import PurchaseRequisitionPaper from '../../components/PurchaseRequisitionPaper'

/** 审批详情页业务视图注册表：新 builtin 业务在此登记，Item 页不再写 bizType 分支。 */
export type PaperLoader = (itemId: number) => Promise<{ node: JSX.Element | null } | null>

const loadClaim: PaperLoader = async (id) => {
  const { qualityApi } = await import('../../services/quality')
  try {
    const res: any = await qualityApi.get(id)
    if (!res?.data) return null
    return { node: <ClaimPaper claim={res.data} /> }
  } catch { return null }
}

const loadRequisition: PaperLoader = async (id) => {
  const { materialApi } = await import('../../services/api')
  try {
    const res: any = await materialApi.getPurchaseRequisition(id)
    if (!res?.data) return null
    return { node: <PurchaseRequisitionPaper req={res.data} small /> }
  } catch { return null }
}

export const approvalPaperRegistry: Record<string, PaperLoader> = {
  supplier_claim: loadClaim,
  purchase_requisition: loadRequisition,
}
