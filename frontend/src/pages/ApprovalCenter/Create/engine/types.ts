import type { ComponentType } from 'react'
import type { FormInstance } from 'antd'

export type WidgetKind =
  | 'text' | 'textarea' | 'number' | 'date' | 'select'
  | 'radio_cards' | 'checkbox_cards'
  | 'remote_select' | 'upload' | 'detail_grid' | 'custom'

export interface FieldOption { value: string; label: string }

export interface FormField {
  key: string
  label: string
  widget: WidgetKind
  required?: boolean
  hidden?: boolean
  placeholder?: string
  extra?: string
  options?: FieldOption[]
  remote?: string
  columns?: FormField[]
  component?: string
  span?: 1 | 2
  rows?: number
  min?: number
  precision?: number
  positive?: boolean
  width?: number
  uploadNamespace?: string
  derive?: Record<string, string>
}

export interface FormSection { title?: string; fields: FormField[] }

export interface FormSchema {
  bizType: string
  title: string
  sections: FormSection[]
  aside?: { component: string; title?: string }
  actions: { draft?: boolean; submit: boolean }
}

export interface CreateAdapter {
  initialValues?: Record<string, any>
  loadForEdit(id: number): Promise<Record<string, any>>
  saveDraft(values: Record<string, any>, editId?: number): Promise<{ id: number }>
  submit(values: Record<string, any>, editId?: number): Promise<{ id: number }>
}

export interface CreateBusinessEntry {
  bizType: string
  name: string
  description: string
  permission: [string, string]
  schema: FormSchema
  adapter: CreateAdapter
}

export interface WidgetProps {
  field: FormField
  value?: any
  fileList?: any[]
  onChange?: (v: any) => void
}

export type PanelComponent = ComponentType<{ form: FormInstance }>
