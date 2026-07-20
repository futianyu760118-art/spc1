import { create } from 'zustand'

export interface PoolMaterial {
  erp_material_id: number
  material_code: string | null
  material_name: string | null
  spec_model: string | null
  unit: string | null
  system_qty: number | null
  added_at: string
}

const STORAGE_KEY_PREFIX = 'spc_stock_check_pool'

function storageKeyFor(userId: number | null): string {
  return `${STORAGE_KEY_PREFIX}:${userId ?? 'anon'}`
}

function readPool(userId: number | null): PoolMaterial[] {
  try {
    const raw = localStorage.getItem(storageKeyFor(userId))
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as PoolMaterial[]) : []
  } catch {
    return []
  }
}

function writePool(userId: number | null, items: PoolMaterial[]): void {
  try {
    localStorage.setItem(storageKeyFor(userId), JSON.stringify(items))
  } catch {
    // localStorage may be unavailable (private mode, quota); silently degrade
  }
}

interface StockCheckPoolState {
  currentUserId: number | null
  items: PoolMaterial[]
  add: (materials: PoolMaterial[]) => void
  remove: (erpMaterialIds: number[]) => void
  clear: () => void
  has: (erpMaterialId: number) => boolean
  loadForUser: (userId: number | null) => void
}

function nowIso(): string {
  return new Date().toISOString()
}

export const useStockCheckPoolStore = create<StockCheckPoolState>((set, get) => {
  return {
    currentUserId: null,
    items: [],

    add: (materials) => {
      const state = get()
      const existing = new Set(state.items.map((m) => m.erp_material_id))
      const incoming = materials.filter((m) => !existing.has(m.erp_material_id))
      if (incoming.length === 0) return
      const stamped = incoming.map((m) => ({ ...m, added_at: m.added_at || nowIso() }))
      const next = [...state.items, ...stamped]
      set({ items: next })
      writePool(state.currentUserId, next)
    },

    remove: (erpMaterialIds) => {
      const state = get()
      const drop = new Set(erpMaterialIds)
      const next = state.items.filter((m) => !drop.has(m.erp_material_id))
      if (next.length === state.items.length) return
      set({ items: next })
      writePool(state.currentUserId, next)
    },

    clear: () => {
      const state = get()
      set({ items: [] })
      writePool(state.currentUserId, [])
    },

    has: (erpMaterialId) => get().items.some((m) => m.erp_material_id === erpMaterialId),

    loadForUser: (userId) => {
      const items = readPool(userId)
      set({ currentUserId: userId, items })
    },
  }
})