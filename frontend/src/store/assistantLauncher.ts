import { create } from 'zustand'

const STORAGE_KEY = 'spc_assistant_launcher_v1'
const DEFAULT_POSITION = { right: 24, bottom: 24 }

export type AssistantLauncherMode = 'floating' | 'docked'

interface AssistantLauncherPosition {
  right: number
  bottom: number
}

interface AssistantLauncherState {
  mode: AssistantLauncherMode
  position: AssistantLauncherPosition
  setPosition: (position: AssistantLauncherPosition) => void
  dock: () => void
  undock: () => void
}

function loadState(): Pick<AssistantLauncherState, 'mode' | 'position'> {
  if (typeof window === 'undefined') {
    return { mode: 'floating', position: DEFAULT_POSITION }
  }
  try {
    const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '{}')
    const right = Number(saved.position?.right)
    const bottom = Number(saved.position?.bottom)
    return {
      mode: saved.mode === 'docked' ? 'docked' : 'floating',
      position: {
        right: Number.isFinite(right) ? right : DEFAULT_POSITION.right,
        bottom: Number.isFinite(bottom) ? bottom : DEFAULT_POSITION.bottom,
      },
    }
  } catch {
    return { mode: 'floating', position: DEFAULT_POSITION }
  }
}

function saveState(mode: AssistantLauncherMode, position: AssistantLauncherPosition) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ mode, position }))
  } catch {
    /* localStorage is optional */
  }
}

const initial = loadState()

export const useAssistantLauncherStore = create<AssistantLauncherState>((set, get) => ({
  ...initial,
  setPosition: (position) => {
    set({ position })
    saveState(get().mode, position)
  },
  dock: () => {
    set({ mode: 'docked' })
    saveState('docked', get().position)
  },
  undock: () => {
    const position = { ...DEFAULT_POSITION }
    set({ mode: 'floating', position })
    saveState('floating', position)
  },
}))
