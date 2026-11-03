import type { ReactNode } from 'react'
import type { PermissionAwareItem } from './navUtils'

export interface SidebarMenuPrefs {
  version: 1
  userId?: number | string
  pinned: string[]
  groupOrder: string[]
  pageOrder: Record<string, string[]>
  parked: string[]
}

export const SIDEBAR_MENU_PREF_KEY = 'spc_sidebar_menu_v1'

export const DEFAULT_SIDEBAR_MENU_PREFS: SidebarMenuPrefs = {
  version: 1,
  pinned: [],
  groupOrder: [],
  pageOrder: {},
  parked: [],
}

export interface SidebarPageRef {
  item: PermissionAwareItem
  key: string
  groupKey: string
  groupLabel: string
  pathLabels: string[]
}

export interface SidebarGroupModel {
  key: string
  label: string
  icon?: ReactNode
  item: PermissionAwareItem
  pages: SidebarPageRef[]
}

export interface SidebarLayout {
  pinned: SidebarPageRef[]
  groups: SidebarGroupModel[]
  parked: SidebarPageRef[]
}

export interface SidebarEntry {
  kind: 'pinned' | 'module'
  key: string
  groupKey: string
  groupLabel: string
  item: PermissionAwareItem
}

export interface SidebarMoreSection {
  key: string
  label: string
  pages: SidebarPageRef[]
}

export interface SidebarCustomizeModel {
  groups: SidebarGroupModel[]
  pinned: SidebarPageRef[]
  parked: SidebarPageRef[]
}

function toKeyArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

export function normalizeSidebarMenuPrefs(raw: unknown): SidebarMenuPrefs {
  if (!raw || typeof raw !== 'object') {
    return { ...DEFAULT_SIDEBAR_MENU_PREFS, pageOrder: {} }
  }
  const record = raw as Record<string, unknown>
  const pageOrder: Record<string, string[]> = {}
  if (record.pageOrder && typeof record.pageOrder === 'object') {
    for (const [groupKey, order] of Object.entries(record.pageOrder as Record<string, unknown>)) {
      pageOrder[groupKey] = toKeyArray(order)
    }
  }
  return {
    version: 1,
    userId: typeof record.userId === 'number' || typeof record.userId === 'string' ? record.userId : undefined,
    pinned: toKeyArray(record.pinned),
    groupOrder: toKeyArray(record.groupOrder),
    pageOrder,
    parked: toKeyArray(record.parked),
  }
}

function uniqueKeys(keys: string[]): string[] {
  return Array.from(new Set(keys))
}

function orderByKeys<T>(items: T[], getKey: (item: T) => string, order: string[]): T[] {
  if (order.length === 0) return items.slice()
  const rank = new Map(order.map((key, index) => [key, index]))
  return items.slice().sort((a, b) => {
    const rankA = rank.get(getKey(a))
    const rankB = rank.get(getKey(b))
    if (rankA === undefined && rankB === undefined) return 0
    if (rankA === undefined) return 1
    if (rankB === undefined) return -1
    return rankA - rankB
  })
}

function collectPages(
  node: PermissionAwareItem,
  trail: string[],
  groupKey: string,
  groupLabel: string,
): SidebarPageRef[] {
  if (!node.children || node.children.length === 0) {
    return [{ item: node, key: node.key, groupKey, groupLabel, pathLabels: trail }]
  }
  const nextTrail = [...trail, node.label]
  return node.children.flatMap(child => collectPages(child, nextTrail, groupKey, groupLabel))
}

function buildGroups(items: PermissionAwareItem[]): SidebarGroupModel[] {
  return items.map(item => {
    const pages = item.children && item.children.length > 0
      ? item.children.flatMap(child => collectPages(child, [], item.key, item.label))
      : [{ item, key: item.key, groupKey: item.key, groupLabel: item.label, pathLabels: [] }]
    return { key: item.key, label: item.label, icon: item.icon, item, pages }
  })
}

export function buildSidebarCustomizeModel(
  navTree: PermissionAwareItem[],
  prefs: SidebarMenuPrefs,
): SidebarCustomizeModel {
  const groups = orderByKeys(buildGroups(navTree), group => group.key, prefs.groupOrder)
  for (const group of groups) {
    group.pages = orderByKeys(group.pages, page => page.key, prefs.pageOrder[group.key] || [])
  }
  const pageByKey = new Map<string, SidebarPageRef>()
  for (const group of groups) {
    for (const page of group.pages) pageByKey.set(page.key, page)
  }
  const pinned = uniqueKeys(prefs.pinned)
    .map(key => pageByKey.get(key))
    .filter((page): page is SidebarPageRef => Boolean(page))
  const pinnedKeySet = new Set(pinned.map(page => page.key))
  const parked = uniqueKeys(prefs.parked)
    .map(key => pageByKey.get(key))
    .filter((page): page is SidebarPageRef => page !== undefined && !pinnedKeySet.has(page.key))
  return { groups, pinned, parked }
}

