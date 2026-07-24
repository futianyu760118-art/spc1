import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Table, Card, Row, Col, Input, Select, Button, Tag, Progress, Tooltip, message, Switch, DatePicker, InputNumber, Space, Popover, Checkbox } from 'antd'
import { SearchOutlined, ShoppingOutlined, PieChartOutlined, WarningOutlined, ExclamationCircleOutlined, CheckCircleOutlined, ReloadOutlined, FilterOutlined, SettingOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { materialApi } from '@/services/api'
import { useUiPreferencesStore } from '@/store/uiPreferences'

interface MaterialItem {
  material_code: string
  material_name: string | null
  product_code: string | null
  product_name: string | null
  material_property: number | null
  material_property_label: string | null
  material_type: string | null
  unit_name: string | null
  supplier_name: string | null
  order_qty: number | null
  mrp_qty: number | null
  po_qty: number | null
  stock_qty: number | null
  available_stock_qty: number | null
  shortage_qty: number | null
  req_date: string | null
  po_no: string | null
  po_count: number
  received_qty: number | null
  eta: string | null
  first_eta: string | null
  latest_eta: string | null
  actual_arrival_date: string | null
  inspection_date: string | null
  status: string
  status_label: string | null
  is_stagnant: boolean
  stagnant_qty: number | null
  bill_type: number | null
  bill_type_label: string | null
  bom_demand_qty: number | null
}

interface KitItem {
  order_no: string
  total_materials: number
  received_materials: number
  partial_received_materials: number
  not_ordered_materials: number
  overdue_materials: number
  stagnant_materials: number
  kit_rate: number
  risk_level: string
  promised_date: string | null
  materials?: MaterialItem[]
}

const RISK_COLOR: Record<string, string> = { red: '#e11d48', yellow: '#f59e0b', green: '#16a34a' }
const RISK_LABEL: Record<string, string> = { red: '缺料严重', yellow: '部分齐套', green: '齐套' }

const MATERIAL_STATUS: Record<string, { label: string; color: string }> = {
  closed: { label: '已关闭', color: 'default' },
  not_ordered: { label: '未下单', color: 'volcano' },
  self_made_unlinked: { label: '自制未排产/未关联', color: 'blue' },
  partial_received: { label: '部分到', color: 'warning' },
  fully_received: { label: '已到齐', color: 'success' },
  overdue: { label: '逾期未到', color: 'error' },
  pending: { label: '待到料', color: 'cyan' },
  in_stock: { label: '有库存', color: 'green' },
}

const MATERIAL_PROPERTY_OPTIONS = [
  { value: 1, label: '外购' },
  { value: 2, label: '自制' },
  { value: 3, label: '委外加工' },
  { value: 5, label: '虚拟件' },
  { value: 6, label: '特征类' },
  { value: 7, label: '配置类' },
  { value: 8, label: '规划类' },
  { value: 9, label: '组装件' },
]

const MATERIAL_PROPERTY_MAP = Object.fromEntries(MATERIAL_PROPERTY_OPTIONS.map(item => [item.value, item.label]))
const MATERIAL_PROPERTY_COLOR: Record<number, string> = {
  1: 'blue', 2: 'purple', 3: 'cyan', 5: 'default', 6: 'geekblue', 7: 'magenta', 8: 'gold', 9: 'orange',
}

const BILL_TYPE_OPTIONS = [
  { value: 11010, label: '采购申请' },
  { value: 11011, label: '自制' },
  { value: 11012, label: '委外申请' },
]
const BILL_TYPE_MAP: Record<number, string> = Object.fromEntries(BILL_TYPE_OPTIONS.map(item => [item.value, item.label]))
const BILL_TYPE_COLOR: Record<number, string> = { 11010: 'geekblue', 11011: 'purple', 11012: 'cyan' }

const DEFAULT_MATERIAL_FILTERS = { status: 'not_ordered,self_made_unlinked,pending,overdue,partial_received' }

const MATERIAL_COLUMN_KEYS = [
  'product_code', 'product_name', 'material_code', 'material_name', 'status', 'is_closed', 'material_property',
  'material_type', 'unit_name', 'supplier_name', 'mrp_qty', 'po_qty', 'stock_qty',
  'available_stock_qty', 'received_qty', 'eta', 'actual_arrival_date', 'inspection_date', 'is_stagnant',
  'bom_demand_qty',
] as const

const MATERIAL_COLUMN_LABELS: Record<string, string> = {
  product_code: '产品代码',
  product_name: '产品名称',
  material_code: '物料代码',
  material_name: '物料名称',
  status: '状态',
  is_closed: '是否关闭',
  material_property: '物料属性',
  material_type: '物料类型',
  unit_name: '单位',
  supplier_name: '供应商',
  mrp_qty: 'MRP数量',
  po_qty: '下单数量',
  stock_qty: '库存',
  available_stock_qty: '可用库存',
  received_qty: '收料量',
  eta: 'ETA',
  actual_arrival_date: '实际到料时间',
  inspection_date: '检验日期',
  is_stagnant: '呆滞',
  bom_demand_qty: 'BOM需求量',
}

const KIT_ANALYSIS_PAGE_KEY = 'kit_analysis_material_columns'

export default function KitAnalysis() {
  const navigate = useNavigate()
  const [data, setData] = useState<KitItem[]>([])
  const [loading, setLoading] = useState(false)
  const [orderNo, setOrderNo] = useState('')
  const [orderType, setOrderType] = useState<string[]>(['big'])
  const [onlyPendingShipment, setOnlyPendingShipment] = useState(true)
  const [riskLevelFilter, setRiskLevelFilter] = useState<string | null>(null)
  const [promisedDateRange, setPromisedDateRange] = useState<[string, string] | null>(null)
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const [sortBy, setSortBy] = useState<string>('')
  const [sortOrder, setSortOrder] = useState<string>('')
  const [materialsLoading, setMaterialsLoading] = useState<Record<string, boolean>>({})
  const [materialFilters, setMaterialFilters] = useState<Record<string, Record<string, any>>>({})
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const paginationRef = useRef(pagination)
  paginationRef.current = pagination
  const [statistics, setStatistics] = useState({ redCount: 0, yellowCount: 0, greenCount: 0, avgKitRate: 0 })

  const getColumnVisibility = useUiPreferencesStore(s => s.getColumnVisibility)
  const setColumnVisibility = useUiPreferencesStore(s => s.setColumnVisibility)
  const [materialColumnKeys, setMaterialColumnKeys] = useState<string[]>(
    () => getColumnVisibility(KIT_ANALYSIS_PAGE_KEY, MATERIAL_COLUMN_KEYS as unknown as string[])
  )

  const load = useCallback(async (page?: number, pageSize?: number) => {
    setLoading(true)
    try {
      const currentPage = page || paginationRef.current.current
      const currentPageSize = pageSize || paginationRef.current.pageSize
      const typeValues = orderType.filter(t => t === 'big' || t === 'sample')
      const textSearch = orderType.find(t => t !== 'big' && t !== 'sample') || orderNo
      const res: any = await materialApi.getKitAnalysis({
        ...(textSearch ? { order_no: textSearch } : {}),
        ...(typeValues.length > 0 ? { order_type: typeValues.join(',') } : {}),
        ...(sortBy ? { sort_by: sortBy, sort_order: sortOrder || 'asc' } : {}),
        ...(riskLevelFilter ? { risk_level: riskLevelFilter } : {}),
        only_pending_shipment: onlyPendingShipment,
        ...(promisedDateRange ? { promised_date_start: promisedDateRange[0], promised_date_end: promisedDateRange[1] } : {}),
        page: currentPage,
        page_size: currentPageSize,
      })
      setData(res.data.items)
      setPagination(prev => ({ ...prev, total: res.data.total, current: currentPage, pageSize: currentPageSize }))
      setStatistics({
        redCount: res.data.statistics?.red_count || 0,
        yellowCount: res.data.statistics?.yellow_count || 0,
        greenCount: res.data.statistics?.green_count || 0,
        avgKitRate: res.data.statistics?.avg_kit_rate || 0,
      })
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [orderNo, orderType, sortBy, sortOrder, onlyPendingShipment, riskLevelFilter, promisedDateRange])

  const handlePaginationChange = useCallback((page: number, pageSize: number) => {
    setPagination(prev => ({ ...prev, current: page, pageSize }))
    // Trigger load with new pagination values
    load(page, pageSize)
  }, [load])

  const handleFilterChange = useCallback(() => {
    setPagination(prev => ({ ...prev, current: 1 }))
  }, [])

  const handlePendingShipmentToggle = useCallback((checked: boolean) => {
    setOnlyPendingShipment(checked)
    handleFilterChange()
  }, [handleFilterChange])

  const loadMaterials = useCallback(async (orderNo: string, filters: Record<string, any> = {}) => {
    setMaterialsLoading(prev => ({ ...prev, [orderNo]: true }))
    try {
      const params: any = {}
      if (filters.material_code) params.material_code = filters.material_code
      if (filters.material_name) params.material_name = filters.material_name
      if (filters.material_property) params.material_property = filters.material_property
      if (filters.material_type) params.material_type = filters.material_type
      if (filters.supplier) params.supplier = filters.supplier
      if (filters.po_qty_min) params.po_qty_min = filters.po_qty_min
      if (filters.po_qty_max) params.po_qty_max = filters.po_qty_max
      if (filters.received_qty_min) params.received_qty_min = filters.received_qty_min
      if (filters.received_qty_max) params.received_qty_max = filters.received_qty_max
      if (filters.eta_start) params.eta_start = filters.eta_start
      if (filters.eta_end) params.eta_end = filters.eta_end
      if (filters.actual_arrival_date_start) params.actual_arrival_date_start = filters.actual_arrival_date_start
      if (filters.actual_arrival_date_end) params.actual_arrival_date_end = filters.actual_arrival_date_end
      if (filters.inspection_date_start) params.inspection_date_start = filters.inspection_date_start
      if (filters.inspection_date_end) params.inspection_date_end = filters.inspection_date_end
      if (filters.status) params.status = filters.status
      if (filters.is_stagnant) params.is_stagnant = filters.is_stagnant
      if (filters.bill_type) params.bill_type = filters.bill_type
      if (filters.sortBy) params.sort_by = filters.sortBy
      if (filters.sortOrder) params.sort_order = filters.sortOrder

      const res: any = await materialApi.getOrderMaterials(orderNo, params)
      setData(prev => prev.map(item =>
        item.order_no === orderNo ? { ...item, materials: res.data } : item
      ))
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setMaterialsLoading(prev => ({ ...prev, [orderNo]: false }))
    }
  }, [])

  const handleExpand = useCallback(async (expanded: boolean, record: KitItem) => {
    if (expanded && !record.materials) {
      const filters = materialFilters[record.order_no] || DEFAULT_MATERIAL_FILTERS
      await loadMaterials(record.order_no, filters)
    }
  }, [loadMaterials, materialFilters])

  const handleMaterialFilterChange = useCallback((orderNo: string, filters: Record<string, any>) => {
    setMaterialFilters(prev => ({
      ...prev,
      [orderNo]: filters
    }))
    setData(prev => prev.map(item =>
      item.order_no === orderNo ? { ...item, materials: undefined } : item
    ))
  }, [])

  const handleMaterialSortChange = useCallback((orderNo: string, sortField: string, sortOrder: string) => {
    setMaterialFilters(prev => ({
      ...prev,
      [orderNo]: { ...prev[orderNo], sortBy: sortField, sortOrder }
    }))
    setData(prev => prev.map(item =>
      item.order_no === orderNo ? { ...item, materials: undefined } : item
    ))
  }, [])

  useEffect(() => { load() }, [load])

  const textFilterDropdown = (placeholder: string) => ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
    <div style={{ padding: 8 }}>
      <Input
        placeholder={placeholder}
        value={selectedKeys[0]}
        onChange={e => setSelectedKeys(e.target.value ? [e.target.value] : [])}
        onPressEnter={confirm}
        style={{ width: 188, marginBottom: 8, display: 'block' }}
      />
      <Button type="primary" onClick={confirm} size="small" style={{ width: 90, marginRight: 8 }}>搜索</Button>
      <Button onClick={() => { clearFilters?.(); confirm() }} size="small" style={{ width: 90 }}>重置</Button>
    </div>
  )

  const numberRangeFilterDropdown = (minPlaceholder: string, maxPlaceholder: string) => ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
    <div style={{ padding: 8 }}>
      <Space direction="vertical" size={8}>
        <InputNumber placeholder={minPlaceholder} value={selectedKeys[0]} onChange={v => setSelectedKeys([v, selectedKeys[1]].filter(x => x !== undefined && x !== null && x !== ''))} style={{ width: 188 }} />
        <InputNumber placeholder={maxPlaceholder} value={selectedKeys[1]} onChange={v => setSelectedKeys([selectedKeys[0], v].filter(x => x !== undefined && x !== null && x !== ''))} style={{ width: 188 }} />
        <div>
          <Button type="primary" onClick={confirm} size="small" style={{ width: 90, marginRight: 8 }}>筛选</Button>
          <Button onClick={() => { clearFilters?.(); confirm() }} size="small" style={{ width: 90 }}>重置</Button>
        </div>
      </Space>
    </div>
  )

  const dateRangeFilterDropdown = () => ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
    <div style={{ padding: 8 }}>
      <DatePicker.RangePicker
        value={selectedKeys && selectedKeys.length === 2 ? [dayjs(selectedKeys[0]), dayjs(selectedKeys[1])] : null}
        onChange={(dates) => {
          if (dates && dates[0] && dates[1]) setSelectedKeys([dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')])
          else setSelectedKeys([])
        }}
        style={{ marginBottom: 8, display: 'block', width: 220 }}
      />
      <Button type="primary" onClick={confirm} size="small" style={{ width: 90, marginRight: 8 }}>筛选</Button>
      <Button onClick={() => { clearFilters?.(); confirm() }} size="small" style={{ width: 90 }}>重置</Button>
    </div>
  )

  const getMaterialColumns = (orderNo: string) => {
    const currentFilters = materialFilters[orderNo]
    const statusFilteredValue = currentFilters
      ? (currentFilters.status ? String(currentFilters.status).split(',') : null)
      : DEFAULT_MATERIAL_FILTERS.status.split(',')

    return [
    {
      title: '产品代码', dataIndex: 'product_code', width: 140, ellipsis: true,
      render: (v: string | null) => v ? <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '产品名称', dataIndex: 'product_name', width: 160, ellipsis: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '物料代码', dataIndex: 'material_code', width: 180, ellipsis: true, sorter: true,
      filterDropdown: textFilterDropdown('物料代码'),
      filterIcon: (filtered: boolean) => <SearchOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
      render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    {
      title: '物料名称', dataIndex: 'material_name', width: 180, ellipsis: true, sorter: true,
      filterDropdown: textFilterDropdown('物料名称'),
      filterIcon: (filtered: boolean) => <SearchOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
    },
    {
      title: '状态', dataIndex: 'status', width: 90, sorter: true,
      filters: [
        { text: '未下单', value: 'not_ordered' },
        { text: '自制未排产/未关联', value: 'self_made_unlinked' },
        { text: '已到齐', value: 'fully_received' },
        { text: '部分到', value: 'partial_received' },
        { text: '逾期未到', value: 'overdue' },
        { text: '待到料', value: 'pending' },
        { text: '有库存', value: 'in_stock' },
      ],
      filteredValue: statusFilteredValue,
      filterMultiple: true,
      render: (v: string, row: MaterialItem) => {
        const s = MATERIAL_STATUS[v] || { label: v, color: 'default' }
        return <Tag color={s.color}>{row.status_label || s.label}</Tag>
      },
    },
    {
      title: '是否关闭', dataIndex: 'is_closed', width: 90,
      filters: [
        { text: '已关闭', value: 'true' },
        { text: '未关闭', value: 'false' },
      ],
      filterMultiple: false,
      render: (v: number) => v === 1
        ? <span style={{ color: '#e11d48', fontWeight: 500 }}>已关闭</span>
        : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '物料属性', dataIndex: 'material_property', width: 90, sorter: true,
      filters: MATERIAL_PROPERTY_OPTIONS.map(opt => ({ text: opt.label, value: String(opt.value) })),
      filterMultiple: true,
      render: (v: number | null) => {
        if (!v) return <span style={{ color: '#cbd5e1' }}>-</span>
        return <Tag color={MATERIAL_PROPERTY_COLOR[v] || 'default'}>{MATERIAL_PROPERTY_MAP[v] || v}</Tag>
      },
    },
    {
      title: '物料类型', dataIndex: 'material_type', width: 110, ellipsis: true, sorter: true,
      filterDropdown: textFilterDropdown('物料类型'),
      filterIcon: (filtered: boolean) => <SearchOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
    },
    {
      title: '单位', dataIndex: 'unit_name', width: 70,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '供应商', dataIndex: 'supplier_name', width: 130, ellipsis: true, sorter: true,
      filterDropdown: textFilterDropdown('供应商名称'),
      filterIcon: (filtered: boolean) => <SearchOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
    },
    {
      title: 'MRP数量', dataIndex: 'mrp_qty', width: 90, sorter: true,
      render: (v: number | null) => v != null ? <span style={{ color: '#6366f1' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '下单数量', dataIndex: 'po_qty', width: 90, sorter: true,
      filterDropdown: numberRangeFilterDropdown('最小下单数量', '最大下单数量'),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
      render: (v: number | null) => v != null ? <span style={{ color: '#0ea5e9' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '库存', dataIndex: 'stock_qty', width: 80, sorter: true,
      render: (v: number | null) => v != null ? <span style={{ color: '#0ea5e9' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '可用库存', dataIndex: 'available_stock_qty', width: 100, sorter: true,
      render: (v: number | null, row: MaterialItem) => {
        if (v == null) return <span style={{ color: '#cbd5e1' }}>-</span>
        const netDemand = Math.max(0, (row.mrp_qty || 0) - (row.received_qty || 0))
        const met = netDemand > 0 && v >= netDemand
        const tip = `总库存 ${row.stock_qty ?? '-'}，扣除其他订单占用后可用 ${v}（净需求 ${netDemand}）`
        return (
          <Tooltip title={tip}>
            <span style={{ color: met ? '#16a34a' : '#0ea5e9', fontWeight: met ? 600 : 400 }}>{v}</span>
          </Tooltip>
        )
      },
    },
    {
      title: '收料量', dataIndex: 'received_qty', width: 80, sorter: true,
      filterDropdown: numberRangeFilterDropdown('最小收料量', '最大收料量'),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
      render: (v: number | null) => v != null ? <span style={{ color: '#16a34a' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>0</span>,
    },
    {
      title: 'ETA', dataIndex: 'eta', width: 100, sorter: true,
      filterDropdown: dateRangeFilterDropdown(),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '实际到料时间', dataIndex: 'actual_arrival_date', width: 120, sorter: true,
      filterDropdown: dateRangeFilterDropdown(),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
      render: (v: string | null) => v ? <span style={{ color: '#16a34a' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '检验日期', dataIndex: 'inspection_date', width: 100, sorter: true,
      filterDropdown: dateRangeFilterDropdown(),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
      render: (v: string | null) => v ? <span style={{ color: '#6366f1' }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '呆滞', dataIndex: 'is_stagnant', width: 80, sorter: true,
      filters: [
        { text: '呆滞', value: 'true' },
        { text: '非呆滞', value: 'false' },
      ],
      filterMultiple: false,
      render: (v: boolean, row: MaterialItem) => {
        if (!v) return <span style={{ color: '#cbd5e1' }}>-</span>
        return <Tooltip title={`超量 ${row.stagnant_qty}，收料${row.received_qty} > 需求${row.order_qty}`}><Tag color="warning">呆滞 +{row.stagnant_qty}</Tag></Tooltip>
      },
    },
    {
      title: 'BOM需求量', dataIndex: 'bom_demand_qty', width: 100, sorter: true,
      render: (v: number | null) => v != null
        ? <span style={{ color: '#e11d48', fontWeight: 500 }}>{v}</span>
        : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    ]
      .map((col: any) => ({ ...col, key: col.key || col.dataIndex }))
      .filter((col: any) => materialColumnKeys.includes(col.key))
  }

  const columns = [
    {
      title: '订单号',
      dataIndex: 'order_no',
      key: 'order_no',
      width: 180,
      fixed: 'left' as const,
      sorter: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8, width: 200 }}>
          <Input
            placeholder="输入订单号"
            value={selectedKeys.find((k: string) => !['big', 'sample'].includes(k)) || ''}
            onChange={(e) => {
              const typeKeys = selectedKeys.filter((k: string) => ['big', 'sample'].includes(k))
              const newKeys = e.target.value ? [...typeKeys, e.target.value] : typeKeys
              setSelectedKeys(newKeys.length > 0 ? newKeys : [])
            }}
            style={{ width: '100%', marginBottom: 8, display: 'block' }}
          />
          <Checkbox.Group
            value={selectedKeys.filter((k: string) => ['big', 'sample'].includes(k))}
            onChange={(checkedValues) => {
              const textKey = selectedKeys.find((k: string) => !['big', 'sample'].includes(k))
              const newKeys = textKey ? [...checkedValues, textKey] : [...checkedValues]
              setSelectedKeys(newKeys.length > 0 ? newKeys : [])
            }}
            style={{ marginBottom: 8, display: 'block' }}
          >
            <Checkbox value="big">大单（HJ开头）</Checkbox>
            <Checkbox value="sample">样品单（HJY开头）</Checkbox>
          </Checkbox.Group>
          <Space>
            <Button
              type="primary"
              onClick={() => {
                setOrderType(selectedKeys)
                const textVal = selectedKeys.find((k: string) => !['big', 'sample'].includes(k))
                setOrderNo(textVal || '')
                confirm()
                setPagination(prev => ({ ...prev, current: 1 }))
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters?.()
                setOrderType([])
                setOrderNo('')
                setPagination(prev => ({ ...prev, current: 1 }))
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
      render: (v: string) => {
        let orderTypeTag = null
        if (v?.startsWith('HJY')) {
          orderTypeTag = <Tag color="blue" style={{ marginLeft: 4, fontSize: 'calc(0.625rem * var(--font-size-scale))', padding: '0 4px', height: 18, lineHeight: '16px' }}>样品</Tag>
        } else if (v?.startsWith('HJ')) {
          orderTypeTag = <Tag color="orange" style={{ marginLeft: 4, fontSize: 'calc(0.625rem * var(--font-size-scale))', padding: '0 4px', height: 18, lineHeight: '16px' }}>大单</Tag>
        }
        return (
          <Tooltip title={v}>
            <div style={{ display: 'flex', alignItems: 'center' }}>
              <a onClick={() => navigate(`/orders/${v}`)} style={{ fontFamily: 'monospace', fontWeight: 600 }}>{v}</a>
              {orderTypeTag}
            </div>
          </Tooltip>
        )
      },
    },
    {
      title: '合同交期',
      dataIndex: 'promised_date',
      key: 'promised_date',
      width: 120,
      sorter: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <DatePicker.RangePicker
            value={selectedKeys && selectedKeys.length === 2 ? [dayjs(selectedKeys[0]), dayjs(selectedKeys[1])] : null}
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setSelectedKeys([dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')])
              } else {
                setSelectedKeys([])
              }
            }}
            style={{ marginBottom: 8, display: 'block', width: 220 }}
          />
          <div>
            <Button type="primary" onClick={() => { confirm(); setPromisedDateRange(selectedKeys.length === 2 ? [selectedKeys[0], selectedKeys[1]] : null); setPagination(prev => ({ ...prev, current: 1 })) }} size="small" style={{ width: 90, marginRight: 8 }}>确定</Button>
            <Button onClick={() => { clearFilters?.(); setPromisedDateRange(null); setPagination(prev => ({ ...prev, current: 1 })) }} size="small" style={{ width: 90 }}>重置</Button>
          </div>
        </div>
      ),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
      render: (date: string | null) => date || '-',
    },
    {
      title: '齐套率', dataIndex: 'kit_rate', width: 180, sorter: true,
      render: (v: number, row: KitItem) => {
        const percent = Math.round(v * 100)
        const tip = `齐套率 = 已到齐 ÷ 物料数\n已到齐 ${row.received_materials} / 物料数 ${row.total_materials} = ${percent}%\n（已到料齐 或 可用库存≥净需求 或 有库存 计为齐套；部分到、未到不计入）`
        return (
          <Tooltip title={<span style={{ whiteSpace: 'pre-line' }}>{tip}</span>}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Progress
                percent={percent}
                size="small"
                style={{ width: 120 }}
                strokeColor={RISK_COLOR[row.risk_level]}
                showInfo={false}
              />
              <span style={{ color: RISK_COLOR[row.risk_level], fontWeight: 600, fontSize: 13 }}>
                {percent}%
              </span>
            </div>
          </Tooltip>
        )
      },
    },
    {
      title: '物料数', dataIndex: 'total_materials', width: 80, sorter: true,
      render: (v: number) => v,
    },
    {
      title: '已到齐', dataIndex: 'received_materials', width: 80, sorter: true,
      render: (v: number) => <span style={{ color: '#16a34a' }}>{v}</span>,
    },
    {
      title: '部分到', dataIndex: 'partial_received_materials', width: 80, sorter: true,
      render: (v: number) => v > 0 ? <span style={{ color: '#f59e0b', fontWeight: 600 }}>{v}</span> : <span style={{ color: '#94a3b8' }}>0</span>,
    },
    {
      title: '未到', width: 80, sorter: true,
      render: (_: any, row: KitItem) => {
        const shortage = row.total_materials - row.received_materials - row.partial_received_materials
        return shortage > 0 ? <span style={{ color: '#e11d48', fontWeight: 600 }}>{shortage}</span> : <span style={{ color: '#16a34a' }}>0</span>
      },
    },
    {
      title: '呆滞物料', dataIndex: 'stagnant_materials', width: 80, sorter: true,
      render: (v: number) => v > 0 ? <span style={{ color: '#d97706', fontWeight: 600 }}>{v}</span> : <span style={{ color: '#94a3b8' }}>0</span>,
    },
    {
      title: '风险等级', dataIndex: 'risk_level', width: 90, sorter: true,
      filters: [
        { text: '缺料严重', value: 'red' },
        { text: '部分齐套', value: 'yellow' },
        { text: '齐套', value: 'green' },
      ],
      render: (v: string) => (
        <Tag color={v === 'red' ? 'error' : v === 'yellow' ? 'warning' : 'success'}>
          {RISK_LABEL[v] || v}
        </Tag>
      ),
    },
  ]

  return (
    <div>
      {/* 统计卡 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '订单总数', value: pagination.total, icon: <ShoppingOutlined />, color: '#6366f1' },
          { title: '平均齐套率', value: `${statistics.avgKitRate}%`, icon: <PieChartOutlined />, color: '#16a34a' },
          { title: '缺料严重(齐套率<80%)', value: statistics.redCount, icon: <WarningOutlined />, color: '#e11d48' },
          { title: '部分齐套(80%-99%)', value: statistics.yellowCount, icon: <ExclamationCircleOutlined />, color: '#f59e0b' },
          { title: '已齐套(100%)', value: statistics.greenCount, icon: <CheckCircleOutlined />, color: '#16a34a' },
        ].map((card, i) => (
          <Col flex={1} key={i}>
            <Card size="small" className="card-modern" style={{ padding: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ width: 44, height: 44, borderRadius: 10, background: `${card.color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 'calc(1.25rem * var(--font-size-scale))', color: card.color }}>
                  {card.icon}
                </div>
                <div>
                  <div style={{ fontSize: 'calc(1.375rem * var(--font-size-scale))', fontWeight: 700, color: '#1e293b' }}>{card.value}</div>
                  <div style={{ fontSize: 'calc(0.75rem * var(--font-size-scale))', color: '#64748b' }}>{card.title}</div>
                </div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input
              prefix={<SearchOutlined />}
              placeholder="订单号"
              value={orderNo}
              onChange={e => { setOrderNo(e.target.value); handleFilterChange() }}
              style={{ width: 160 }}
              allowClear
            />
          </Col>
          <Col>
            <Switch
              checked={onlyPendingShipment}
              onChange={handlePendingShipmentToggle}
              checkedChildren="仅未发货"
              unCheckedChildren="全部"
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Button icon={<ReloadOutlined />} onClick={() => load()}>刷新</Button>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="order_no"
          dataSource={data}
          columns={columns}
          loading={loading}
          size="small"
          scroll={{ x: 720 }}
          expandable={{
            expandedRowKeys: expandedKeys,
            onExpandedRowsChange: (keys) => {
              const next = keys as string[]
              setExpandedKeys(next.length > 1 ? [next[next.length - 1]] : next)
            },
            onExpand: handleExpand,
            expandedRowRender: (row: KitItem) => (
              <div style={{ padding: '8px 0' }}>
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 4, paddingRight: 8 }}>
                  <Popover
                    trigger="click"
                    placement="bottomRight"
                    title="选择显示列"
                    content={
                      <Checkbox.Group
                        value={materialColumnKeys}
                        onChange={(checked) => {
                          const next = checked as string[]
                          if (next.length === 0) return
                          setMaterialColumnKeys(next)
                          setColumnVisibility(KIT_ANALYSIS_PAGE_KEY, next)
                        }}
                      >
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, auto)', gap: '4px 16px', maxWidth: 420 }}>
                          {MATERIAL_COLUMN_KEYS.map(key => (
                            <Checkbox key={key} value={key}>{MATERIAL_COLUMN_LABELS[key]}</Checkbox>
                          ))}
                        </div>
                      </Checkbox.Group>
                    }
                  >
                    <Button size="small" icon={<SettingOutlined />}>列设置</Button>
                  </Popover>
                </div>
                <Table
                  rowKey="material_code"
                  dataSource={row.materials || []}
                  columns={getMaterialColumns(row.order_no)}
                  pagination={false}
                  size="small"
                  virtual
                  sticky
                  scroll={{ x: 1700, y: 360 }}
                  loading={materialsLoading[row.order_no]}
                  onChange={(_pagination, tableFilters: any, sorter: any) => {
                    const sortField = sorter.field as string | undefined
                    const sortDir = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : ''
                    const nextFilters: Record<string, any> = {
                      material_code: tableFilters.material_code?.[0],
                      material_name: tableFilters.material_name?.[0],
                      material_property: tableFilters.material_property?.length ? tableFilters.material_property.join(',') : undefined,
                      material_type: tableFilters.material_type?.[0],
                      supplier: tableFilters.supplier_name?.[0],
                      po_qty_min: tableFilters.po_qty?.[0],
                      po_qty_max: tableFilters.po_qty?.[1],
                      received_qty_min: tableFilters.received_qty?.[0],
                      received_qty_max: tableFilters.received_qty?.[1],
                      eta_start: tableFilters.eta?.[0],
                      eta_end: tableFilters.eta?.[1],
                      actual_arrival_date_start: tableFilters.actual_arrival_date?.[0],
                      actual_arrival_date_end: tableFilters.actual_arrival_date?.[1],
                      inspection_date_start: tableFilters.inspection_date?.[0],
                      inspection_date_end: tableFilters.inspection_date?.[1],
                      status: tableFilters.status?.length ? tableFilters.status.join(',') : undefined,
                      is_stagnant: tableFilters.is_stagnant?.[0],
                      bill_type: tableFilters.bill_type?.length ? tableFilters.bill_type.join(',') : undefined,
                      sortBy: sortField || '',
                      sortOrder: sortDir,
                    }
                    Object.keys(nextFilters).forEach(key => {
                      if (nextFilters[key] === undefined || nextFilters[key] === null || nextFilters[key] === '') delete nextFilters[key]
                    })
                    handleMaterialFilterChange(row.order_no, nextFilters)
                    loadMaterials(row.order_no, nextFilters)
                  }}
                />
              </div>
            ),
          }}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showTotal: t => `共 ${t} 单`,
            showSizeChanger: true,
            onChange: handlePaginationChange,
            onShowSizeChange: handlePaginationChange,
          }}
          onChange={(_pagination, tableFilters: any, sorter: any) => {
            const sortField = sorter.field as string | undefined
            const sortDir = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : ''
            setSortBy(sortField || '')
            setSortOrder(sortDir)

            // Handle risk_level filter
            const riskFilter = tableFilters.risk_level?.[0] || null
            setRiskLevelFilter(riskFilter)

            handleFilterChange()
          }}
        />
      </div>
    </div>
  )
}
