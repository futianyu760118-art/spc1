import { DatePicker, Input, InputNumber, Select } from 'antd'
import { registerWidget } from '../registry'
import type { WidgetProps } from '../types'

function TextWidget({ field }: WidgetProps) {
  return <Input placeholder={field.placeholder} allowClear />
}

function TextareaWidget({ field }: WidgetProps) {
  return <Input.TextArea rows={field.rows ?? 4} placeholder={field.placeholder} />
}

function NumberWidget({ field }: WidgetProps) {
  return (
    <InputNumber min={field.min ?? 0} precision={field.precision ?? 2}
      style={{ width: '100%' }} placeholder={field.placeholder} />
  )
}

function DateWidget({ field }: WidgetProps) {
  return <DatePicker style={{ width: '100%' }} placeholder={field.placeholder} />
}

function SelectWidget({ field }: WidgetProps) {
  return <Select options={field.options} placeholder={field.placeholder} allowClear />
}

registerWidget('text', TextWidget)
registerWidget('textarea', TextareaWidget)
registerWidget('number', NumberWidget)
registerWidget('date', DateWidget)
registerWidget('select', SelectWidget)
