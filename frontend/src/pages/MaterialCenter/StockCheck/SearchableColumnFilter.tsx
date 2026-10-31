import { useEffect, useMemo, useState } from 'react'
import { Input, Checkbox, Button, Space, Empty } from 'antd'
import { SearchOutlined } from '@ant-design/icons'

interface FilterOption {
  text: string
  value: string | number
}

interface Props {
  // Ant Design filterDropdown 注入的属性
  prefixCls?: string
  setSelectedKeys?: (keys: (string | number)[]) => void
  selectedKeys?: (string | number)[]
  confirm?: () => void
  clearFilters?: () => void
  close?: () => void
  filters?: FilterOption[]
  // 当前列的 dataIndex（用于 confirm 时上报）
  columnKey?: string
}

/**
 * 列筛选下拉：可在搜索框中按 text/value 过滤；
 * 过滤后仅剩 1 条时自动勾选，用户点击「确定」即应用该筛选。
 */
export default function SearchableColumnFilter({
  setSelectedKeys, selectedKeys = [], confirm, clearFilters, filters = [], close,
}: Props) {
  const [kw, setKw] = useState('')
  const [picked, setPicked] = useState<(string | number)[]>(selectedKeys)

  const filtered = useMemo(() => {
    const q = kw.trim().toLowerCase()
    if (!q) return filters
    return filters.filter(
      (f) =>
        String(f.text || '').toLowerCase().includes(q) ||
        String(f.value ?? '').toLowerCase().includes(q),
    )
  }, [filters, kw])

  // 搜索结果仅 1 条时自动勾选；多条/无条 不自动变更
  useEffect(() => {
    if (filtered.length === 1) {
      setPicked([filtered[0].value])
    } else if (filtered.length === 0) {
      setPicked([])
    }
  }, [filtered])

  const toggle = (v: string | number) => {
    setPicked((prev) =>
      prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v],
    )
  }

  const handleConfirm = () => {
    setSelectedKeys?.(picked)
    confirm?.()
  }

  const handleReset = () => {
    setPicked([])
    setKw('')
    setSelectedKeys?.([])
    clearFilters?.()
    confirm?.()
  }

  return (
    <div style={{ padding: 8, minWidth: 200 }} onClick={(e) => e.stopPropagation()}>
      <Input
        autoFocus
        allowClear
        prefix={<SearchOutlined />}
        placeholder="搜索筛选项"
        value={kw}
        onChange={(e) => setKw(e.target.value)}
        style={{ marginBottom: 8 }}
      />
      <div style={{ maxHeight: 220, overflowY: 'auto', marginBottom: 8 }}>
        {filtered.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无匹配项" />
        ) : (
          filtered.map((f) => (
            <label key={String(f.value)} style={{ display: 'flex', alignItems: 'center', padding: '3px 0', cursor: 'pointer' }}>
              <Checkbox
                checked={picked.includes(f.value)}
                onChange={() => toggle(f.value)}
                style={{ marginRight: 6 }}
              />
              <span>{f.text}</span>
            </label>
          ))
        )}
      </div>
      <Space>
        <Button size="small" onClick={handleReset}>重置</Button>
        <Button size="small" type="primary" onClick={handleConfirm}>确定</Button>
      </Space>
    </div>
  )
}