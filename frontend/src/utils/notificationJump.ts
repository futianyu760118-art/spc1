export interface NotificationJumpItem {
  type: string
  ref_type?: string | null
  ref_id?: number | null
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
  if (item.type === 'agent_config' || item.type === 'agent_hierarchy' || item.type === 'agent_team') {
    return { label: '智能体中心', path: '/agents/team' }
  }
  return null
}
