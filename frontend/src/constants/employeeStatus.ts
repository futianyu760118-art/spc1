export const EMPLOYEE_STATUS_OPTIONS = [
  { value: 0, label: '试用', color: 'blue', activeAccount: true },
  { value: 1, label: '正式', color: 'green', activeAccount: true },
  { value: 2, label: '临时', color: 'cyan', activeAccount: true },
  { value: 3, label: '试用延期', color: 'orange', activeAccount: true },
  { value: 4, label: '解聘', color: 'red', activeAccount: false },
  { value: 5, label: '离职', color: 'volcano', activeAccount: false },
  { value: 6, label: '退休', color: 'purple', activeAccount: false },
  { value: 7, label: '无效', color: 'default', activeAccount: false },
] as const

export const EMPLOYEE_STATUS_FILTERS = EMPLOYEE_STATUS_OPTIONS.map(({ label, value }) => ({
  text: label,
  value: String(value),
}))

export const getEmployeeStatusMeta = (status?: number | null) => {
  return EMPLOYEE_STATUS_OPTIONS.find(item => item.value === status)
    ?? { value: status ?? -1, label: '未知', color: 'default', activeAccount: false }
}
