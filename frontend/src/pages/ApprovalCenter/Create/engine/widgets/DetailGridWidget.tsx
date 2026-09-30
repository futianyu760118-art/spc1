import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, DatePicker, Input, InputNumber, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { registerWidget } from '../registry'
import type { FormField, WidgetProps } from '../types'

function renderCell(col: FormField, row: any, setCell: (v: any) => void) {
  switch (col.widget) {
    case 'number':
      return (
        <InputNumber min={col.min ?? 0} precision={col.precision ?? 2} style={{ width: '100%' }}
          placeholder={col.placeholder} value={row?.[col.key] ?? null} onChange={v => setCell(v)} />
      )
    case 'date':
      return (
        <DatePicker style={{ width: '100%' }} value={row?.[col.key] ?? null} onChange={v => setCell(v)} />
      )
    default:
      return (
        <Input placeholder={col.placeholder} value={row?.[col.key] ?? ''}
          onChange={e => setCell(e.target.value)} />
      )
  }
}

function DetailGridWidget({ field, value, onChange }: WidgetProps) {
  const rows: any[] = Array.isArray(value) ? value : []
  const updateCell = (index: number, key: string, v: any) =>
    onChange?.(rows.map((row, i) => (i === index ? { ...row, [key]: v } : row)))

  const columns: ColumnsType<any> = [
    ...(field.columns || []).map(col => ({
      title: col.label,
      dataIndex: col.key,
      width: col.width ?? 160,
      render: (_: any, row: any) => {
        const index = rows.indexOf(row)
        return renderCell(col, row, v => updateCell(index, col.key, v))
      },
    })),
    {
      title: '',
      dataIndex: '_op',
      width: 46,
      align: 'center' as const,
      render: (_: any, row: any) => (
        <Button type="text" danger icon={<DeleteOutlined />} disabled={rows.length <= 1}
          onClick={() => onChange?.(rows.filter(r => r !== row))} />
      ),
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', marginBottom: 8 }}>
        <Button size="small" type="link" icon={<PlusOutlined />} style={{ marginLeft: 'auto' }}
          onClick={() => onChange?.([...rows, {}])}>添加行</Button>
      </div>
      <Table rowKey={(_: any, index?: number) => String(index)} size="small" pagination={false}
        columns={columns} dataSource={rows} />
    </div>
  )
}

registerWidget('detail_grid', DetailGridWidget)
