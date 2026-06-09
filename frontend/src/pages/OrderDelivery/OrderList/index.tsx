import React, { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { Row, Col, Table, Tag, Input, Select, Button, message, Space, Tooltip, Modal, Form, DatePicker, Card, Spin, Progress, Dropdown, Switch } from 'antd'
import zhCN from 'antd/locale/zh_CN'
const { RangePicker } = DatePicker
import {
  SearchOutlined,
  ReloadOutlined,
  ShoppingCartOutlined,
  WarningOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  AuditOutlined,
  EditOutlined,
  SaveOutlined,
  FilterOutlined,
  CloseOutlined,
  DownloadOutlined,
  DownOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import RiskBadge from '../../../components/RiskBadge'
import StatusTag from '../../../components/StatusTag'
import RiskDetailModal from '../../../components/RiskDetailModal'
import { orderApi, riskApi } from '../../../services/api'
import { formatDate, formatDateTime } from '../../../utils'
import { useExport } from '../../../hooks/useExport'
import ExportColumnSelector, { type ExportColumnOption } from '../../../components/ExportColumnSelector'

interface OrderRow {
  id: number
  order_no: string
  line_no: string | null
  customer: string | null
  customer_code: string | null
  product_code: string | null
  product_name: string | null
  order_qty: number | null
  order_amount: number | null
  completed_qty: number | null
  promised_date: string | null
  planned_start_date: string | null
  department: string | null
  owner: string | null
  status: string
  risk_level: string | null
  risk_score: number | null
  risk_factors: Record<string, number> | null
  risk_assessed_at: string | null
  data_source: string | null
  delivery_completed_date: string | null
  customer_grade: string | null
  shipping_plan: string | null
  customer_inspection_date: string | null
  inspection_result: string | null
  packaging_status: string | null
  bom_return_date: string | null
  material_ready_date: string | null
  shipping_status_desc: string | null
  procurement_status: string | null
  kit_rate: number | null
  kit_status: string | null
  kit_risk_level: string | null
  kit_total_materials: number
  kit_received_materials: number
  material_dates: Record<string, string> | null
  front_process_date: string | null
  first_article_date: string | null
  assembly_start_date: string | null
  assembly_complete_date: string | null
  remark: string | null
  order_date: string | null
  shortage_count: number
}

interface OrderLineData {
  id: number
  order_no: string
  line_no: string | null
  product_code: string | null
  product_name: string | null
  product_model: string | null
  order_qty: number | null
  order_amount: number | null
  promised_date: string | null
  planned_start_date: string | null
  batch_no: string | null
  status: string
}

interface OrderDetailData {
  id: number
  order_no: string
  line_no: string | null
  customer: string | null
  product_name: string | null
  order_qty: number | null
  promised_date: string | null
  shortage_count: number
  in_transit_count: number
  latest_eta: string | null
  lines: OrderLineData[]
  material_demands: any[]
  bindings: any[]
  issues: any[]
}

interface Filters {
  keyword: string
  risk_level: string[]
  customer_grade: string[]
  department: string[]
  status: string[]
  inspection_result: string[]
  packaging_status: string[]
  procurement_status: string[]
  delivery_completed: string[]
  order_type: string[]
  promised_date_range: [string, string] | null
  shipping_plan_range: [string, string] | null
  order_date_range: [string, string] | null
  customer_inspection_date_range: [string, string] | null
  planned_start_date_range: [string, string] | null
  material_ready_date_range: [string, string] | null
  front_process_date_range: [string, string] | null
  first_article_date_range: [string, string] | null
  assembly_start_date_range: [string, string] | null
  assembly_complete_date_range: [string, string] | null
}

const MATERIAL_KEYS = [
  '电子料', 'SMT上线', '光源', '感应器/电源/控制板',
  '结构', '结构2', '支架', '电缆线', '塑料件', '手杆',
  '彩盒', '说明书', '灯珠', '光源板', '电源板', '包材',
]


const today = () => new Date().toISOString().slice(0, 10)

function DateCell({ value, overdue }: { value: string | null; overdue?: boolean }) {
  if (!value) return <span style={{ color: '#cbd5e1' }}>-</span>
  return <span style={{ color: overdue ? '#e11d48' : undefined, fontWeight: overdue ? 600 : undefined }}>{formatDate(value)}</span>
}

function GreenDateCell({ value }: { value: string | null }) {
  if (!value) return <span style={{ color: '#cbd5e1' }}>-</span>
  return <span style={{ color: '#16a34a', fontWeight: 500 }}>{formatDate(value)}</span>
}

function calculateOrderStatus(record: OrderRow) {
  if (record.delivery_completed_date) return 'closed'
  if (record.completed_qty && record.order_qty && record.completed_qty >= record.order_qty) return 'in_progress'
  if (record.assembly_complete_date || record.assembly_start_date || record.first_article_date || record.front_process_date) return 'in_production'
  if (record.material_ready_date || record.procurement_status || record.shipping_plan || record.planned_start_date) return 'in_progress'
  return record.status || 'open'
}


// 从表格列自动生成导出列选项
const generateExportColumns = (tableColumns: any[]): ExportColumnOption[] => {
  return tableColumns
    .filter(col => col.title && col.dataIndex) // 过滤掉没有标题或数据索引的列
    .map(col => ({
      field: col.dataIndex,
      label: col.title
    }))
}

export default function OrderList() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { exporting, exportData } = useExport()
  const [orders, setOrders] = useState<OrderRow[]>([])
  const [loading, setLoading] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 50, total: 0 })
  const [filters, setFilters] = useState<Filters>({
    keyword: '',
    risk_level: [],
    customer_grade: [],
    department: [],
    status: [],
    inspection_result: [],
    packaging_status: [],
    procurement_status: [],
    delivery_completed: ['no'],
    order_type: [],
    promised_date_range: null,
    shipping_plan_range: null,
    order_date_range: null,
    customer_inspection_date_range: null,
    planned_start_date_range: null,
    material_ready_date_range: null,
    front_process_date_range: null,
    first_article_date_range: null,
    assembly_start_date_range: null,
    assembly_complete_date_range: null,
  })
  const [sortInfo, setSortInfo] = useState<{ sort_by?: string; sort_order?: string }>({})
  const [summary, setSummary] = useState({ total: 0, red: 0, yellow: 0, blue: 0, green: 0, shortage: 0, order_qty_total: 0, order_amount_total: 0 })
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<OrderRow | null>(null)
  const [editForm] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const [detailCache, setDetailCache] = useState<Record<string, OrderDetailData>>({})
  const [detailLoading, setDetailLoading] = useState<Record<string, boolean>>({})
  const [riskModalOpen, setRiskModalOpen] = useState(false)
  const [selectedOrder, setSelectedOrder] = useState<OrderRow | null>(null)
  const [exportColumnModalOpen, setExportColumnModalOpen] = useState(false)
  const [exportFormat, setExportFormat] = useState<'xlsx' | 'csv'>('xlsx')
  const [selectedColumns, setSelectedColumns] = useState<string[]>([])

  // ── URL 参数处理 ──
  const urlSearchAppliedRef = useRef(false)
  const [shouldInitialLoad, setShouldInitialLoad] = useState(false)
  
  // 第一步：从 URL 读取参数并更新 filters
  useEffect(() => {
    if (urlSearchAppliedRef.current) return
    
    const searchKeyword = searchParams.get('search')
    if (searchKeyword) {
      // 自动填充搜索关键字
      setFilters(prev => ({ ...prev, keyword: searchKeyword }))
      urlSearchAppliedRef.current = true
      
      // 清除 URL 参数
      const newParams = new URLSearchParams(searchParams)
      newParams.delete('search')
      setSearchParams(newParams, { replace: true })
    }
    
    // 标记可以开始初始加载
    setShouldInitialLoad(true)
  }, [searchParams, setSearchParams])

  // ── 行内编辑 ──
  const [editingCell, setEditingCell] = useState<{ rowId: number; field: string } | null>(null)
  const [savingCell, setSavingCell] = useState(false)
  const savingCellRef = useRef(false)

  const DATE_FIELDS = [
    'delivery_completed_date', 'shipping_plan', 'customer_inspection_date',
    'planned_start_date', 'bom_return_date', 'material_ready_date',
    'front_process_date', 'first_article_date', 'assembly_start_date', 'assembly_complete_date',
  ]

  const handleCellSave = useCallback(async (record: OrderRow, field: string, value: any) => {
    if (savingCellRef.current) return
    savingCellRef.current = true
    setSavingCell(true)
    try {
      const payload: Record<string, any> = {}
      // material_dates 子字段
      if (field.startsWith('mat_')) {
        const matKey = field.replace('mat_', '')
        const newMaterialDates = { ...(record.material_dates || {}) }
        if (value) {
          newMaterialDates[matKey] = dayjs.isDayjs(value) ? value.format('YYYY-MM-DD') : value
        } else {
          delete newMaterialDates[matKey]
        }
        payload.material_dates = Object.keys(newMaterialDates).length > 0 ? newMaterialDates : null
      } else if (DATE_FIELDS.includes(field)) {
        payload[field] = value && dayjs.isDayjs(value) ? value.format('YYYY-MM-DD') : value || null
      } else {
        payload[field] = value || null
      }

      await orderApi.update(record.order_no, payload)

      // 本地更新 orders state 避免全量刷新
      setOrders(prev => prev.map(o => {
        if (o.id !== record.id) return o
        if (field.startsWith('mat_')) {
          return { ...o, material_dates: payload.material_dates }
        }
        return { ...o, [field]: payload[field] }
      }))
      setEditingCell(null)
    } catch {
      message.error('保存失败')
    } finally {
      savingCellRef.current = false
      setSavingCell(false)
    }
  }, [])

  const isEditingCell = useCallback((rowId: number, field: string) =>
    editingCell?.rowId === rowId && editingCell?.field === field, [editingCell])

  const startEditCell = useCallback((rowId: number, field: string) => {
    if (savingCellRef.current) return
    setEditingCell({ rowId, field })
  }, [])

  const cancelEditCell = useCallback(() => {
    if (!savingCellRef.current) setEditingCell(null)
  }, [])

  // ── 行内编辑渲染辅助 ──
  function EditableDateCell({ value, record, field, overdue, green }: {
    value: string | null; record: OrderRow; field: string; overdue?: boolean; green?: boolean
  }) {
    const editing = isEditingCell(record.id, field)
    const pickerRef = useRef<any>(null)
    
    const handleClick = (e: React.MouseEvent) => {
      e.stopPropagation()
      startEditCell(record.id, field)
    }
    
    if (editing) {
      return (
        <div className="editable-cell editable-cell-editing">
          <DatePicker
            ref={pickerRef}
            defaultValue={value ? dayjs(value) : undefined}
            size="small"
            open
            onChange={(d) => handleCellSave(record, field, d)}
            onOpenChange={(open) => { if (!open) cancelEditCell() }}
            style={{ width: '100%' }}
            popupStyle={{ zIndex: 1050 }}
          />
        </div>
      )
    }
    const display = value
      ? <span style={{
          color: green ? '#16a34a' : overdue ? '#e11d48' : undefined,
          fontWeight: (green || overdue) ? (green ? 500 : 600) : undefined,
        }}>{formatDate(value)}</span>
      : <span style={{ color: '#cbd5e1' }}>-</span>
    return <div className="editable-cell" onClick={handleClick}>{display}</div>
  }

  function EditableSelectCell({ value, record, field, options, renderValue }: {
    value: string | null; record: OrderRow; field: string;
    options: { value: string; label: string }[];
    renderValue?: (v: string | null) => React.ReactNode;
  }) {
    const editing = isEditingCell(record.id, field)
    const selectRef = useRef<any>(null)
    
    const handleClick = (e: React.MouseEvent) => {
      e.stopPropagation()
      startEditCell(record.id, field)
    }
    
    if (editing) {
      return (
        <div className="editable-cell editable-cell-editing">
          <Select
            ref={selectRef}
            defaultValue={value || undefined}
            size="small"
            open
            allowClear
            options={options}
            style={{ width: '100%' }}
            onChange={(v) => handleCellSave(record, field, v ?? null)}
            onDropdownVisibleChange={(open) => { if (!open) cancelEditCell() }}
            dropdownStyle={{ zIndex: 1050 }}
          />
        </div>
      )
    }
    const display = renderValue ? renderValue(value) : (value || '-')
    return <div className="editable-cell" onClick={handleClick}>{display}</div>
  }

  function EditableTextCell({ value, record, field, renderValue }: {
    value: string | null; record: OrderRow; field: string;
    renderValue?: (v: string | null) => React.ReactNode;
  }) {
    const editing = isEditingCell(record.id, field)
    const inputRef = useRef<any>(null)
    const [tempVal, setTempVal] = useState('')
    
    const handleClick = (e: React.MouseEvent) => {
      e.stopPropagation()
      startEditCell(record.id, field)
    }
    
    // 进入编辑态时初始化值
    useEffect(() => {
      if (editing) {
        setTempVal(value || '')
        // 延迟聚焦，确保DOM已渲染
        setTimeout(() => inputRef.current?.focus(), 0)
      }
    }, [editing, value])
    
    if (editing) {
      return (
        <div className="editable-cell editable-cell-editing">
          <Input
            ref={inputRef}
            value={tempVal}
            size="small"
            onChange={(e) => setTempVal(e.target.value)}
            onBlur={() => handleCellSave(record, field, tempVal)}
            onPressEnter={() => handleCellSave(record, field, tempVal)}
            onKeyDown={(e) => { if (e.key === 'Escape') cancelEditCell() }}
          />
        </div>
      )
    }
    const display = renderValue ? renderValue(value) : (value || <span style={{ color: '#cbd5e1' }}>-</span>)
    return <div className="editable-cell" onClick={handleClick}>{display}</div>
  }

  const fetchOrders = useCallback(async (
    page = 1,
    pageSize = 50,
    overrideFilters?: Filters,
    overrideSort?: { sort_by?: string; sort_order?: string },
  ) => {
    setLoading(true)
    try {
      const f = overrideFilters ?? filters
      const s = overrideSort ?? sortInfo
      const params: Record<string, any> = { page, page_size: pageSize }
      if (s.sort_by) params.sort_by = s.sort_by
      if (s.sort_order) params.sort_order = s.sort_order
      if (f.keyword) params.keyword = f.keyword
      if (f.risk_level.length > 0) params.risk_level = f.risk_level.join(',')
      if (f.customer_grade.length > 0) params.customer_grade = f.customer_grade.join(',')
      if (f.department.length > 0) params.department = f.department.join(',')
      if (f.status.length > 0) params.status = f.status.join(',')
      if (f.inspection_result.length > 0) params.inspection_result = f.inspection_result.join(',')
      if (f.packaging_status.length > 0) params.packaging_status = f.packaging_status.join(',')
      if (f.procurement_status.length > 0) params.procurement_status = f.procurement_status.join(',')
      if (f.delivery_completed.length > 0) params.delivery_completed = f.delivery_completed.join(',')
      if (f.order_type.length > 0) params.order_type = f.order_type.join(',')
      if (f.promised_date_range) {
        params.promised_date_start = f.promised_date_range[0]
        params.promised_date_end = f.promised_date_range[1]
      }
      if (f.shipping_plan_range) {
        params.shipping_plan_start = f.shipping_plan_range[0]
        params.shipping_plan_end = f.shipping_plan_range[1]
      }
      if (f.order_date_range) {
        params.order_date_start = f.order_date_range[0]
        params.order_date_end = f.order_date_range[1]
      }
      if (f.customer_inspection_date_range) {
        params.customer_inspection_date_start = f.customer_inspection_date_range[0]
        params.customer_inspection_date_end = f.customer_inspection_date_range[1]
      }
      if (f.planned_start_date_range) {
        params.planned_start_date_start = f.planned_start_date_range[0]
        params.planned_start_date_end = f.planned_start_date_range[1]
      }
      if (f.material_ready_date_range) {
        params.material_ready_date_start = f.material_ready_date_range[0]
        params.material_ready_date_end = f.material_ready_date_range[1]
      }
      if (f.front_process_date_range) {
        params.front_process_date_start = f.front_process_date_range[0]
        params.front_process_date_end = f.front_process_date_range[1]
      }
      if (f.first_article_date_range) {
        params.first_article_date_start = f.first_article_date_range[0]
        params.first_article_date_end = f.first_article_date_range[1]
      }
      if (f.assembly_start_date_range) {
        params.assembly_start_date_start = f.assembly_start_date_range[0]
        params.assembly_start_date_end = f.assembly_start_date_range[1]
      }
      if (f.assembly_complete_date_range) {
        params.assembly_complete_date_start = f.assembly_complete_date_range[0]
        params.assembly_complete_date_end = f.assembly_complete_date_range[1]
      }
      const res: any = await orderApi.list(params)
      const items = res.data.items || []
      setOrders(items)
      setPagination({ current: res.data.page, pageSize: res.data.page_size, total: res.data.total })
      // 使用后端返回的全局统计
      const stats = res.data.stats || {}
      setSummary({
        total: stats.total || res.data.total,
        red: stats.red_count || 0,
        yellow: stats.yellow_count || 0,
        blue: stats.blue_count || 0,
        green: stats.green_count || 0,
        shortage: stats.shortage_count || 0,
        order_qty_total: stats.order_qty_total || 0,
        order_amount_total: stats.order_amount_total || 0,
      })
    } catch {
      message.error('获取订单列表失败')
    } finally {
      setLoading(false)
    }
  }, [filters, sortInfo])

  // 第二步：初始化加载数据（在 fetchOrders 定义之后）
  const initialLoadRef = useRef(false)
  useEffect(() => {
    if (shouldInitialLoad && !initialLoadRef.current) {
      fetchOrders()
      initialLoadRef.current = true
    }
  }, [shouldInitialLoad, fetchOrders])

  const handleTableChange = (pag: any, tableFilters: any, sorter: any) => {
    let sortField = sorter.field
    const sortOrder = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : undefined
    // 风险等级列按分值排序
    if (sortField === 'risk_level') sortField = 'risk_score'
    
    // 处理各种筛选
    const riskLevelFilter = tableFilters.risk_level?.length > 0 ? tableFilters.risk_level : []
    const customerGradeFilter = tableFilters.customer_grade?.length > 0 ? tableFilters.customer_grade : []
    const departmentFilter = tableFilters.department?.length > 0 ? tableFilters.department : []
    const statusFilter = tableFilters.status?.length > 0 ? tableFilters.status : []
    const inspectionResultFilter = tableFilters.inspection_result?.length > 0 ? tableFilters.inspection_result : []
    const packagingStatusFilter = tableFilters.packaging_status?.length > 0 ? tableFilters.packaging_status : []
    const procurementStatusFilter = tableFilters.procurement_status?.length > 0 ? tableFilters.procurement_status : []
    const deliveryCompletedFilter = tableFilters.delivery_completed_date != null
      ? (tableFilters.delivery_completed_date.length > 0 ? tableFilters.delivery_completed_date : [])
      : filters.delivery_completed
    const orderTypeFilter = tableFilters.order_type?.length > 0 ? tableFilters.order_type : []
    
    const newSort = { sort_by: sortField, sort_order: sortOrder }
    const newFilters = {
      ...filters,
      risk_level: riskLevelFilter,
      customer_grade: customerGradeFilter,
      department: departmentFilter,
      status: statusFilter,
      inspection_result: inspectionResultFilter,
      packaging_status: packagingStatusFilter,
      procurement_status: procurementStatusFilter,
      delivery_completed: deliveryCompletedFilter,
      order_type: orderTypeFilter,
    }
    setSortInfo(newSort)
    setFilters(newFilters)
    fetchOrders(pag.current, pag.pageSize, newFilters, newSort)
  }

  const handleScan = async () => {
    setScanning(true)
    try {
      const res: any = await riskApi.scan()
      message.success(`扫描完成: ${res.data.new_issues} 个新问题, ${res.data.updated_orders} 个订单更新`)
      fetchOrders()
    } catch {
      message.error('风险扫描失败')
    } finally {
      setScanning(false)
    }
  }

  const buildFilterParams = useCallback(() => {
    const params: Record<string, any> = {}
    if (filters.keyword) params.keyword = filters.keyword
    if (filters.risk_level.length > 0) params.risk_level = filters.risk_level.join(',')
    if (filters.customer_grade.length > 0) params.customer_grade = filters.customer_grade.join(',')
    if (filters.department.length > 0) params.department = filters.department.join(',')
    if (filters.status.length > 0) params.status = filters.status.join(',')
    if (filters.inspection_result.length > 0) params.inspection_result = filters.inspection_result.join(',')
    if (filters.packaging_status.length > 0) params.packaging_status = filters.packaging_status.join(',')
    if (filters.procurement_status.length > 0) params.procurement_status = filters.procurement_status.join(',')
    if (filters.delivery_completed.length > 0) params.delivery_completed = filters.delivery_completed.join(',')
    if (filters.order_type.length > 0) params.order_type = filters.order_type.join(',')
    if (filters.promised_date_range) {
      params.promised_date_start = filters.promised_date_range[0]
      params.promised_date_end = filters.promised_date_range[1]
    }
    if (filters.shipping_plan_range) {
      params.shipping_plan_start = filters.shipping_plan_range[0]
      params.shipping_plan_end = filters.shipping_plan_range[1]
    }
    if (filters.order_date_range) {
      params.order_date_start = filters.order_date_range[0]
      params.order_date_end = filters.order_date_range[1]
    }
    if (filters.customer_inspection_date_range) {
      params.customer_inspection_date_start = filters.customer_inspection_date_range[0]
      params.customer_inspection_date_end = filters.customer_inspection_date_range[1]
    }
    if (filters.planned_start_date_range) {
      params.planned_start_date_start = filters.planned_start_date_range[0]
      params.planned_start_date_end = filters.planned_start_date_range[1]
    }
    if (filters.material_ready_date_range) {
      params.material_ready_date_start = filters.material_ready_date_range[0]
      params.material_ready_date_end = filters.material_ready_date_range[1]
    }
    if (filters.front_process_date_range) {
      params.front_process_date_start = filters.front_process_date_range[0]
      params.front_process_date_end = filters.front_process_date_range[1]
    }
    if (filters.first_article_date_range) {
      params.first_article_date_start = filters.first_article_date_range[0]
      params.first_article_date_end = filters.first_article_date_range[1]
    }
    if (filters.assembly_start_date_range) {
      params.assembly_start_date_start = filters.assembly_start_date_range[0]
      params.assembly_start_date_end = filters.assembly_start_date_range[1]
    }
    if (filters.assembly_complete_date_range) {
      params.assembly_complete_date_start = filters.assembly_complete_date_range[0]
      params.assembly_complete_date_end = filters.assembly_complete_date_range[1]
    }
    return params
  }, [filters])

  const handleExport = (format: 'xlsx' | 'csv', columns?: string[]) => {
    const params: Record<string, any> = { format, ...buildFilterParams() }
    if (sortInfo.sort_by) { params.sort_by = sortInfo.sort_by; params.sort_order = sortInfo.sort_order || 'asc' }
    if (columns && columns.length > 0) {
      params.columns = columns.join(',')
    }
    const ext = format === 'csv' ? 'csv' : 'xlsx'
    exportData(`/api/v1/orders/export`, params, `订单总控台.${ext}`)
  }

  const handleExportClick = (format: 'xlsx' | 'csv') => {
    setExportFormat(format)
    setExportColumnModalOpen(true)
  }

  const handleExportColumnConfirm = (selectedColumns: string[]) => {
    setExportColumnModalOpen(false)
    handleExport(exportFormat, selectedColumns)
  }

  const handleExportColumnCancel = () => {
    setExportColumnModalOpen(false)
  }

  const handleUnfinishedOrdersToggle = (checked: boolean) => {
    const newFilters = { ...filters, delivery_completed: checked ? ['no'] : [] }
    setFilters(newFilters)
    fetchOrders(1, pagination.pageSize, newFilters, sortInfo)
  }

  const openEditModal = (record: OrderRow) => {
    setEditingRecord(record)
    const formValues: Record<string, any> = {
      delivery_completed_date: record.delivery_completed_date ? dayjs(record.delivery_completed_date) : undefined,
      customer_grade: record.customer_grade || undefined,
      shipping_plan: record.shipping_plan ? dayjs(record.shipping_plan) : undefined,
      customer_inspection_date: record.customer_inspection_date ? dayjs(record.customer_inspection_date) : undefined,
      planned_start_date: record.planned_start_date ? dayjs(record.planned_start_date) : undefined,
      inspection_result: record.inspection_result || undefined,
      packaging_status: record.packaging_status || undefined,
      bom_return_date: record.bom_return_date ? dayjs(record.bom_return_date) : undefined,
      material_ready_date: record.material_ready_date ? dayjs(record.material_ready_date) : undefined,
      shipping_status_desc: record.shipping_status_desc || undefined,
      procurement_status: record.procurement_status || undefined,
      front_process_date: record.front_process_date ? dayjs(record.front_process_date) : undefined,
      first_article_date: record.first_article_date ? dayjs(record.first_article_date) : undefined,
      assembly_start_date: record.assembly_start_date ? dayjs(record.assembly_start_date) : undefined,
      assembly_complete_date: record.assembly_complete_date ? dayjs(record.assembly_complete_date) : undefined,
      risk_level: record.risk_level || undefined,
      remark: record.remark || undefined,
    }
    MATERIAL_KEYS.forEach(key => {
      const val = record.material_dates?.[key]
      formValues[`mat_${key}`] = val ? dayjs(val) : undefined
    })
    editForm.setFieldsValue(formValues)
    setEditModalOpen(true)
  }

  const handleEditSave = async () => {
    if (!editingRecord) return
    try {
      const values = await editForm.validateFields()
      const payload: Record<string, any> = {}
      const dateFields = [
        'delivery_completed_date', 'shipping_plan', 'customer_inspection_date',
        'planned_start_date', 'bom_return_date', 'material_ready_date',
        'front_process_date', 'first_article_date', 'assembly_start_date', 'assembly_complete_date',
      ]
      dateFields.forEach(f => {
        payload[f] = values[f] ? values[f].format('YYYY-MM-DD') : null
      })
      const textFields = [
        'customer_grade', 'inspection_result', 'packaging_status',
        'shipping_status_desc', 'procurement_status', 'risk_level', 'remark',
      ]
      textFields.forEach(f => {
        if (values[f] !== undefined) payload[f] = values[f] || null
      })
      // material_dates JSONB
      const materialDates: Record<string, string> = {}
      MATERIAL_KEYS.forEach(key => {
        const val = values[`mat_${key}`]
        if (val) materialDates[key] = val.format('YYYY-MM-DD')
      })
      payload.material_dates = Object.keys(materialDates).length > 0 ? materialDates : null

      setSaving(true)
      await orderApi.update(editingRecord.order_no, payload)
      message.success('订单已更新')
      setEditModalOpen(false)
      setEditingRecord(null)
      fetchOrders(pagination.current, pagination.pageSize)
    } catch (err: any) {
      if (err?.errorFields) return // form validation error
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  const fetchDetail = useCallback(async (orderNo: string, lineNo: string | null) => {
    const cacheKey = `${orderNo}_${lineNo || '10'}`
    if (detailCache[cacheKey] || detailLoading[cacheKey]) return
    setDetailLoading(prev => ({ ...prev, [cacheKey]: true }))
    try {
      const res: any = await orderApi.getDetail(orderNo, lineNo || undefined)
      setDetailCache(prev => ({ ...prev, [cacheKey]: res.data }))
    } catch {
      message.error('获取订单详情失败')
    } finally {
      setDetailLoading(prev => ({ ...prev, [cacheKey]: false }))
    }
  }, [detailCache, detailLoading])

  const columns = useMemo<any[]>(() => [
    // ── 基本信息（固定左侧）──
    {
      title: '销售部门', dataIndex: 'department', key: 'department', minWidth: 70, fixed: 'left' as const,
      ellipsis: true, sorter: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <Input
            placeholder="输入销售部门"
            value={selectedKeys[0]}
            onChange={(e) => setSelectedKeys(e.target.value ? [e.target.value] : [])}
            style={{ width: 188, marginBottom: 8, display: 'block' }}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => confirm()}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
      onFilter: (value: string, record: OrderRow) => 
        record.department ? record.department.toLowerCase().includes(value.toLowerCase()) : false,
    },
    {
      title: '发货完成', dataIndex: 'delivery_completed_date', key: 'delivery_completed_date', minWidth: 90, fixed: 'left' as const,
      render: (v: string, r: OrderRow) => <EditableDateCell value={v} record={r} field="delivery_completed_date" green />, sorter: true,
      filters: [
        { text: '已发货', value: 'yes' },
        { text: '未发货', value: 'no' },
      ],
      filterMultiple: true,
    },
    {
      title: '客户等级', dataIndex: 'customer_grade', key: 'customer_grade', minWidth: 60, fixed: 'left' as const,
      render: (v: string, r: OrderRow) => (
        <EditableSelectCell value={v} record={r} field="customer_grade"
          options={[
            { value: 'A', label: 'A级' }, { value: 'B', label: 'B级' },
            { value: 'C', label: 'C级' }, { value: 'D', label: 'D级' },
          ]}
          renderValue={(val) => val ? <Tag color={val === 'A' ? 'red' : val === 'B' ? 'orange' : val === 'C' ? 'blue' : 'default'}>{val}</Tag> : '-'}
        />
      ),
      sorter: true,
      filters: [
        { text: 'A级', value: 'A' },
        { text: 'B级', value: 'B' },
        { text: 'C级', value: 'C' },
        { text: 'D级', value: 'D' },
      ],
      filterMultiple: true,
    },
    {
      title: '客户', dataIndex: 'customer_code', key: 'customer_code', minWidth: 70, fixed: 'left' as const,
      ellipsis: true,
      render: (v: string, r: OrderRow) => {
        const firstDashIndex = v?.indexOf('-') ?? -1
        const displayCode = v ? (firstDashIndex !== -1 ? v.substring(firstDashIndex + 1) : v) : ''
        const displayValue = r.customer || displayCode
        if (!displayValue) return '-'
        const tooltip = [r.customer, v].filter(Boolean).join(' / ')
        return <Tooltip title={tooltip}>{displayValue}</Tooltip>
      }, sorter: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <Input
            placeholder="输入客户代码"
            value={selectedKeys[0]}
            onChange={(e) => setSelectedKeys(e.target.value ? [e.target.value] : [])}
            style={{ width: 188, marginBottom: 8, display: 'block' }}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => confirm()}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
      onFilter: (value: string, record: OrderRow) => 
        [record.customer_code, record.customer].some(text => text?.toLowerCase().includes(value.toLowerCase())),
    },
    {
      title: '单号', dataIndex: 'order_no', key: 'order_no', minWidth: 120, fixed: 'left' as const,
      render: (v: string, r: OrderRow) => {
        if (!v) return '-'
        const lastDashIndex = v.lastIndexOf('-')
        const afterDash = lastDashIndex !== -1 ? v.substring(lastDashIndex + 1) : v
        // 去除前导零，但至少保留3位
        const displayValue = afterDash.replace(/^0+/, '').padStart(3, '0')
        // 确定订单类型
        let orderTypeTag = null
        if (v.startsWith('HJY')) {
          orderTypeTag = <Tag color="blue" style={{ marginLeft: 4, fontSize: 10, padding: '0 4px', height: 18, lineHeight: '16px' }}>样品</Tag>
        } else if (v.startsWith('HJ')) {
          orderTypeTag = <Tag color="orange" style={{ marginLeft: 4, fontSize: 10, padding: '0 4px', height: 18, lineHeight: '16px' }}>大单</Tag>
        }
        return (
          <Tooltip title={v}>
            <div>
              <a onClick={() => navigate(`/orders/${v}/lines/${r.line_no || '10'}`)} style={{ fontWeight: 600, fontSize: 'calc(0.75rem * var(--font-size-scale))' }}>{displayValue}</a>
              {orderTypeTag}
            </div>
          </Tooltip>
        )
      }, sorter: true,
      filters: [
        { text: '大单（HJ开头）', value: 'big' },
        { text: '样品单（HJY开头）', value: 'sample' },
      ],
      filterMultiple: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <Input
            placeholder="输入订单号"
            value={selectedKeys[0]}
            onChange={(e) => setSelectedKeys(e.target.value ? [e.target.value] : [])}
            style={{ width: 188, marginBottom: 8, display: 'block' }}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => confirm()}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
      onFilter: (value: string, record: OrderRow) => 
        record.order_no ? record.order_no.toLowerCase().includes(value.toLowerCase()) : false,
    },
    {
      title: '风险等级', dataIndex: 'risk_level', key: 'risk_level', minWidth: 80,
      render: (v: string, r: OrderRow) => (
        <EditableSelectCell value={v} record={r} field="risk_level"
          options={[
            { value: 'red', label: '高风险' }, { value: 'yellow', label: '中风险' },
            { value: 'blue', label: '低风险' }, { value: 'green', label: '正常' },
          ]}
          renderValue={(val) => <RiskBadge level={val} onClick={() => { setSelectedOrder(r); setRiskModalOpen(true) }} />}
        />
      ),
      sorter: true,
      filters: [
        { text: '高风险', value: 'red' },
        { text: '中风险', value: 'yellow' },
        { text: '低风险', value: 'blue' },
        { text: '正常', value: 'green' },
      ],
      filterMultiple: true,
    },
    {
      title: '数量', dataIndex: 'order_qty', key: 'order_qty', minWidth: 60, align: 'right' as const,
      render: (v: number) => v?.toLocaleString() || '-', sorter: true,
    },
    {
      title: '金额', dataIndex: 'order_amount', key: 'order_amount', minWidth: 80, align: 'right' as const,
      render: (v: number) => v?.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '-', sorter: true,
    },
    {
      title: '完成数量', dataIndex: 'completed_qty', key: 'completed_qty', minWidth: 80, align: 'right' as const,
      render: (v: number) => v?.toLocaleString() || '-', sorter: true,
    },
    {
      title: '下单时间', dataIndex: 'order_date', key: 'order_date', minWidth: 90,
      render: (v: string) => <DateCell value={v} />, sorter: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <RangePicker
            locale={zhCN.DatePicker}
            value={selectedKeys[0] ? [dayjs(selectedKeys[0][0]), dayjs(selectedKeys[0][1])] : null}
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setSelectedKeys([[dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]])
              } else {
                setSelectedKeys([])
              }
            }}
            style={{ width: 250, marginBottom: 8, display: 'block' }}
            placeholder={['开始日期', '结束日期']}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => {
                const newFilters = { ...filters, order_date_range: selectedKeys[0] || null }
                setFilters(newFilters)
                confirm()
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters, order_date_range: null }
                setFilters(newFilters)
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
    },
    // ── 交期 & 计划 ──
    {
      title: '合同交期', dataIndex: 'promised_date', key: 'promised_date', minWidth: 85,
      render: (v: string, r: OrderRow) => <EditableDateCell value={v} record={r} field="promised_date" overdue={!!(v && v < today() && r.status !== 'closed')} />, sorter: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <RangePicker
            locale={zhCN.DatePicker}
            value={selectedKeys[0] ? [dayjs(selectedKeys[0][0]), dayjs(selectedKeys[0][1])] : null}
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setSelectedKeys([[dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]])
              } else {
                setSelectedKeys([])
              }
            }}
            style={{ width: 250, marginBottom: 8, display: 'block' }}
            placeholder={['开始日期', '结束日期']}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => {
                const newFilters = { ...filters, promised_date_range: selectedKeys[0] || null }
                setFilters(newFilters)
                confirm()
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters, promised_date_range: null }
                setFilters(newFilters)
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
    },
    {
      title: '出货计划', dataIndex: 'shipping_plan', key: 'shipping_plan', minWidth: 85,
      render: (v: string, r: OrderRow) => <EditableDateCell value={v} record={r} field="shipping_plan" />, sorter: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <RangePicker
            locale={zhCN.DatePicker}
            value={selectedKeys[0] ? [dayjs(selectedKeys[0][0]), dayjs(selectedKeys[0][1])] : null}
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setSelectedKeys([[dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]])
              } else {
                setSelectedKeys([])
              }
            }}
            style={{ width: 250, marginBottom: 8, display: 'block' }}
            placeholder={['开始日期', '结束日期']}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => {
                const newFilters = { ...filters, shipping_plan_range: selectedKeys[0] || null }
                setFilters(newFilters)
                confirm()
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters, shipping_plan_range: null }
                setFilters(newFilters)
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
    },
    {
      title: '客户验货时间', dataIndex: 'customer_inspection_date', key: 'customer_inspection_date', minWidth: 100,
      render: (v: string, r: OrderRow) => <EditableDateCell value={v} record={r} field="customer_inspection_date" />, sorter: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <RangePicker
            locale={zhCN.DatePicker}
            value={selectedKeys[0] ? [dayjs(selectedKeys[0][0]), dayjs(selectedKeys[0][1])] : null}
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setSelectedKeys([[dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]])
              } else {
                setSelectedKeys([])
              }
            }}
            style={{ width: 250, marginBottom: 8, display: 'block' }}
            placeholder={['开始日期', '结束日期']}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => {
                const newFilters = { ...filters, customer_inspection_date_range: selectedKeys[0] || null }
                setFilters(newFilters)
                confirm()
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters, customer_inspection_date_range: null }
                setFilters(newFilters)
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
    },
    {
      title: '上线时间', dataIndex: 'planned_start_date', key: 'planned_start_date', minWidth: 85,
      render: (v: string, r: OrderRow) => <EditableDateCell value={v} record={r} field="planned_start_date" />, sorter: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <RangePicker
            locale={zhCN.DatePicker}
            value={selectedKeys[0] ? [dayjs(selectedKeys[0][0]), dayjs(selectedKeys[0][1])] : null}
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setSelectedKeys([[dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]])
              } else {
                setSelectedKeys([])
              }
            }}
            style={{ width: 250, marginBottom: 8, display: 'block' }}
            placeholder={['开始日期', '结束日期']}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => {
                const newFilters = { ...filters, planned_start_date_range: selectedKeys[0] || null }
                setFilters(newFilters)
                confirm()
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters, planned_start_date_range: null }
                setFilters(newFilters)
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
    },
    {
      title: '客检结果', dataIndex: 'inspection_result', key: 'inspection_result', minWidth: 70,
      render: (v: string, r: OrderRow) => (
        <EditableSelectCell value={v} record={r} field="inspection_result"
          options={[
            { value: 'OK', label: 'OK / 通过' }, { value: 'NG', label: 'NG / 不通过' },
            { value: '待检', label: '待检' },
          ]}
          renderValue={(val) => {
            if (!val) return '-'
            const color = val === 'OK' || val === '通过' ? '#16a34a' : val === 'NG' ? '#e11d48' : undefined
            return <span style={{ color, fontWeight: 600 }}>{val}</span>
          }}
        />
      ),
      filters: [
        { text: 'OK', value: 'OK' },
        { text: '通过', value: '通过' },
        { text: 'NG', value: 'NG' },
        { text: '不通过', value: '不通过' },
        { text: '待检', value: '待检' },
      ],
      filterMultiple: true,
    },
    {
      title: '包装完成状况', dataIndex: 'packaging_status', key: 'packaging_status', minWidth: 100,
      ellipsis: true,
      render: (v: string, r: OrderRow) => (
        <EditableTextCell value={v} record={r} field="packaging_status"
          renderValue={(val) => {
            if (!val) return <span style={{ color: '#cbd5e1' }}>-</span>
            const isBlue = val.includes('完成') && !val.includes('入库')
            const isGreen = val.includes('入库')
            return <span style={{ color: isGreen ? '#16a34a' : isBlue ? '#2563eb' : undefined }}>{val}</span>
          }}
        />
      ),
      filters: [
        { text: '完成', value: '完成' },
        { text: '入库', value: '入库' },
        { text: '进行中', value: '进行中' },
        { text: '未开始', value: '未开始' },
      ],
      filterMultiple: true,
    },
    {
      title: 'BOM回收', dataIndex: 'bom_return_date', key: 'bom_return_date', minWidth: 80,
      render: (v: string, r: OrderRow) => <EditableDateCell value={v} record={r} field="bom_return_date" />, sorter: true,
    },
    {
      title: '料齐套时间', dataIndex: 'material_ready_date', key: 'material_ready_date', minWidth: 85,
      render: (v: string, r: OrderRow) => <EditableDateCell value={v} record={r} field="material_ready_date" green />, sorter: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <RangePicker
            locale={zhCN.DatePicker}
            value={selectedKeys[0] ? [dayjs(selectedKeys[0][0]), dayjs(selectedKeys[0][1])] : null}
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setSelectedKeys([[dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]])
              } else {
                setSelectedKeys([])
              }
            }}
            style={{ width: 250, marginBottom: 8, display: 'block' }}
            placeholder={['开始日期', '结束日期']}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => {
                const newFilters = { ...filters, material_ready_date_range: selectedKeys[0] || null }
                setFilters(newFilters)
                confirm()
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters, material_ready_date_range: null }
                setFilters(newFilters)
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
    },
    // ── 发货 & 采购 ──
    {
      title: '发货状态即时说明', dataIndex: 'shipping_status_desc', key: 'shipping_status_desc', minWidth: 120,
      ellipsis: true,
      render: (v: string, r: OrderRow) => <EditableTextCell value={v} record={r} field="shipping_status_desc" />,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <Input
            placeholder="输入发货状态说明"
            value={selectedKeys[0]}
            onChange={(e) => setSelectedKeys(e.target.value ? [e.target.value] : [])}
            style={{ width: 188, marginBottom: 8, display: 'block' }}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => confirm()}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
      onFilter: (value: string, record: OrderRow) => 
        record.shipping_status_desc ? record.shipping_status_desc.toLowerCase().includes(value.toLowerCase()) : false,
    },
    {
      title: '采购物料齐套', dataIndex: 'procurement_status', key: 'procurement_status', minWidth: 100,
      ellipsis: true,
      render: (_v: string, r: OrderRow) => {
        if (!r.kit_total_materials || r.kit_rate == null || !r.kit_risk_level) {
          return <span style={{ color: '#cbd5e1' }}>-</span>
        }
        const percent = Math.round(r.kit_rate * 100)
        const color = r.kit_risk_level === 'green' ? 'success' : r.kit_risk_level === 'yellow' ? 'warning' : 'error'
        return (
          <Tooltip title={`${r.kit_received_materials}/${r.kit_total_materials}`}>
            <Tag color={color}>{r.kit_status || ''} {percent}%</Tag>
          </Tooltip>
        )
      },
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <Input
            placeholder="输入采购状态"
            value={selectedKeys[0]}
            onChange={(e) => setSelectedKeys(e.target.value ? [e.target.value] : [])}
            style={{ width: 188, marginBottom: 8, display: 'block' }}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => confirm()}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
      onFilter: (value: string, record: OrderRow) => 
        record.procurement_status ? record.procurement_status.toLowerCase().includes(value.toLowerCase()) : false,
    },
    // ── 物料分类到料日期（16列 from material_dates JSONB）──
    ...MATERIAL_KEYS.map(key => ({
      title: key, key: `mat_${key}`, minWidth: key.length > 6 ? 100 : 70,
      render: (_: any, r: OrderRow) => {
        const val = r.material_dates?.[key] || null
        return <EditableDateCell value={val} record={r} field={`mat_${key}`} />
      },
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <RangePicker
            locale={zhCN.DatePicker}
            value={selectedKeys[0] ? [dayjs(selectedKeys[0][0]), dayjs(selectedKeys[0][1])] : null}
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setSelectedKeys([[dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]])
              } else {
                setSelectedKeys([])
              }
            }}
            style={{ width: 250, marginBottom: 8, display: 'block' }}
            placeholder={['开始日期', '结束日期']}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => {
                const newFilters = { ...filters }
                if (selectedKeys[0]) {
                  const materialKey = `${key}_date_range` as keyof Filters
                  ;(newFilters as any)[materialKey] = selectedKeys[0]
                }
                setFilters(newFilters)
                confirm()
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters }
                const materialKey = `${key}_date_range` as keyof Filters
                ;(newFilters as any)[materialKey] = null
                setFilters(newFilters)
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
    })),
    // ── 生产节点 ──
    {
      title: '前道', dataIndex: 'front_process_date', key: 'front_process_date', minWidth: 80,
      render: (v: string, r: OrderRow) => <EditableDateCell value={v} record={r} field="front_process_date" />, sorter: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <RangePicker
            locale={zhCN.DatePicker}
            value={selectedKeys[0] ? [dayjs(selectedKeys[0][0]), dayjs(selectedKeys[0][1])] : null}
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setSelectedKeys([[dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]])
              } else {
                setSelectedKeys([])
              }
            }}
            style={{ width: 250, marginBottom: 8, display: 'block' }}
            placeholder={['开始日期', '结束日期']}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => {
                const newFilters = { ...filters, front_process_date_range: selectedKeys[0] || null }
                setFilters(newFilters)
                confirm()
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters, front_process_date_range: null }
                setFilters(newFilters)
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
    },
    {
      title: '首件检验日期', dataIndex: 'first_article_date', key: 'first_article_date', minWidth: 100,
      render: (v: string, r: OrderRow) => <EditableDateCell value={v} record={r} field="first_article_date" />, sorter: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <RangePicker
            locale={zhCN.DatePicker}
            value={selectedKeys[0] ? [dayjs(selectedKeys[0][0]), dayjs(selectedKeys[0][1])] : null}
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setSelectedKeys([[dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]])
              } else {
                setSelectedKeys([])
              }
            }}
            style={{ width: 250, marginBottom: 8, display: 'block' }}
            placeholder={['开始日期', '结束日期']}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => {
                const newFilters = { ...filters, first_article_date_range: selectedKeys[0] || null }
                setFilters(newFilters)
                confirm()
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters, first_article_date_range: null }
                setFilters(newFilters)
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
    },
    {
      title: '组装上线日期', dataIndex: 'assembly_start_date', key: 'assembly_start_date', minWidth: 100,
      render: (v: string, r: OrderRow) => <EditableDateCell value={v} record={r} field="assembly_start_date" />, sorter: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <RangePicker
            locale={zhCN.DatePicker}
            value={selectedKeys[0] ? [dayjs(selectedKeys[0][0]), dayjs(selectedKeys[0][1])] : null}
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setSelectedKeys([[dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]])
              } else {
                setSelectedKeys([])
              }
            }}
            style={{ width: 250, marginBottom: 8, display: 'block' }}
            placeholder={['开始日期', '结束日期']}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => {
                const newFilters = { ...filters, assembly_start_date_range: selectedKeys[0] || null }
                setFilters(newFilters)
                confirm()
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters, assembly_start_date_range: null }
                setFilters(newFilters)
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
    },
    {
      title: '组装完成日期', dataIndex: 'assembly_complete_date', key: 'assembly_complete_date', minWidth: 100,
      render: (v: string, r: OrderRow) => <EditableDateCell value={v} record={r} field="assembly_complete_date" green />, sorter: true,
      filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
        <div style={{ padding: 8 }}>
          <RangePicker
            locale={zhCN.DatePicker}
            value={selectedKeys[0] ? [dayjs(selectedKeys[0][0]), dayjs(selectedKeys[0][1])] : null}
            onChange={(dates) => {
              if (dates && dates[0] && dates[1]) {
                setSelectedKeys([[dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]])
              } else {
                setSelectedKeys([])
              }
            }}
            style={{ width: 250, marginBottom: 8, display: 'block' }}
            placeholder={['开始日期', '结束日期']}
          />
          <Space>
            <Button
              type="primary"
              onClick={() => {
                const newFilters = { ...filters, assembly_complete_date_range: selectedKeys[0] || null }
                setFilters(newFilters)
                confirm()
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters, assembly_complete_date_range: null }
                setFilters(newFilters)
                fetchOrders(pagination.current, pagination.pageSize, newFilters, sortInfo)
              }}
              size="small"
            >
              重置
            </Button>
          </Space>
        </div>
      ),
      filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
    },
    // ── 备注 ──
    {
      title: '备注', dataIndex: 'remark', key: 'remark', minWidth: 120,
      ellipsis: true,
      render: (v: string, r: OrderRow) => <EditableTextCell value={v} record={r} field="remark" />,
    },
    {
      title: '状态', dataIndex: 'status', key: 'status', minWidth: 80,
      render: (_: string, r: OrderRow) => <StatusTag status={calculateOrderStatus(r)} />,
      sorter: true,
      filters: [
        { text: '待处理', value: 'open' },
        { text: '处理中', value: 'in_progress' },
        { text: '在产', value: 'in_production' },
        { text: '已关闭', value: 'closed' },
      ],
      filterMultiple: true,
    },
    {
      title: '', key: 'action', minWidth: 50, fixed: 'right' as const,
      render: (_: any, r: OrderRow) => (
        <Tooltip title="编辑">
          <Button type="link" size="small" icon={<EditOutlined />}
            onClick={() => openEditModal(r)}
          />
        </Tooltip>
      ),
    },
  ].map(col =>
    col.key === 'action' ? col : { ...col, ellipsis: true, minWidth: Math.min(col.minWidth || 100, 100) }
  ), [isEditingCell, handleCellSave, startEditCell, cancelEditCell, navigate, filters, pagination, sortInfo, fetchOrders, openEditModal])

  return (
    <div>

      <div className="card-modern" style={{ padding: '14px 20px', marginBottom: 16 }}>
        <Row gutter={[12, 12]} align="middle">
          <Col xs={24} sm={12} md={5}>
            <Input
              placeholder="搜索订单号/客户/产品"
              prefix={<SearchOutlined />}
              allowClear
              value={filters.keyword}
              onChange={e => {
                const newKeyword = e.target.value
                setFilters(f => ({ ...f, keyword: newKeyword }))
                // 直接传递新的keyword值，避免状态更新延迟问题
                const newFilters = { ...filters, keyword: newKeyword }
                fetchOrders(1, 50, newFilters)
              }}
            />
          </Col>
          <Col xs={24} sm={12} md={3}>
            <Button 
              icon={<ReloadOutlined />} 
              onClick={() => fetchOrders()}
            >
              刷新
            </Button>
          </Col>
          <Col>
            <Switch
              checked={filters.delivery_completed.includes('no')}
              onChange={handleUnfinishedOrdersToggle}
              checkedChildren="未完成订单"
              unCheckedChildren="全部订单"
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Dropdown
                menu={{
                  items: [
                    { key: 'xlsx', label: '导出 Excel', icon: <DownloadOutlined /> },
                    { key: 'csv', label: '导出 CSV', icon: <DownloadOutlined /> },
                  ],
                  onClick: ({ key }) => handleExportClick(key as 'xlsx' | 'csv'),
                }}
              >
                <Button icon={<DownloadOutlined />} loading={exporting}>导出 <DownOutlined /></Button>
              </Dropdown>
              <Button type="primary" icon={<AuditOutlined />} onClick={handleScan} loading={scanning}>风险扫描</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '2px 0 0' }}>
        <div className="table-modern">
          <Table
            columns={columns}
            dataSource={orders}
            rowKey={(r) => `${r.id}`}
            loading={loading}
            size="small"
            scroll={{ x: 'max-content', y: 'calc(100vh - 380px)' }}
            locale={{ emptyText: '暂无订单数据' }}
            onChange={handleTableChange}
            summary={() => (
              <Table.Summary fixed>
                <Table.Summary.Row>
                  <Table.Summary.Cell index={0} colSpan={7}>
                    <span style={{ fontWeight: 600 }}>合计</span>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={7} align="right">
                    <span style={{ fontWeight: 600 }}>{summary.order_qty_total?.toLocaleString() || '0'}</span>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={8} align="right">
                    <span style={{ fontWeight: 600 }}>{summary.order_amount_total?.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}</span>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={9} colSpan={columns.length - 10} />
                </Table.Summary.Row>
              </Table.Summary>
            )}
            expandable={{
              expandedRowKeys: expandedKeys,
              onExpandedRowsChange: (keys) => {
                const newKeys = keys as string[]
                // auto-fetch detail for newly expanded rows
                const added = newKeys.filter(k => !expandedKeys.includes(k))
                added.forEach(key => {
                  const order = orders.find(o => `${o.id}` === key)
                  if (order) fetchDetail(order.order_no, null)
                })
                setExpandedKeys(newKeys)
              },
              expandedRowRender: (record: OrderRow) => {
                const cacheKey = `${record.order_no}_${record.line_no || '10'}`
                const detail = detailCache[cacheKey]
                if (detailLoading[cacheKey] && !detail) {
                  return <div style={{ textAlign: 'center', padding: 24 }}><Spin /></div>
                }
                const lineColumns = [
                  { 
                    title: '明细ID', 
                    dataIndex: 'erp_line_id', 
                    width: 120, 
                    ellipsis: true, 
                    render: (v: string) => v || '-',
                    filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
                      <div style={{ padding: 8 }}>
                        <Input
                          placeholder="输入明细ID"
                          value={selectedKeys[0]}
                          onChange={(e) => setSelectedKeys(e.target.value ? [e.target.value] : [])}
                          style={{ width: 188, marginBottom: 8, display: 'block' }}
                        />
                        <Space>
                          <Button
                            type="primary"
                            onClick={() => confirm()}
                            size="small"
                          >
                            筛选
                          </Button>
                          <Button
                            onClick={() => clearFilters()}
                            size="small"
                          >
                            重置
                          </Button>
                        </Space>
                      </div>
                    ),
                    filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
                    onFilter: (value: any, record: any) => 
                      record.erp_line_id ? record.erp_line_id.toLowerCase().includes(String(value).toLowerCase()) : false,
                  },
                  { 
                    title: '产品编码', 
                    dataIndex: 'product_code', 
                    width: 150, 
                    ellipsis: true,
                    filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
                      <div style={{ padding: 8 }}>
                        <Input
                          placeholder="输入产品编码"
                          value={selectedKeys[0]}
                          onChange={(e) => setSelectedKeys(e.target.value ? [e.target.value] : [])}
                          style={{ width: 188, marginBottom: 8, display: 'block' }}
                        />
                        <Space>
                          <Button
                            type="primary"
                            onClick={() => confirm()}
                            size="small"
                          >
                            筛选
                          </Button>
                          <Button
                            onClick={() => clearFilters()}
                            size="small"
                          >
                            重置
                          </Button>
                        </Space>
                      </div>
                    ),
                    filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
                    onFilter: (value: any, record: any) => 
                      record.product_code ? record.product_code.toLowerCase().includes(String(value).toLowerCase()) : false,
                  },
                  { 
                    title: '产品名称', 
                    dataIndex: 'product_name', 
                    width: 200, 
                    ellipsis: true,
                    filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
                      <div style={{ padding: 8 }}>
                        <Input
                          placeholder="输入产品名称"
                          value={selectedKeys[0]}
                          onChange={(e) => setSelectedKeys(e.target.value ? [e.target.value] : [])}
                          style={{ width: 188, marginBottom: 8, display: 'block' }}
                        />
                        <Space>
                          <Button
                            type="primary"
                            onClick={() => confirm()}
                            size="small"
                          >
                            筛选
                          </Button>
                          <Button
                            onClick={() => clearFilters()}
                            size="small"
                          >
                            重置
                          </Button>
                        </Space>
                      </div>
                    ),
                    filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
                    onFilter: (value: any, record: any) => 
                      record.product_name ? record.product_name.toLowerCase().includes(String(value).toLowerCase()) : false,
                  },
                  { 
                    title: '产品型号', 
                    dataIndex: 'product_model', 
                    width: 150, 
                    ellipsis: true,
                    render: (v: string) => v || '-',
                  },
                  {
                    title: '数量',
                    dataIndex: 'order_qty',
                    width: 100,
                    render: (v: number) => v?.toLocaleString() || '-',
                    filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
                      <div style={{ padding: 8 }}>
                        <Input
                          placeholder="输入数量"
                          value={selectedKeys[0]}
                          onChange={(e) => setSelectedKeys(e.target.value ? [e.target.value] : [])}
                          style={{ width: 188, marginBottom: 8, display: 'block' }}
                        />
                        <Space>
                          <Button
                            type="primary"
                            onClick={() => confirm()}
                            size="small"
                          >
                            筛选
                          </Button>
                          <Button
                            onClick={() => clearFilters()}
                            size="small"
                          >
                            重置
                          </Button>
                        </Space>
                      </div>
                    ),
                    filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
                    onFilter: (value: any, record: any) =>
                      record.order_qty ? record.order_qty.toString().includes(String(value)) : false,
                  },
                  {
                    title: '金额',
                    dataIndex: 'order_amount',
                    width: 120,
                    align: 'right' as const,
                    render: (v: number) => v?.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '-',
                  },
                  {
                    title: '交期',
                    dataIndex: 'promised_date',
                    width: 120,
                    render: (v: string) => <DateCell value={v} overdue={!!(v && v < today())} />,
                    filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
                      <div style={{ padding: 8 }}>
                        <RangePicker
                          locale={zhCN.DatePicker}
                          value={selectedKeys[0] ? [dayjs(selectedKeys[0][0]), dayjs(selectedKeys[0][1])] : null}
                          onChange={(dates) => {
                            if (dates && dates[0] && dates[1]) {
                              setSelectedKeys([[dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')]])
                            } else {
                              setSelectedKeys([])
                            }
                          }}
                          style={{ width: 250, marginBottom: 8, display: 'block' }}
                          placeholder={['开始日期', '结束日期']}
                        />
                        <Space>
                          <Button
                            type="primary"
                            onClick={() => confirm()}
                            size="small"
                          >
                            筛选
                          </Button>
                          <Button
                            onClick={() => clearFilters()}
                            size="small"
                          >
                            重置
                          </Button>
                        </Space>
                      </div>
                    ),
                    filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1890ff' : undefined }} />,
                    onFilter: (value: any, record: any) => {
                      if (!value || !Array.isArray(value) || value.length !== 2) return true
                      const date = record.promised_date
                      if (!date) return false
                      return date >= value[0] && date <= value[1]
                    },
                  },
                ]
                if (!detail) return null
                return (
                  <div style={{ padding: '8px 0' }}>
                    <Table
                      columns={lineColumns}
                      dataSource={detail.lines}
                      rowKey="id"
                      size="small"
                      pagination={false}
                      scroll={{ x: 570 }}
                      locale={{ emptyText: '暂无明细行' }}
                    />
                  </div>
                )
              },
            }}
            pagination={{
              ...pagination,
              showSizeChanger: true,
              pageSizeOptions: ['20', '50', '100'],
              showTotal: (total) => `共 ${total} 条`,
              style: { padding: '0 16px' },
            }}
          />
        </div>
      </div>

      {/* ── 编辑弹窗 ── */}
      <Modal
        title={<span><EditOutlined style={{ marginRight: 8 }} />编辑订单 — {editingRecord?.order_no}</span>}
        open={editModalOpen}
        onCancel={() => { setEditModalOpen(false); setEditingRecord(null) }}
        width={960}
        style={{ top: 32 }}
        footer={[
          <Button key="cancel" icon={<CloseOutlined />} onClick={() => { setEditModalOpen(false); setEditingRecord(null) }}>取消</Button>,
          <Button key="save" type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleEditSave}>保存</Button>,
        ]}
        destroyOnClose
      >
        <Form form={editForm} layout="vertical" size="small">
          {/* ── 不可编辑字段(只读展示) ── */}
          <Row gutter={12} style={{ marginBottom: 8, padding: '8px 12px', background: '#f8fafc', borderRadius: 8 }}>
            <Col span={4}><span style={{ color: '#64748b', fontSize: 12 }}>销售部门</span><div style={{ fontWeight: 500 }}>{editingRecord?.department || '-'}</div></Col>
            <Col span={4}><span style={{ color: '#64748b', fontSize: 12 }}>客户</span><div style={{ fontWeight: 500 }}>{editingRecord?.customer || editingRecord?.customer_code || '-'}</div></Col>
            <Col span={6}><span style={{ color: '#64748b', fontSize: 12 }}>单号</span><div style={{ fontWeight: 500 }}>{editingRecord?.order_no || '-'}</div></Col>
            <Col span={4}><span style={{ color: '#64748b', fontSize: 12 }}>数量</span><div style={{ fontWeight: 500 }}>{editingRecord?.order_qty?.toLocaleString() || '-'}</div></Col>
            <Col span={6}><span style={{ color: '#64748b', fontSize: 12 }}>合同交期</span><div style={{ fontWeight: 500 }}>{editingRecord?.promised_date || '-'}</div></Col>
          </Row>

          {/* ── 可编辑字段 ── */}
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item name="delivery_completed_date" label="发货完成">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="customer_grade" label="客户等级">
                <Select allowClear placeholder="选择等级" options={[
                  { value: 'A', label: 'A级' }, { value: 'B', label: 'B级' },
                  { value: 'C', label: 'C级' }, { value: 'D', label: 'D级' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="shipping_plan" label="出货计划">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item name="customer_inspection_date" label="客户验货时间">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="planned_start_date" label="上线时间">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="inspection_result" label="客检结果">
                <Select allowClear placeholder="选择结果" options={[
                  { value: 'OK', label: 'OK / 通过' }, { value: 'NG', label: 'NG / 不通过' },
                  { value: '待检', label: '待检' },
                ]} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item name="packaging_status" label="包装完成状况">
                <Input allowClear placeholder="如：完成/入库" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="bom_return_date" label="BOM回收">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="material_ready_date" label="料齐套时间">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="shipping_status_desc" label="发货状态即时说明">
                <Input allowClear placeholder="发货状态说明" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="procurement_status" label="采购物料齐套">
                <Input allowClear placeholder="采购齐套状态" />
              </Form.Item>
            </Col>
          </Row>

          {/* ── 物料分类到料日期 ── */}
          <div style={{ margin: '8px 0 4px', fontWeight: 600, fontSize: 'calc(0.8125rem * var(--font-size-scale))', color: '#334155' }}>物料分类到料日期</div>
          <Row gutter={12}>
            {MATERIAL_KEYS.map(key => (
              <Col span={6} key={key}>
                <Form.Item name={`mat_${key}`} label={key} style={{ marginBottom: 8 }}>
                  <DatePicker style={{ width: '100%' }} size="small" />
                </Form.Item>
              </Col>
            ))}
          </Row>

          {/* ── 生产节点 ── */}
          <div style={{ margin: '12px 0 4px', fontWeight: 600, fontSize: 'calc(0.8125rem * var(--font-size-scale))', color: '#334155' }}>生产节点</div>
          <Row gutter={12}>
            <Col span={6}>
              <Form.Item name="front_process_date" label="前道">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="first_article_date" label="首件检验日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="assembly_start_date" label="组装上线日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="assembly_complete_date" label="组装完成日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>

          {/* ── 风险 & 备注 ── */}
          <Row gutter={12}>
            <Col span={8}>
              <Form.Item name="risk_level" label="风险等级">
                <Select allowClear placeholder="选择风险等级" options={[
                  { value: 'red', label: '高风险' }, { value: 'yellow', label: '中风险' },
                  { value: 'green', label: '正常' },
                ]} />
              </Form.Item>
            </Col>
            <Col span={16}>
              <Form.Item name="remark" label="备注">
                <Input.TextArea rows={2} placeholder="备注信息" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      {/* ── 风险详情弹窗 ── */}
      <RiskDetailModal
        visible={riskModalOpen}
        order={selectedOrder}
        onClose={() => { setRiskModalOpen(false); setSelectedOrder(null) }}
      />

      {/* ── 导出列选择弹窗 ── */}
      <ExportColumnSelector
        open={exportColumnModalOpen}
        columns={generateExportColumns(columns)}
        onConfirm={handleExportColumnConfirm}
        onCancel={handleExportColumnCancel}
      />
    </div>
  )
}
