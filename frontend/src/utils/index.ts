import dayjs from 'dayjs'

export function formatDate(date: string | null | undefined, fmt = 'YYYY-MM-DD') {
  if (!date) return '-'
  return dayjs(date).format(fmt)
}

export function daysAgoISO(days: number) {
  return dayjs().subtract(days, 'day').format('YYYY-MM-DD')
}

// 本周一（dayjs 默认周日起算，转成周一）；weekOffset=1 即上周一
export function mondayOf(weekOffset = 0) {
  const offsetToMonday = (dayjs().day() + 6) % 7
  return dayjs().subtract(offsetToMonday, 'day').startOf('day').subtract(weekOffset * 7, 'day')
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

// 表头列宽预估：标题 CJK 字符数 × 13px + 预留（内边距 + 排序/筛选图标 + 页面自有额外区），随全局字号缩放；配合 CSS 取消表头省略，保证表头名完整显示
export function tableHeaderFitWidth(charCount: number, fontSizeScale: number, reserve = 60): number {
  return (charCount * 13 + reserve) * fontSizeScale
}
