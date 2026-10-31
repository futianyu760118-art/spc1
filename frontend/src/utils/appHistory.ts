import { createBrowserHistory, parsePath, type BrowserHistory, type Path, type To } from '@remix-run/router'
import { useTabsStore } from '../store/tabs'

function isLoginPath(pathname: string): boolean {
  return pathname === '/login' || pathname.startsWith('/login/')
}

function resolveTarget(to: To, currentPathname: string): Path {
  const parsed = typeof to === 'string' ? parsePath(to) : to
  // query/hash-only 的 to（如 '?tab=x'）解析后 pathname 为空，按 URL 语义继承当前页
  return {
    pathname: parsed.pathname || currentPathname,
    search: parsed.search || '',
    hash: parsed.hash || '',
  }
}

function isCrossPage(target: Path, currentPathname: string): boolean {
  if (target.pathname === currentPathname) return false
  if (isLoginPath(currentPathname) || isLoginPath(target.pathname)) return false
  return true
}

export function createAppHistory(): BrowserHistory {
  // 必须与 react-router-dom 自带 BrowserRouter 一致传 v5Compat: true，
  // 否则 push/replace 只改 URL 不通知监听器，页面不重渲（登录后停在登录页）
  const history = createBrowserHistory({ v5Compat: true })
  const originalPush = history.push.bind(history)
  history.push = (to: To, state?: any) => {
    const target = resolveTarget(to, history.location.pathname)
    if (isCrossPage(target, history.location.pathname)) {
      useTabsStore.getState().openTab(target.pathname, target.search)
    } else {
      useTabsStore.getState().syncActiveUrl(target.pathname, target.search)
    }
    originalPush(to, state)
  }
  const originalReplace = history.replace.bind(history)
  history.replace = (to: To, state?: any) => {
    const target = resolveTarget(to, history.location.pathname)
    const current = history.location
    if (target.pathname !== current.pathname || target.search !== current.search) {
      if (!isLoginPath(current.pathname) && !isLoginPath(target.pathname)) {
        useTabsStore.getState().replaceTo(target.pathname, target.search)
      }
    }
    originalReplace(to, state)
  }
  return history
}

export const appHistory = createAppHistory()
