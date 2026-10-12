import type { ReactNode } from 'react'

export type PermissionAwareItem = {
  key: string
  icon?: ReactNode
  label: string
  permission?: string
  children?: PermissionAwareItem[]
}

export type CrumbInfo = { root: string; page: string }

// 当前路径是否命中菜单项（精确或子路径，如 /orders/SO-123 命中 /orders）
export function pathMatches(key: string, pathname: string): boolean {
  return pathname === key || pathname.startsWith(key + '/')
}

// 不在菜单叶子下的页面（标题与面包屑共用回退）
const EXTRA_PAGE_NAMES: Record<string, string> = {
  '/profile': '个人中心',
}
const EXTRA_PAGE_PREFIXES: Array<[string, string]> = [
  ['/approvals/items/', '审批详情'],
]

function findCrumb(items: PermissionAwareItem[], pathname: string, rootLabel?: string): CrumbInfo | null {
  for (const item of items) {
    if (item.children && item.children.length > 0) {
      const found = findCrumb(item.children, pathname, rootLabel || item.label)
      if (found) return found
    } else if (pathMatches(item.key, pathname)) {
      return { root: rootLabel || '供应链中台', page: item.label }
    }
  }
  return null
}

// 面包屑：一级分组名 + 当前页名（顶级页面 root 固定为「供应链中台」）
export function resolveCrumb(items: PermissionAwareItem[], pathname: string): CrumbInfo {
  const matched = findCrumb(items, pathname)
  if (matched) return matched
  const exact = EXTRA_PAGE_NAMES[pathname]
  if (exact) return { root: '供应链中台', page: exact }
  const prefixHit = EXTRA_PAGE_PREFIXES.find(([p]) => pathname.startsWith(p))
  return { root: '供应链中台', page: prefixHit ? prefixHit[1] : '' }
}
