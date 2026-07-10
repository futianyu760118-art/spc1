import { create } from 'zustand'
import { authApi } from '../services/api'

interface ThemeState {
  fontSizeScale: number
  setFontSizeScale: (scale: number) => void
  loadFontSizeFromUser: (user: any) => void
}

const FONT_SIZE_KEY = 'spc_font_size_scale'

export const useThemeStore = create<ThemeState>((set, get) => {
  // Initialize from localStorage first (fallback)
  const savedScale = localStorage.getItem(FONT_SIZE_KEY)
  const fontSizeScale = savedScale ? parseFloat(savedScale) : 1.0

  return {
    fontSizeScale,
    setFontSizeScale: async (scale) => {
      // Update local state immediately for responsiveness
      localStorage.setItem(FONT_SIZE_KEY, scale.toString())
      set({ fontSizeScale: scale })

      // Save to database in the background
      try {
        await authApi.updatePreferences({ font_size_scale: scale.toString() })
      } catch (error) {
        console.error('Failed to save font size preference:', error)
      }
    },
    loadFontSizeFromUser: (user) => {
      if (user?.font_size_scale) {
        const scale = parseFloat(user.font_size_scale)
        if (!isNaN(scale)) {
          localStorage.setItem(FONT_SIZE_KEY, user.font_size_scale)
          set({ fontSizeScale: scale })
        }
      }
    },
  }
})
