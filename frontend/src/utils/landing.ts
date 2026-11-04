import { useAuthStore } from '../store/auth'

export function resolveEmployeeLandingPath(user: any): string {
  const auth = useAuthStore.getState()
  if (!user || user.role_code === 'admin') return '/dashboard'
  if (auth.hasPermission('production.labor_price_audit', 'read')) {
    return '/engineering/labor-prices'
  }
  if (auth.hasPermission('production.schedule_plans', 'read')) {
    return '/todo-workbench'
  }
  return '/dashboard'
}

export function resolveEmployeeLoginTarget(user: any, from?: string | null): string {
  const path = (from || '').split('?')[0]
  if (path && path !== '/' && path !== '/dashboard' && path !== '/login') {
    return from as string
  }
  return resolveEmployeeLandingPath(user)
}
