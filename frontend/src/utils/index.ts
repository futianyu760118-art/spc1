import dayjs from 'dayjs'

export function formatDate(date: string | null | undefined, fmt = 'YYYY-MM-DD') {
  if (!date) return '-'
  return dayjs(date).format(fmt)
}

export function formatDateTime(date: string | null | undefined) {
  return formatDate(date, 'YYYY-MM-DD HH:mm')
}

export function downloadBlob(data: any, filename: string) {
  const url = window.URL.createObjectURL(new Blob([data]))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  window.URL.revokeObjectURL(url)
}

// 审批等待时长分级：≥阈值 urgent（已超时），≥一半 soon（即将超时），否则 ok；索赔单台账 / 详情共用
export function waitPill(submittedAt: string | null | undefined, thresholdHours: number): { level: 'urgent' | 'soon' | 'ok'; text: string } | null {
  if (!submittedAt) return null
  const hours = dayjs().diff(dayjs(submittedAt), 'hour')
  const level = hours >= thresholdHours ? 'urgent' : hours >= thresholdHours / 2 ? 'soon' : 'ok'
  const text = level === 'urgent'
    ? `已超时 ${hours >= 48 ? `${Math.floor(hours / 24)} 天` : `${hours} 小时`}`
    : `已等待 ${hours} 小时`
  return { level, text }
}
