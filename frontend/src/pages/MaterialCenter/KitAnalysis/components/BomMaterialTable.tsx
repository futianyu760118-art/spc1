import React, { useEffect, useMemo, useState } from 'react'
import { Table, Tag, InputNumber, DatePicker, Space, Button, Popover, Checkbox } from 'antd'
import type { ColumnType, TablePaginationConfig } from 'antd/es/table'
import type { FilterConfirmProps } from 'antd/es/table/interface'
import { SettingOutlined, HolderOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import type { BomKitFlatItem } from '../index'

const MATERIAL_STATUS_COLOR: Record<string, string> = {
  not_in_plan: 'default',
  not_ordered: 'volcano',
  self_made_unlinked: 'blue',
  partial_received: 'warning',
  fully_received: 'success',
  overdue: 'error',
  pending: 'cyan',
  in_stock: 'green',
}

// 物料属性全量枚举(对应 material_property 1/2/3/5/6/7/8/9),不依赖当前数据是否齐全
const MATERIAL_PROPERTY_OPTIONS = [
  { text: '外购', value: '外购' },
  { text: '自制', value: '自制' },
  { text: '委外加工', value: '委外加工' },
  { text: '虚拟件', value: '虚拟件' },
  { text: '特征类', value: '特征类' },
  { text: '配置类', value: '配置类' },
  { text: '规划类', value: '规划类' },
  { text: '组装件', value: '组装件' },
]

// 物料齐套状态全量枚举,value 为后端 status code,text 为中文标签
const MATERIAL_STATUS_OPTIONS = [
  { text: 'BOM 有 / 计划无', value: 'not_in_plan' },
  { text: '未下单', value: 'not_ordered' },
  { text: '自制未排产/未关联', value: 'self_made_unlinked' },
  { text: '待到料', value: 'pending' },
  { text: '逾期未到', value: 'overdue' },
  { text: '部分到', value: 'partial_received' },
  { text: '已到齐', value: 'fully_received' },
  { text: '有库存', value: 'in_stock' },
]

// MRP 关闭标志 / 关闭类型 全量枚举
const MRP_CLOSED_OPTIONS = [
  { text: '未关闭', value: 0 },
  { text: '已关闭', value: 1 },
]
const MRP_CLOSE_TYPE_OPTIONS = [
  { text: '投放关闭', value: 0 },
  { text: '手工关闭', value: 1 },
  { text: '强制关闭', value: 2 },
  { text: '反关闭', value: 3 },
]

// 可配置列的元数据(层级列固定在最前,不参与配置)
const CONFIGURABLE_COLUMNS: { key: string; title: string }[] = [
  { key: 'material_code', title: '物料编码' },
  { key: 'material_name', title: '物料名称' },
  { key: 'material_property_label', title: '属性' },
  { key: 'material_type', title: '分类' },
  { key: 'unit_name', title: '单位' },
  { key: 'standard_qty', title: 'BOM 用量' },
  { key: 'req_qty', title: '需求量' },
  { key: 'stock_qty', title: '即时库存' },
  { key: 'transit_qty', title: '在途' },
  { key: 'received_qty', title: '已收' },
  { key: 'shortage_qty', title: '短缺' },
  { key: 'eta', title: 'ETA' },
  { key: 'mrp_is_closed', title: 'MRP关闭' },
  { key: 'mrp_close_type', title: '关闭类型' },
  { key: 'supplier_name', title: '供应商' },
  { key: 'status', title: '状态' },
]
const COLUMN_SETTINGS_STORAGE_KEY = 'bom_material_table_column_settings'
const DEFAULT_COLUMN_ORDER = CONFIGURABLE_COLUMNS.map((c) => c.key)

const fmt = (v: number | null | undefined) =>
  v == null ? '-' : Number(v).toLocaleString()

const NumberRangeFilter: React.FC<{
  dataIndex: string
  onConfirm: (min?: number, max?: number) => void
  onReset: () => void
  confirm: (param?: FilterConfirmProps) => void
}> = ({ onConfirm, onReset, confirm }) => {
  const [min, setMin] = useState<number | null>(null)
  const [max, setMax] = useState<number | null>(null)
  return (
    <div style={{ padding: 8, width: 220 }} onClick={(e) => e.stopPropagation()}>
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <InputNumber
          placeholder="最小值"
          value={min}
          onChange={(v) => setMin(v as number | null)}
          style={{ width: '100%' }}
        />
        <InputNumber
          placeholder="最大值"
          value={max}
          onChange={(v) => setMax(v as number | null)}
          style={{ width: '100%' }}
        />
        <Space>
          <Button
            type="primary"
            size="small"
            onClick={() => {
              onConfirm(min ?? undefined, max ?? undefined)
              confirm()
            }}
          >
            确定
          </Button>
          <Button
            size="small"
            onClick={() => {
              setMin(null)
              setMax(null)
              onReset()
              confirm()
            }}
          >
            重置
          </Button>
        </Space>
      </Space>
    </div>
  )
}

const DateRangeFilter: React.FC<{
  onConfirm: (start?: string, end?: string) => void
  onReset: () => void
  confirm: (param?: FilterConfirmProps) => void
}> = ({ onConfirm, onReset, confirm }) => {
  const [range, setRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null)
  return (
    <div style={{ padding: 8, width: 260 }} onClick={(e) => e.stopPropagation()}>
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <DatePicker.RangePicker
          value={range as any}
          onChange={(v) => setRange(v as any)}
          style={{ width: '100%' }}
        />
        <Space>
          <Button
            type="primary"
            size="small"
            onClick={() => {
              const start = range?.[0]?.format('YYYY-MM-DD')
              const end = range?.[1]?.format('YYYY-MM-DD')
              onConfirm(start, end)
              confirm()
            }}
          >
            确定
          </Button>
          <Button
            size="small"
            onClick={() => {
              setRange(null)
              onReset()
              confirm()
            }}
          >
            重置
          </Button>
        </Space>
      </Space>
    </div>
  )
}

interface Props {
  items: BomKitFlatItem[]
  loading?: boolean
}

const ColumnSettingsPanel: React.FC<{
  order: string[]
  hidden: string[]
  onToggle: (key: string) => void
  onReorder: (from: number, to: number) => void
  onReset: () => void
}> = ({ order, hidden, onToggle, onReorder, onReset }) => {
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)

  return (
    <div style={{ width: 260, maxHeight: 420, overflowY: 'auto', padding: 4 }}>
      <div style={{ marginBottom: 8, fontWeight: 600, fontSize: 13 }}>
        列设置
        <span style={{ fontWeight: 400, color: '#999', fontSize: 12 }}>
          （层级固定在最前，拖动⠿调序）
        </span>
      </div>
      {order.map((key, idx) => {
        const meta = CONFIGURABLE_COLUMNS.find((m) => m.key === key)
        if (!meta) return null
        const visible = !hidden.includes(key)
        const isDragging = dragIndex === idx
        const isOverTarget = overIndex === idx && dragIndex !== null && dragIndex !== idx
        return (
          <div
            key={key}
            onDragOver={(e) => {
              e.preventDefault()
              e.dataTransfer.dropEffect = 'move'
              if (overIndex !== idx) setOverIndex(idx)
            }}
            onDrop={(e) => {
              e.preventDefault()
              if (dragIndex !== null && dragIndex !== idx) {
                onReorder(dragIndex, idx)
              }
              setDragIndex(null)
              setOverIndex(null)
            }}
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: '4px 8px',
              fontSize: 13,
              borderRadius: 4,
              marginBottom: 2,
              border: isOverTarget
                ? '1px dashed #1890ff'
                : '1px solid transparent',
              background: isDragging ? '#f5f5f5' : isOverTarget ? '#e6f7ff' : 'transparent',
              opacity: isDragging ? 0.4 : 1,
              transition: 'border-color 0.1s, background 0.1s',
            }}
          >
            <span
              draggable
              onDragStart={(e) => {
                setDragIndex(idx)
                e.dataTransfer.effectAllowed = 'move'
              }}
              onDragEnd={() => {
                setDragIndex(null)
                setOverIndex(null)
              }}
              style={{ cursor: 'grab', padding: '0 6px 0 2px', color: '#bbb', lineHeight: 1 }}
              title="拖动调序"
            >
              <HolderOutlined />
            </span>
            <Checkbox checked={visible} onChange={() => onToggle(key)}>
              {meta.title}
            </Checkbox>
          </div>
        )
      })}
      <div style={{ marginTop: 8, borderTop: '1px solid #f0f0f0', paddingTop: 8 }}>
        <Button size="small" onClick={onReset}>
          重置默认
        </Button>
      </div>
    </div>
  )
}

