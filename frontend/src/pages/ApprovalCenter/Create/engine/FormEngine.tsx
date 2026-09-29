import { Card, Form, Input } from 'antd'
import type { FormInstance } from 'antd'
import { componentRegistry, getWidget } from './registry'
import type { FormField, FormSchema } from './types'
import './widgets'
import './remotes'

function detailGridValidator(field: FormField) {
  return async (_: any, value: any) => {
    const rows: any[] = Array.isArray(value) ? value : []
    if (!rows.length) throw new Error(`请至少添加一行${field.label}`)
    for (let i = 0; i < rows.length; i++) {
      for (const col of field.columns || []) {
        const raw = rows[i]?.[col.key]
        if (col.required && (raw === undefined || raw === null || raw === '')) {
          throw new Error(`第 ${i + 1} 行「${col.label}」不能为空`)
        }
        if (col.positive && !(Number(raw) > 0)) {
          throw new Error(`第 ${i + 1} 行「${col.label}」必须大于 0`)
        }
      }
    }
  }
}

function buildRules(field: FormField): any[] {
  if (field.widget === 'checkbox_cards') {
    return field.required ? [{
      validator: async (_: any, v: any) => {
        if (!Array.isArray(v) || v.length === 0) throw new Error(`请至少选择一项${field.label}`)
      },
    }] : []
  }
  if (field.widget === 'detail_grid') {
    return field.required ? [{ validator: detailGridValidator(field) }] : []
  }
  return field.required ? [{ required: true, message: `请填写${field.label}` }] : []
}

function FieldRenderer({ field, form }: { field: FormField; form: FormInstance }) {
  if (field.widget === 'custom') {
    const Panel = field.component ? componentRegistry[field.component] : undefined
    return Panel ? <Panel form={form} /> : null
  }
  if (field.hidden) {
    return <Form.Item name={field.key} hidden><Input /></Form.Item>
  }
  const spanStyle = field.span === 2 ? { gridColumn: '1 / -1' } : undefined
  if (field.widget === 'upload') {
    const Widget = getWidget('upload')
    return (
      <Form.Item name={field.key} label={field.label} valuePropName="fileList"
        extra={field.extra} style={spanStyle}>
        {Widget ? <Widget field={field} /> : null}
      </Form.Item>
    )
  }
  const Widget = getWidget(field.widget)
  return (
    <Form.Item name={field.key} label={field.label} rules={buildRules(field)}
      extra={field.extra} style={spanStyle}>
      {Widget ? <Widget field={field} /> : <Input disabled placeholder={`未注册控件：${field.widget}`} />}
    </Form.Item>
  )
}

export default function FormEngine({ schema, form }: { schema: FormSchema; form: FormInstance }) {
  const Aside = schema.aside ? componentRegistry[schema.aside.component] : undefined
  const content = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
      {schema.sections.map((section, index) => (
        <Card key={index} title={section.title} styles={{ body: { paddingTop: 8 } }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0 16px' }}>
            {section.fields.map(field => <FieldRenderer key={field.key} field={field} form={form} />)}
          </div>
        </Card>
      ))}
    </div>
  )
  return (
    <Form form={form} layout="vertical">
      {schema.aside && Aside ? (
        <div className="clm-form-grid">
          {content}
          <div className="clm-sticky">
            <Card title={schema.aside.title} styles={{ body: { padding: 12, background: '#f8fafc' } }}>
              <Aside form={form} />
            </Card>
          </div>
        </div>
      ) : content}
    </Form>
  )
}