export function buildSidebarLayout(
  navTree: PermissionAwareItem[],
  prefs: SidebarMenuPrefs,
): SidebarLayout {
  const model = buildSidebarCustomizeModel(navTree, prefs)
  const pinnedKeys = new Set(model.pinned.map(page => page.key))
  const parkedKeys = new Set(model.parked.map(page => page.key))
  const groups = model.groups.map(group => ({
    ...group,
    pages: group.pages.filter(page => !pinnedKeys.has(page.key) && !parkedKeys.has(page.key)),
  }))
  return { pinned: model.pinned, groups, parked: model.parked }
}

function buildRenderableItem(
  node: PermissionAwareItem,
  visibleKeys: Set<string>,
  pageRank: Map<string, number>,
): PermissionAwareItem | null {
  if (!node.children || node.children.length === 0) {
    return visibleKeys.has(node.key) ? node : null
  }
  const minRank = (item: PermissionAwareItem): number => {
    if (!item.children || item.children.length === 0) {
      return pageRank.get(item.key) ?? Number.POSITIVE_INFINITY
    }
    return Math.min(...item.children.map(minRank))
  }
  const children = node.children
    .map(child => buildRenderableItem(child, visibleKeys, pageRank))
    .filter((child): child is PermissionAwareItem => Boolean(child))
    .sort((a, b) => {
      const rankA = minRank(a)
      const rankB = minRank(b)
      if (rankA === rankB) return 0
      return rankA - rankB
    })
  if (children.length === 0) return null
  return { ...node, children }
}

export function buildSidebarEntries(
  layout: SidebarLayout,
  prefs: SidebarMenuPrefs,
): SidebarEntry[] {
  const entries: SidebarEntry[] = layout.pinned.map(page => ({
    kind: 'pinned',
    key: page.key,
    groupKey: page.groupKey,
    groupLabel: page.groupLabel,
    item: page.item,
  }))
  for (const group of layout.groups) {
    if (group.pages.length === 0) continue
    if (!group.item.children || group.item.children.length === 0) {
      entries.push({
        kind: 'module',
        key: group.key,
        groupKey: group.key,
        groupLabel: group.label,
        item: group.item,
      })
      continue
    }
    const visibleKeys = new Set(group.pages.map(page => page.key))
    const pageRank = new Map((prefs.pageOrder[group.key] || []).map((key, index) => [key, index]))
    const item = buildRenderableItem(group.item, visibleKeys, pageRank)
    if (item) {
      entries.push({
        kind: 'module',
        key: group.key,
        groupKey: group.key,
        groupLabel: group.label,
        item,
      })
    }
  }
  return entries
}

export function buildMoreSections(
  layout: SidebarLayout,
  overflowEntries: SidebarEntry[],
): SidebarMoreSection[] {
  const sections = new Map<string, SidebarMoreSection>()
  const pinnedOverflow = overflowEntries.filter(entry => entry.kind === 'pinned')
  if (pinnedOverflow.length > 0) {
    sections.set('__pinned__', {
      key: '__pinned__',
      label: '快捷入口',
      pages: pinnedOverflow.map(entry => ({
        item: entry.item,
        key: entry.key,
        groupKey: entry.groupKey,
        groupLabel: entry.groupLabel,
        pathLabels: [],
      })),
    })
  }
  const groupByKey = new Map(layout.groups.map(group => [group.key, group]))
  for (const entry of overflowEntries) {
    if (entry.kind !== 'module') continue
    const group = groupByKey.get(entry.groupKey)
    if (!group || group.pages.length === 0) continue
    sections.set(group.key, {
      key: group.key,
      label: group.label,
      pages: group.pages,
    })
  }
  for (const page of layout.parked) {
    const existing = sections.get(page.groupKey)
    if (existing) {
      existing.pages = [...existing.pages, page]
    } else {
      sections.set(page.groupKey, {
        key: page.groupKey,
        label: page.groupLabel,
        pages: [page],
      })
    }
  }
  const ordered: SidebarMoreSection[] = []
  const pinnedSection = sections.get('__pinned__')
  if (pinnedSection) ordered.push(pinnedSection)
  for (const group of layout.groups) {
    const section = sections.get(group.key)
    if (section) ordered.push(section)
  }
  for (const section of sections.values()) {
    if (!ordered.includes(section)) ordered.push(section)
  }
  return ordered.filter(section => section.pages.length > 0)
}

export function pinSidebarPage(prefs: SidebarMenuPrefs, key: string): SidebarMenuPrefs {
  return {
    ...prefs,
    pinned: [...prefs.pinned.filter(item => item !== key), key],
    parked: prefs.parked.filter(item => item !== key),
  }
}

export function parkSidebarPage(prefs: SidebarMenuPrefs, key: string): SidebarMenuPrefs {
  return {
    ...prefs,
    pinned: prefs.pinned.filter(item => item !== key),
    parked: [...prefs.parked.filter(item => item !== key), key],
  }
}

export function restoreSidebarPage(prefs: SidebarMenuPrefs, key: string): SidebarMenuPrefs {
  return {
    ...prefs,
    pinned: prefs.pinned.filter(item => item !== key),
    parked: prefs.parked.filter(item => item !== key),
  }
}

export function reorderKeys(keys: string[], fromKey: string, toKey: string): string[] {
  const from = keys.indexOf(fromKey)
  const to = keys.indexOf(toKey)
  if (from < 0 || to < 0 || from === to) return keys
  const next = keys.slice()
  next.splice(from, 1)
  next.splice(to, 0, fromKey)
  return next
}
