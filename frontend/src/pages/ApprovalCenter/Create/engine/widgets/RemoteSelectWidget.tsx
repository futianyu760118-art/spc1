import { useState } from 'react'
import { Form, Select } from 'antd'
import { registerWidget, remoteRegistry } from '../registry'
import type { WidgetProps } from '../types'

function RemoteSelectWidget({ field, value, onChange }: WidgetProps) {
  const form = Form.useFormInstance()
  const [options, setOptions] = useState<any[]>([])
  const source = field.remote ? remoteRegistry[field.remote] : undefined

  const search = async (keyword: string) => {
    if (!keyword || !source) return
    try {
      const items = await source.search(keyword)
      setOptions(items.map(source.toOption))
    } catch { /* 全局拦截器已提示 */ }
  }

  return (
    <Select showSearch filterOption={false} allowClear value={value}
      placeholder={field.placeholder} onSearch={search}
      onChange={(v, opt) => {
        onChange?.(v)
        Object.entries(field.derive || {}).forEach(([target, sourceKey]) =>
          form.setFieldValue(target, (opt as any)?.[sourceKey]))
      }}
      options={options} />
  )
}

registerWidget('remote_select', RemoteSelectWidget)