const BomMaterialTable: React.FC<Props> = ({ items, loading }) => {
  const [filters, setFilters] = useState<Record<string, (string | number | null)[]>>({})
  const [sortInfo, setSortInfo] = useState<{ columnKey?: string; order?: 'ascend' | 'descend' }>({})

  // 列设置:显隐 + 排序,持久化到 localStorage
  const [columnOrder, setColumnOrder] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem(COLUMN_SETTINGS_STORAGE_KEY + '_order')
      const parsed = saved ? JSON.parse(saved) : null
      if (Array.isArray(parsed) && parsed.length > 0) return parsed
    } catch {
      /* noop */
    }
    return DEFAULT_COLUMN_ORDER
  })
  const [hiddenColumns, setHiddenColumns] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem(COLUMN_SETTINGS_STORAGE_KEY + '_hidden')
      const parsed = saved ? JSON.parse(saved) : null
      if (Array.isArray(parsed)) return parsed
    } catch {
      /* noop */
    }
    return []
  })
  useEffect(() => {
    localStorage.setItem(COLUMN_SETTINGS_STORAGE_KEY + '_order', JSON.stringify(columnOrder))
  }, [columnOrder])
  useEffect(() => {
    localStorage.setItem(COLUMN_SETTINGS_STORAGE_KEY + '_hidden', JSON.stringify(hiddenColumns))
  }, [hiddenColumns])

  const handleToggleColumn = (key: string) =>
    setHiddenColumns((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key],
    )
  const handleReorderColumns = (from: number, to: number) =>
    setColumnOrder((prev) => {
      if (from < 0 || from >= prev.length || to < 0 || to >= prev.length || from === to) {
        return prev
      }
      const next = [...prev]
      const [moved] = next.splice(from, 1)
      next.splice(to, 0, moved)
      return next
    })
  const handleResetColumns = () => {
    setColumnOrder(DEFAULT_COLUMN_ORDER)
    setHiddenColumns([])
  }

  const textFilterOptions = useMemo(() => {
    const build = (key: keyof BomKitFlatItem) => {
      const set = new Set<string>()
      items.forEach((it) => {
        const v = it[key]
        if (v != null && v !== '') set.add(String(v))
      })
      return Array.from(set)
        .sort((a, b) => a.localeCompare(b))
        .map((v) => ({ text: v, value: v }))
    }
    return {
      material_code: build('material_code'),
      material_name: build('material_name'),
      material_type: build('material_type'),
      supplier_name: build('supplier_name'),
    }
  }, [items])

  const columns = useMemo<ColumnType<BomKitFlatItem>[]>(() => {
    const numRange = (dataIndex: keyof BomKitFlatItem): ColumnType<BomKitFlatItem> => {
      const key = String(dataIndex)
      return {
        title: '',
        dataIndex: key as any,
        key,
        sorter: (a, b) => {
          const av = (a as any)[dataIndex] ?? -Infinity
          const bv = (b as any)[dataIndex] ?? -Infinity
          return Number(av) - Number(bv)
        },
        filteredValue: filters[key] as any,
        filterDropdown: (props) => (
          <NumberRangeFilter
            dataIndex={key}
            confirm={props.confirm}
            onConfirm={(min, max) =>
              setFilters((prev) => ({ ...prev, [key]: [min ?? null, max ?? null] }))
            }
            onReset={() =>
              setFilters((prev) => {
                const cp = { ...prev }
                delete cp[key]
                return cp
              })
            }
          />
        ),
        render: fmt,
      }
    }

    const textCol = (
      title: string,
      dataIndex: keyof BomKitFlatItem,
      width: number,
      optsKey: keyof typeof textFilterOptions,
    ): ColumnType<BomKitFlatItem> => ({
      title,
      dataIndex: dataIndex as any,
      key: String(dataIndex),
      width,
      sorter: (a, b) =>
        String((a as any)[dataIndex] ?? '').localeCompare(String((b as any)[dataIndex] ?? '')),
      filters: textFilterOptions[optsKey],
      filterSearch: true,
      onFilter: (value, record) => String((record as any)[dataIndex] ?? '') === String(value),
      render: (v: any) => (v == null || v === '' ? <span style={{ color: '#ccc' }}>-</span> : v),
    })

    return [
      {
        title: '层级',
        dataIndex: 'level',
        key: 'level',
        width: 60,
        sorter: (a, b) => (a.level ?? 0) - (b.level ?? 0),
        render: (lv: number) => `L${lv}`,
      },
      textCol('物料编码', 'material_code', 140, 'material_code'),
      textCol('物料名称', 'material_name', 160, 'material_name'),
      {
        title: '属性',
        dataIndex: 'material_property_label',
        key: 'material_property_label',
        width: 90,
        sorter: (a, b) =>
          String(a.material_property_label ?? '').localeCompare(String(b.material_property_label ?? '')),
        filters: MATERIAL_PROPERTY_OPTIONS,
        filterSearch: true,
        onFilter: (value, record) => String(record.material_property_label ?? '') === String(value),
        render: (v: any) => (v == null || v === '' ? <span style={{ color: '#ccc' }}>-</span> : v),
      },
      textCol('分类', 'material_type', 100, 'material_type'),
      {
        title: '单位',
        dataIndex: 'unit_name',
        key: 'unit_name',
        width: 70,
        sorter: (a, b) => String(a.unit_name ?? '').localeCompare(String(b.unit_name ?? '')),
        render: (v: any) => (v == null || v === '' ? <span style={{ color: '#ccc' }}>-</span> : v),
      },
      { ...numRange('standard_qty'), title: 'BOM 用量', width: 90, align: 'right' as const },
      { ...numRange('req_qty'), title: '需求量', width: 90, align: 'right' as const },
      { ...numRange('stock_qty'), title: '即时库存', width: 90, align: 'right' as const },
      { ...numRange('transit_qty'), title: '在途', width: 80, align: 'right' as const },
      { ...numRange('received_qty'), title: '已收', width: 90, align: 'right' as const },
      {
        ...numRange('shortage_qty'),
        title: '短缺',
        width: 90,
        align: 'right' as const,
        render: (v: number | null) =>
          v != null && v > 0 ? (
            <span style={{ color: '#cf1322', fontWeight: 600 }}>{fmt(v)}</span>
          ) : (
            fmt(v)
          ),
      },
      {
        title: 'ETA',
        dataIndex: 'eta',
        key: 'eta',
        width: 100,
        sorter: (a, b) => String(a.eta ?? '').localeCompare(String(b.eta ?? '')),
        filteredValue: filters['eta'] as any,
        filterDropdown: (props) => (
          <DateRangeFilter
            confirm={props.confirm}
            onConfirm={(start, end) =>
              setFilters((prev) => ({ ...prev, eta: [start ?? null, end ?? null] }))
            }
            onReset={() =>
              setFilters((prev) => {
                const cp = { ...prev }
                delete cp.eta
                return cp
              })
            }
          />
        ),
        render: (v: string | null) => (v ? v : <span style={{ color: '#ccc' }}>-</span>),
      },
      {
        title: 'MRP关闭',
        dataIndex: 'mrp_is_closed',
        key: 'mrp_is_closed',
        width: 90,
        align: 'center' as const,
        sorter: (a, b) => (a.mrp_is_closed ?? 0) - (b.mrp_is_closed ?? 0),
        filters: MRP_CLOSED_OPTIONS,
        onFilter: (value, record) => Number(record.mrp_is_closed ?? 0) === Number(value),
        render: (v: number) =>
          v === 1 ? (
            <Tag color="default">已关闭</Tag>
          ) : (
            <span style={{ color: '#ccc' }}>未关闭</span>
          ),
      },
      {
        title: '关闭类型',
        dataIndex: 'mrp_close_type',
        key: 'mrp_close_type',
        width: 90,
        align: 'center' as const,
        sorter: (a, b) => (a.mrp_close_type ?? -1) - (b.mrp_close_type ?? -1),
        filters: MRP_CLOSE_TYPE_OPTIONS,
        onFilter: (value, record) => Number(record.mrp_close_type ?? -999) === Number(value),
        render: (v: number | null) => {
          if (v === null || v === undefined) return <span style={{ color: '#ccc' }}>-</span>
          const opt = MRP_CLOSE_TYPE_OPTIONS.find((o) => o.value === v)
          return opt ? <Tag>{opt.text}</Tag> : <span style={{ color: '#ccc' }}>{v}</span>
        },
      },
      textCol('供应商', 'supplier_name', 120, 'supplier_name'),
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 100,
        sorter: (a, b) => String(a.status ?? '').localeCompare(String(b.status ?? '')),
        filters: MATERIAL_STATUS_OPTIONS,
        filterSearch: true,
        onFilter: (value, record) => record.status === String(value),
        render: (s: string, row: BomKitFlatItem) => {
          if (s === 'not_in_plan') return <Tag>BOM 有 / 计划无</Tag>
          const label = row.status_label || s
          return <Tag color={MATERIAL_STATUS_COLOR[s] || 'default'}>{label}</Tag>
        },
      },
    ] as ColumnType<BomKitFlatItem>[]
  }, [textFilterOptions, filters])

  // 按用户设置(显隐+顺序)过滤列。层级列固定在最前。
  const visibleColumns = useMemo(() => {
    const byKey: Record<string, ColumnType<BomKitFlatItem>> = {}
    for (const c of columns) {
      if (c.key) byKey[c.key as string] = c
    }
    const levelCol = byKey['level']
    const rest: ColumnType<BomKitFlatItem>[] = columnOrder
      .filter((k) => !hiddenColumns.includes(k) && byKey[k])
      .map((k) => byKey[k])
    return [levelCol, ...rest].filter(Boolean) as ColumnType<BomKitFlatItem>[]
  }, [columns, columnOrder, hiddenColumns])

  const dataSource = useMemo(() => {
    let arr = items
    const NUMERIC_KEYS = new Set([
      'standard_qty',
      'req_qty',
      'stock_qty',
      'transit_qty',
      'received_qty',
      'shortage_qty',
    ])
    Object.entries(filters).forEach(([key, vals]) => {
      if (vals == null) return
      if (NUMERIC_KEYS.has(key)) {
        const [min, max] = vals as (number | null)[]
        arr = arr.filter((it) => {
          const v = (it as any)[key]
          if (v == null) return min == null && max == null
          if (min != null && Number(v) < Number(min)) return false
          if (max != null && Number(v) > Number(max)) return false
          return true
        })
        return
      }
      if (key === 'eta') {
        const [start, end] = vals as (string | null)[]
        arr = arr.filter((it) => {
          if (!it.eta) return false
          if (start && it.eta < start) return false
          if (end && it.eta > end) return false
          return true
        })
      }
    })
    if (sortInfo.columnKey && sortInfo.order) {
      const k = sortInfo.columnKey
      const dir = sortInfo.order === 'ascend' ? 1 : -1
      arr = [...arr].sort((a, b) => {
        const av = (a as any)[k]
        const bv = (b as any)[k]
        if (av == null && bv == null) return 0
        if (av == null) return -1 * dir
        if (bv == null) return 1 * dir
        if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir
        return String(av).localeCompare(String(bv)) * dir
      })
    }
    return arr
  }, [items, filters, sortInfo])

  return (
    <div style={{ flex: 1, minWidth: 0, paddingLeft: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <div
          style={{
            background: '#e6f7ff',
            border: '1px solid #91d5ff',
            padding: '6px 10px',
            borderRadius: 4,
            fontSize: 12,
            color: '#0050b3',
            flex: 1,
            marginRight: 8,
          }}
        >
          齐套数字为<b>订单级聚合</b>(来源 MRP/PO/库存),跨产品不累加;BOM 仅作结构展示
        </div>
        <Popover
          trigger="click"
          placement="bottomRight"
          content={
            <ColumnSettingsPanel
              order={columnOrder}
              hidden={hiddenColumns}
              onToggle={handleToggleColumn}
              onReorder={handleReorderColumns}
              onReset={handleResetColumns}
            />
          }
        >
          <Button icon={<SettingOutlined />} size="small">
            列设置
          </Button>
        </Popover>
      </div>
      <Table<BomKitFlatItem>
        rowKey={(r) =>
          `${r.bom_id || ''}-${r.material_code || ''}-${r.level}-${r.parent_bom_id || ''}-${r.status || ''}`
        }
        dataSource={dataSource}
        columns={visibleColumns}
        size="small"
        pagination={false}
        loading={loading}
        scroll={{ x: 1580, y: 360 }}
        onChange={(pagination: TablePaginationConfig, _filters, sorter: any) => {
          setSortInfo({ columnKey: sorter?.columnKey, order: sorter?.order })
        }}
      />
    </div>
  )
}

export default BomMaterialTable