import React, { useMemo, useState } from 'react'
import { Table, Tag, InputNumber, DatePicker, Space, Button } from 'antd'
import type { ColumnType, TablePaginationConfig } from 'antd/es/table'
import type { FilterConfirmProps } from 'antd/es/table/interface'
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

const BomMaterialTable: React.FC<Props> = ({ items, loading }) => {
  const [filters, setFilters] = useState<Record<string, (string | number | null)[]>>({})
  const [sortInfo, setSortInfo] = useState<{ columnKey?: string; order?: 'ascend' | 'descend' }>({})

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
      material_property_label: build('material_property_label'),
      supplier_name: build('supplier_name'),
      status: build('status'),
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
      filteredValue: filters[String(dataIndex)] as any,
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
      textCol('属性', 'material_property_label', 80, 'material_property_label'),
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
      textCol('供应商', 'supplier_name', 120, 'supplier_name'),
      {
        title: '状态',
        dataIndex: 'status',
        key: 'status',
        width: 100,
        sorter: (a, b) => String(a.status ?? '').localeCompare(String(b.status ?? '')),
        filters: textFilterOptions.status,
        filteredValue: filters['status'] as any,
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

  const dataSource = useMemo(() => {
    let arr = items
    Object.entries(filters).forEach(([key, vals]) => {
      if (vals == null) return
      if (
        key === 'standard_qty' ||
        key === 'req_qty' ||
        key === 'stock_qty' ||
        key === 'transit_qty' ||
        key === 'received_qty' ||
        key === 'shortage_qty'
      ) {
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
        return
      }
      if (Array.isArray(vals) && vals.length > 0) {
        const set = new Set(vals.map(String))
        arr = arr.filter((it) => set.has(String((it as any)[key] ?? '')))
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
      <div
        style={{
          background: '#e6f7ff',
          border: '1px solid #91d5ff',
          padding: '6px 10px',
          borderRadius: 4,
          fontSize: 12,
          color: '#0050b3',
          marginBottom: 8,
        }}
      >
        齐套数字为<b>订单级聚合</b>(来源 MRP/PO/库存),跨产品不累加;BOM 仅作结构展示
      </div>
      <Table<BomKitFlatItem>
        rowKey={(r) =>
          `${r.bom_id || ''}-${r.material_code || ''}-${r.level}-${r.parent_bom_id || ''}-${r.status || ''}`
        }
        dataSource={dataSource}
        columns={columns}
        size="small"
        pagination={false}
        loading={loading}
        scroll={{ x: 1300, y: 360 }}
        onChange={(pagination: TablePaginationConfig, _filters, sorter: any) => {
          setSortInfo({ columnKey: sorter?.columnKey, order: sorter?.order })
        }}
      />
    </div>
  )
}

export default BomMaterialTable