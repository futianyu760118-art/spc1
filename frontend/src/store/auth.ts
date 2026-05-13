import { create } from 'zustand'

interface UserInfo {
  id: number
  username: string
  display_name: string | null
  role_code: string
  role_name: string
  permissions: Record<string, string[]> | null
}

interface AuthState {
  token: string | null
  user: UserInfo | null
  setAuth: (token: string, user: UserInfo | null) => void
  logout: () => void
  hasPermission: (resource: string, action: string) => boolean
  isAdmin: () => boolean
}

export const useAuthStore = create<AuthState>((set, get) => {
  // Initialize from localStorage
  const token = localStorage.getItem('token')
  const userStr = localStorage.getItem('user')
  let user: UserInfo | null = null
  if (userStr) {
    try {
      user = JSON.parse(userStr)
    } catch {
      localStorage.removeItem('user')
    }
  }

  return {
    token,
    user,
    setAuth: (token, user) => {
      localStorage.setItem('token', token)
      if (user) {
        localStorage.setItem('user', JSON.stringify(user))
      }
      set({ token, user })
    },
    logout: () => {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      set({ token: null, user: null })
    },
    hasPermission: (resource: string, action: string) => {
      const { user } = get()
      if (!user) return false
      if (user.role_code === 'admin') return true
      const perms = user.permissions
      if (!perms || typeof perms !== 'object') return false
      // Check exact resource first
      const actions = perms[resource]
      if (Array.isArray(actions) && actions.includes(action)) return true
      // Fallback: check parent resource (e.g. 'orders.list' → 'orders')
      const dot = resource.indexOf('.')
      if (dot > 0) {
        const parent = resource.substring(0, dot)
        const parentActions = perms[parent]
        if (Array.isArray(parentActions) && parentActions.includes(action)) return true
      }
      return false
    },
    isAdmin: () => {
      const { user } = get()
      return user?.role_code === 'admin'
    },
  }
})
