export interface NotificationJumpItem {
  type: string
  ref_type?: string | null
  ref_no?: string | null
}

export interface NotificationJumpTarget {
  label: string
  path: string
}

const ASSISTANT_ORDER_LINK_TYPES = new Set([
  'assistant_update',
  'assistant_create',
  'assistant_gap',
])

export function notificationJump(item: NotificationJumpItem): NotificationJumpTarget | null {
  const refNo = item.ref_no?.trim()
  if (
    ASSISTANT_ORDER_LINK_TYPES.has(item.type) &&
    item.ref_type === 'order' &&
    refNo
  ) {
    return {
      label: `订单 ${refNo}`,
      path: `/orders/${encodeURIComponent(refNo)}`,
    }
  }
  return null
}
