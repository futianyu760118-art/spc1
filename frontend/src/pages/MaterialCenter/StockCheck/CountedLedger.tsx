import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Space, Input, Select, DatePicker, Table, Tag, Typography, Button } from 'antd'
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons'
import { materialApi } from '@/services/api'
import { useAntTableQuery } from '@/hooks/useAntTableQuery'

const { RangePicker } = DatePicker

interface LedgerRow {
  check_id?: number | null
  check_no?: string | null
  check_date?: string | null
  check_type?: string | null
  status?: string | null
  material_id?: number | null
  material_code?: string | null
  material_name?: string | null
  spec_model?: string | null
  unit?: string | null
  wh_id?: number | null
  wh_name?: string | null
  system_qty?: number | null
  system_qty_time?: string | null
  live_qty?: number | null
  actual_qty?: number | null
  diff_qty?: number | null
  counted_by?: string | null
  counted_at?: string | null
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  open: { label: '待盘点', color: 'default' },
  in_progress: { label: '进行中', color: 'processing' },
  completed: { label: '已完成', color: 'success' },
  cancelled: { label: '已取消', color: 'error' },
}

const LEDGER_STATUS_OPTIONS = [
  { text: '待盘点', value: 'open' },
  { text: '进行中', value: 'in_progress' },
  { text: '已完成', value: 'completed' },
]

const CHECK_TYPE_MAP: Record<string, string> = {
  order: '订单盘点',
  manual: '手动盘点',
  cycle_count: '周期盘点',
}

function rowKey(row: LedgerRow): string {
  return `${row.material_id ?? 'x'}|${row.wh_id ?? 'none'}`
}

function fmtNum(v: number | null | undefined): string {
  return v == null ? '—' : Number(v).toFixed(2)
}

export default function CountedLedgerPanel() {
  const navigate = useNavigate()
  const [whFilter, setWhFilter] = useState('')
  const [checkType, setCheckType] = useState<string>()
  const [dateRange, setDateRange] = useState<[string, string] | undefined>()

  const { data, loading, total, searchInput, tableProps, reload, filters } = useAntTableQuery({
    fetchData: async (params) => {
      const res: any = await materialApi.listCountedMaterials({
        ...params,
        wh_id: whFilter || undefined,
        check_type: checkType || undefined,
        date_from: dateRange?.[0],
        date_to: dateRange?.[1],
      })
      return { items: res?.data?.items || [], total: Number(res?.data?.total || 0) }
    },
    initialKeyword: '',
    filterToQuery: (filters) => ({
      status: (filters.status as string[] | undefined)?.join(','),
    }),
    extraDeps: [whFilter, checkType, dateRange],
  })

  const columns = [
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 150, sorter: true },
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name', width: 200, sorter: true, ellipsis: true },
    { title: '规格', dataIndex: 'spec_model', key: 'spec_model', width: 180, sorter: true, ellipsis: true },
    { title: '单位', dataIndex: 'unit', key: 'unit', width: 70, sorter: true },
    { title: '仓库', dataIndex: 'wh_name', key: 'wh_name', width: 130, sorter: true, render: (v: string | null | undefined) => v || '—' },
    {
      title: '即时库存', dataIndex: 'live_qty', key: 'live_qty', width: 100, align: 'right' as const,
      render: fmtNum,
    },
    {
      title: '快照库存', dataIndex: 'system_qty', key: 'system_qty', width: 130, sorter: true, align: 'right' as const,
      render: (v: number | null | undefined, r: LedgerRow) => (
        <div>
          <div>{fmtNum(v)}</div>
          {r.system_qty_time ? (
            <div style={{ fontSize: 12, color: '#94a3b8' }}>{new Date(r.system_qty_time).toLocaleString()}</div>
          ) : null}
        </div>
      ),
    },
    {
      title: '盘点数', dataIndex: 'actual_qty', key: 'actual_qty', width: 100, sorter: true, align: 'right' as const,
      render: fmtNum,
    },
    {
      title: '差异', dataIndex: 'diff_qty', key: 'diff_qty', width: 100, sorter: true, align: 'right' as const,
      render: (v: number | null | undefined) => {
        if (v == null) return '—'
        const n = Number(v)
        const color = n > 0 ? '#52c41a' : n < 0 ? '#f5222d' : '#666'
        return <span style={{ color, fontWeight: 600 }}>{n > 0 ? '+' : ''}{n.toFixed(2)}</span>
      },
    },
    {
      title: '盘点单号', dataIndex: 'check_no', key: 'check_no', width: 160, sorter: true,
      render: (v: string | null | undefined, r: LedgerRow) =>
        v && r.check_id ? (
          <Typography.Link onClick={() => navigate(`/stock-check?checkId=${r.check_id}`)}>{v}</Typography.Link>
        ) : (v || '—'),
    },
    { title: '盘点日期', dataIndex: 'check_date', key: 'check_date', width: 110, sorter: true },
    { title: '盘点人', dataIndex: 'counted_by', key: 'counted_by', width: 100, sorter: true, render: (v: string | null | undefined) => v || '—' },
    {
      title: '盘点时间', dataIndex: 'counted_at', key: 'counted_at', width: 160, sorter: true,
      render: (v: string | null | undefined) => (v ? new Date(v).toLocaleString() : '—'),
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', width: 100, sorter: true,
      filters: LEDGER_STATUS_OPTIONS,
      filteredValue: (filters.status as string[] | undefined) ?? null,
      render: (v: string | null | undefined) => {
        const s = STATUS_MAP[v || '']
        return s ? <Tag color={s.color}>{s.label}</Tag> : (v || '—')
      },
    },
  ]

  return (
    <>
      <Space style={{ marginBottom: 12 }} wrap>
        {searchInput}
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="仓库名称或ID"
          value={whFilter}
          onChange={(e) => setWhFilter(e.target.value)}
          style={{ width: 180 }}
        />
        <Select
          allowClear
          placeholder="盘点类型"
          value={checkType}
          onChange={(v) => setCheckType(v)}
          style={{ width: 130 }}
          options={[
            { value: 'order', label: '订单盘点' },
            { value: 'manual', label: '手动盘点' },
            { value: 'cycle_count', label: '周期盘点' },
          ]}
        />
        <RangePicker
          onChange={(_, dateStrings) => {
            if (dateStrings && dateStrings[0] && dateStrings[1]) {
              setDateRange([dateStrings[0], dateStrings[1]])
            } else {
              setDateRange(undefined)
            }
          }}
        />
        <Button icon={<ReloadOutlined />} onClick={reload}>
          刷新
        </Button>
      </Space>
      <Table
        {...tableProps}
        rowKey={rowKey}
        columns={columns}
        size="middle"
        scroll={{ x: 1650 }}
        locale={{ emptyText: '暂无已盘点的物料记录' }}
      />
    </>
  )
}
