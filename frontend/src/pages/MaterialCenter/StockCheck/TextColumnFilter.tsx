import { Input, Button, Space } from 'antd'
import { FilterOutlined } from '@ant-design/icons'

interface TextColumnFilterProps {
  setSelectedKeys?: (keys: React.Key[]) => void
  selectedKeys?: React.Key[]
  confirm?: () => void
  clearFilters?: () => void
  close?: () => void
}

interface TextColumnFilterOptions {
  placeholder?: string
  width?: number
}

/**
 * 文本列筛选下拉工厂：返回一个 antd `filterDropdown`。
 *
 * 用法：
 *   filterDropdown: textColumnFilter({ placeholder: '输入盘点单号' }),
 *   filterIcon: textFilterIcon,
 *
 * 筛选值以 `string[]` 形式存入 column filter state（首元素为文本）；
 * 通过 `useAntTableQuery` 的 `filterToQuery` 在服务端用对应字段做 ILIKE 匹配。
 */
export function textColumnFilter(opts: TextColumnFilterOptions = {}) {
  const { placeholder = '输入筛选内容', width = 188 } = opts
  return function TextColumnFilterDropdown({
    setSelectedKeys, selectedKeys = [], confirm, clearFilters,
  }: TextColumnFilterProps) {
    return (
      <div style={{ padding: 8 }} onClick={(e) => e.stopPropagation()}>
        <Input
          autoFocus
          allowClear
          placeholder={placeholder}
          value={selectedKeys[0] as string | undefined}
          onChange={(e) => setSelectedKeys?.(e.target.value ? [e.target.value] : [])}
          onPressEnter={() => confirm?.()}
          style={{ width, marginBottom: 8, display: 'block' }}
        />
        <Space>
          <Button type="primary" size="small" onClick={() => confirm?.()}>筛选</Button>
          <Button
            size="small"
            onClick={() => {
              setSelectedKeys?.([])
              clearFilters?.()
              confirm?.()
            }}
          >
            重置
          </Button>
        </Space>
      </div>
    )
  }
}

export function textFilterIcon(filtered: boolean) {
  return <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />
}