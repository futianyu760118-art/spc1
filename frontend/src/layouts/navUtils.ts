import type { ReactNode } from 'react'

export type PermissionAwareItem = {
  key: string
  icon?: ReactNode
  label: string
  permission?: string
  /** 任一满足即可见/可进入（如 智能助手管理：monitor 或 config 任一） */
  anyOfPermissions?: string[]
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

type CrumbMatch = CrumbInfo & { key: string }

// 按最长 key 匹配（如 /orders 与 /orders/new 均前缀命中时取更具体的菜单项）
function findCrumb(items: PermissionAwareItem[], pathname: string): CrumbMatch | null {
  let best: CrumbMatch | null = null
  const walk = (list: PermissionAwareItem[], root: string) => {
    for (const item of list) {
      if (item.children && item.children.length > 0) {
        walk(item.children, root || item.label)
      } else if (pathMatches(item.key, pathname)) {
        if (!best || item.key.length > best.key.length) {
          best = { root: root || '供应链中台', page: item.label, key: item.key }
        }
      }
    }
  }
  walk(items, '')
  return best
}

function safeDecode(segment: string): string {
  try {
    return decodeURIComponent(segment)
  } catch {
    return segment
  }
}

// 详情等动态页面把识别段拼进标题（订单总控台 · HJ202604-0021-0089），
// 避免同一菜单下多个页面页签同名
function withPathSuffix(label: string, pathname: string, key: string): string {
  const rest = pathname.slice(key.length).replace(/^\/+|\/+$/g, '')
  if (!rest) return label
  const seg = safeDecode(rest.split('/')[0])
  return seg ? `${label} · ${seg}` : label
}

// 面包屑/页签标题：一级分组名 + 当前页名（顶级页面 root 固定为「供应链中台」）
export function resolveCrumb(items: PermissionAwareItem[], pathname: string): CrumbInfo {
  const matched = findCrumb(items, pathname)
  if (matched) {
    return { root: matched.root, page: withPathSuffix(matched.page, pathname, matched.key) }
  }
  const exact = EXTRA_PAGE_NAMES[pathname]
  if (exact) return { root: '供应链中台', page: exact }
  const prefixHit = EXTRA_PAGE_PREFIXES.find(([p]) => pathname.startsWith(p))
  if (prefixHit) {
    // 前缀型页面（审批详情）识别段在末尾（id），取最后一段
    const segs = pathname.slice(prefixHit[0].length).split('/').filter(Boolean)
    const tail = segs.length ? safeDecode(segs[segs.length - 1]) : ''
    return { root: '供应链中台', page: tail ? `${prefixHit[1]} · ${tail}` : prefixHit[1] }
  }
  return { root: '供应链中台', page: '' }
}
