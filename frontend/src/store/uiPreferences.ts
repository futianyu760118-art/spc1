import { create } from 'zustand'
import { authApi } from '../services/api'

interface UiPreferencesState {
  preferences: Record<string, any>
  getColumnVisibility: (pageKey: string, defaultColumns: string[]) => string[]
  setColumnVisibility: (pageKey: string, visibleColumns: string[]) => void
  loadFromUser: (user: any) => void
}

const UI_PREFS_KEY = 'spc_ui_preferences'

function readLocalPrefs(): Record<string, any> {
  try {
    const raw = localStorage.getItem(UI_PREFS_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

export const useUiPreferencesStore = create<UiPreferencesState>((set, get) => {
  const initial = readLocalPrefs()

  return {
    preferences: initial,

    getColumnVisibility: (pageKey, defaultColumns) => {
      const prefs = get().preferences
      const page = prefs[pageKey]
      if (page && Array.isArray(page.visibleColumns)) {
        return page.visibleColumns
      }
      return defaultColumns
    },

    setColumnVisibility: (pageKey, visibleColumns) => {
      const next = {
        ...get().preferences,
        [pageKey]: { ...get().preferences[pageKey], visibleColumns },
      }
      set({ preferences: next })
      localStorage.setItem(UI_PREFS_KEY, JSON.stringify(next))

      authApi.updateUiPreferences(next).catch((err) => {
        console.error('Failed to save column visibility preference:', err)
      })
    },

    loadFromUser: (user) => {
      if (user?.ui_preferences && typeof user.ui_preferences === 'object') {
        const merged = { ...readLocalPrefs(), ...user.ui_preferences }
        localStorage.setItem(UI_PREFS_KEY, JSON.stringify(merged))
        set({ preferences: merged })
      }
    },
  }
})
