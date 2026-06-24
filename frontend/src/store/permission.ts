import { create } from 'zustand'
import { permissionApi } from '../services/api'

export interface PermNode {
  code: string
  name: string
  module: string
  parent_code: string | null
  actions: string[]
  route_path: string | null
  sort_order: number
  children: PermNode[]
}

interface PermissionState {
  tree: PermNode[]
  loaded: boolean
  loading: boolean
  // 派生数据缓存
  _pathToPermission: Record<string, string> | null
  _pathToGroupKey: Record<string, string> | null
  _sharePathToPermission: Record<string, string> | null

  fetchTree: () => Promise<PermNode[]>
  getTree: () => PermNode[]
  getPathToPermission: () => Record<string, string>
  getPathToGroupKey: () => Record<string, string>
  getSharePathToPermission: () => Record<string, string>
}

function buildPathToPermission(nodes: PermNode[]): Record<string, string> {
  const map: Record<string, string> = {}
  for (const node of nodes) {
    if (node.route_path) {
      map[node.route_path] = node.code
    }
    if (node.children?.length) {
      Object.assign(map, buildPathToPermission(node.children))
    }
  }
  return map
}

function buildPathToGroupKey(nodes: PermNode[], parentKey?: string): Record<string, string> {
  const map: Record<string, string> = {}
  for (const node of nodes) {
    // 有 children 的节点是菜单组
    const groupKey = node.children?.length ? node.code : parentKey
    if (node.route_path && groupKey) {
      map[node.route_path] = groupKey
    }
    if (node.children?.length) {
      Object.assign(map, buildPathToGroupKey(node.children, node.children.length ? node.code : parentKey))
    }
  }
  return map
}

function buildSharePathToPermission(nodes: PermNode[]): Record<string, string> {
  const map: Record<string, string> = {}
  for (const node of nodes) {
    if (node.route_path) {
      map[node.route_path] = node.code
    }
    if (node.children?.length) {
      Object.assign(map, buildSharePathToPermission(node.children))
    }
  }
  return map
}

export const usePermissionStore = create<PermissionState>((set, get) => ({
  tree: [],
  loaded: false,
  loading: false,
  _pathToPermission: null,
  _pathToGroupKey: null,
  _sharePathToPermission: null,

  fetchTree: async () => {
    const state = get()
    if (state.loaded && state.tree.length > 0) return state.tree
    if (state.loading) {
      // 等待加载完成
      return new Promise((resolve) => {
        const check = () => {
          const s = get()
          if (s.loaded) resolve(s.tree)
          else setTimeout(check, 100)
        }
        setTimeout(check, 100)
      })
    }
    set({ loading: true })
    try {
      const res: any = await permissionApi.tree()
      const tree: PermNode[] = res?.data || []
      set({
        tree,
        loaded: true,
        loading: false,
        _pathToPermission: null,
        _pathToGroupKey: null,
        _sharePathToPermission: null,
      })
      return tree
    } catch {
      set({ loading: false })
      return []
    }
  },

  getTree: () => get().tree,

  getPathToPermission: () => {
    const state = get()
    if (state._pathToPermission) return state._pathToPermission
    const map = buildPathToPermission(state.tree)
    set({ _pathToPermission: map })
    return map
  },

  getPathToGroupKey: () => {
    const state = get()
    if (state._pathToGroupKey) return state._pathToGroupKey
    const map = buildPathToGroupKey(state.tree)
    set({ _pathToGroupKey: map })
    return map
  },

  getSharePathToPermission: () => {
    const state = get()
    if (state._sharePathToPermission) return state._sharePathToPermission
    const map = buildSharePathToPermission(state.tree)
    set({ _sharePathToPermission: map })
    return map
  },
}))
