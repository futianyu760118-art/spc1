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
