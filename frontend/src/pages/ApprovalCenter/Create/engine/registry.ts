import type { ComponentType } from 'react'
import type { PanelComponent, WidgetProps } from './types'

export interface RemoteSource {
  search(keyword: string): Promise<any[]>
  toOption(item: any): { value: any; label: string } & Record<string, any>
}

export const widgetRegistry: Record<string, ComponentType<WidgetProps>> = {}
export const remoteRegistry: Record<string, RemoteSource> = {}
export const componentRegistry: Record<string, PanelComponent> = {}

export function registerWidget(kind: string, component: ComponentType<WidgetProps>): void {
  widgetRegistry[kind] = component
}

export function getWidget(kind: string): ComponentType<WidgetProps> | undefined {
  return widgetRegistry[kind]
}

export function registerRemote(name: string, source: RemoteSource): void {
  remoteRegistry[name] = source
}

export function registerPanel(name: string, component: PanelComponent): void {
  componentRegistry[name] = component
}
