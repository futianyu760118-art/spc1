import { create } from 'zustand'

export interface PoolMaterial {
  erp_material_id: number
  material_code: string | null
  material_name: string | null
  spec_model: string | null
  unit: string | null
  system_qty: number | null
  added_at: string
  // 仓库维度: wh_id === undefined 表示旧版数据(整物料全仓库); null 表示未入库合成行; 数字表示具体仓库
  wh_id?: number | null
  wh_code?: string | null
  wh_name?: string | null
}

export function poolKey(m: Pick<PoolMaterial, 'erp_material_id' | 'wh_id'>): string {
  if (m.wh_id === undefined) return `${m.erp_material_id}|all`
  if (m.wh_id === null) return `${m.erp_material_id}|none`
  return `${m.erp_material_id}|${m.wh_id}`
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
  remove: (materials: Array<Pick<PoolMaterial, 'erp_material_id' | 'wh_id'>>) => void
  clear: () => void
  has: (material: Pick<PoolMaterial, 'erp_material_id' | 'wh_id'>) => boolean
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
      const existing = new Set(state.items.map((m) => poolKey(m)))
      const incoming = materials.filter((m) => !existing.has(poolKey(m)))
      if (incoming.length === 0) return
      const stamped = incoming.map((m) => ({ ...m, added_at: m.added_at || nowIso() }))
      const next = [...state.items, ...stamped]
      set({ items: next })
      writePool(state.currentUserId, next)
    },

    remove: (materials) => {
      const state = get()
      const drop = new Set(materials.map((m) => poolKey(m)))
      const next = state.items.filter((m) => !drop.has(poolKey(m)))
      if (next.length === state.items.length) return
      set({ items: next })
      writePool(state.currentUserId, next)
    },

    clear: () => {
      const state = get()
      set({ items: [] })
      writePool(state.currentUserId, [])
    },

    has: (material) => get().items.some((m) => poolKey(m) === poolKey(material)),

    loadForUser: (userId) => {
      const items = readPool(userId)
      set({ currentUserId: userId, items })
    },
  }
})
