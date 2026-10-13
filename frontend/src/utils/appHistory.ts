import { createBrowserHistory, parsePath, type BrowserHistory, type Path, type To } from '@remix-run/router'
import { useUiPreferencesStore } from '../store/uiPreferences'

export const NEW_TAB_NAV_FLAG = 'open_links_in_new_tab'

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

function shouldOpenInNewTab(target: Path, currentPathname: string): boolean {
  if (!useUiPreferencesStore.getState().getFlag(NEW_TAB_NAV_FLAG, true)) return false
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
    if (shouldOpenInNewTab(target, history.location.pathname)) {
      // 保留 opener: 置空 opener 会导致浏览器禁止该标签自我关闭
      // (如审批完成后需要 window.close() 关掉页签)。同源自建应用, 保留 opener 可接受。
      const win = window.open(
        `${window.location.origin}${target.pathname}${target.search}${target.hash}`,
        '_blank'
      )
      if (win) {
        return
      }
      // 弹窗拦截器可能拦掉非用户手势触发的 window.open（如异步保存后自动跳转），此时退回本页跳转保证不失效
    }
    originalPush(to, state)
  }
  return history
}

export const appHistory = createAppHistory()
