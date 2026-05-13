import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Row, Col, Table, Tag, Input, Select, Button, message, Space, Tooltip, Modal, Form, DatePicker, Card, Spin, Progress } from 'antd'
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
} from '@ant-design/icons'
import dayjs from 'dayjs'
import RiskBadge from '../../../components/RiskBadge'
import StatusTag from '../../../components/StatusTag'
import RiskDetailModal from '../../../components/RiskDetailModal'
import { orderApi, riskApi } from '../../../services/api'
import { formatDate, formatDateTime } from '../../../utils'

interface OrderRow {
  id: number
  order_no: string
  line_no: string | null
  customer: string | null
  customer_code: string | null
  product_code: string | null
  product_name: string | null
  order_qty: number | null
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
  order_qty: number | null
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

const STAT_COLORS: Record<string, string> = {
  'stat-total': '#6366f1', 'stat-red': '#e11d48', 'stat-yellow': '#f59e0b',
  'stat-green': '#16a34a', 'stat-overdue': '#e11d48', 'stat-transit': '#2563eb',
}

function StatCard({ icon, label, value, className }: {
  icon: React.ReactNode; label: string; value: number | string; className: string
}) {
  const color = STAT_COLORS[className] || '#6366f1'
  return (
    <Card size="small" className="card-modern" style={{ padding: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 44, height: 44, borderRadius: 10, background: `${color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, color }}>
          {icon}
        </div>
        <div>
          <div style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>{value ?? '-'}</div>
          <div style={{ fontSize: 12, color: '#64748b' }}>{label}</div>
        </div>
      </div>
    </Card>
  )
}

export default function OrderList() {
  const navigate = useNavigate()
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
    delivery_completed: [],
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
  const [summary, setSummary] = useState({ total: 0, red: 0, yellow: 0, blue: 0, green: 0, shortage: 0 })
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<OrderRow | null>(null)
  const [editForm] = Form.useForm()
  const [saving, setSaving] = useState(false)
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])
  const [detailCache, setDetailCache] = useState<Record<string, OrderDetailData>>({})
  const [detailLoading, setDetailLoading] = useState<Record<string, boolean>>({})
  const [riskModalOpen, setRiskModalOpen] = useState(false)
  const [selectedOrder, setSelectedOrder] = useState<OrderRow | null>(null)

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
      })
    } catch {
      message.error('获取订单列表失败')
    } finally {
      setLoading(false)
    }
  }, [filters, sortInfo])

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchOrders() }, [])

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
    const deliveryCompletedFilter = tableFilters.delivery_completed_date?.length > 0 ? tableFilters.delivery_completed_date : []
    
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

  const columns: any[] = [
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
      render: (v: string) => <GreenDateCell value={v} />, sorter: true,
      filters: [
        { text: '已发货', value: 'yes' },
        { text: '未发货', value: 'no' },
      ],
      filterMultiple: true,
    },
    {
      title: '客户等级', dataIndex: 'customer_grade', key: 'customer_grade', minWidth: 60, fixed: 'left' as const,
      render: (v: string) => v ? <Tag color={v === 'A' ? 'red' : v === 'B' ? 'orange' : v === 'C' ? 'blue' : 'default'}>{v}</Tag> : '-',
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
      render: (v: string) => {
        if (!v) return '-'
        const firstDashIndex = v.indexOf('-')
        const displayValue = firstDashIndex !== -1 ? v.substring(firstDashIndex + 1) : v
        return <Tooltip title={v}>{displayValue}</Tooltip>
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
        record.customer_code ? record.customer_code.toLowerCase().includes(value.toLowerCase()) : false,
    },
    {
      title: '单号', dataIndex: 'order_no', key: 'order_no', minWidth: 100, fixed: 'left' as const,
      render: (v: string, r: OrderRow) => {
        if (!v) return '-'
        const lastDashIndex = v.lastIndexOf('-')
        const afterDash = lastDashIndex !== -1 ? v.substring(lastDashIndex + 1) : v
        // 去除前导零，但至少保留3位
        const displayValue = afterDash.replace(/^0+/, '').padStart(3, '0')
        return (
          <Tooltip title={v}>
            <a onClick={() => navigate(`/orders/${v}/lines/${r.line_no || '10'}`)} style={{ fontWeight: 600, fontSize: 12 }}>{displayValue}</a>
          </Tooltip>
        )
      }, sorter: true,
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
      title: '风险等级', dataIndex: 'risk_level', key: 'risk_level', minWidth: 80, fixed: 'left' as const,
      render: (v: string, r: OrderRow) => <RiskBadge level={v} onClick={() => { setSelectedOrder(r); setRiskModalOpen(true) }} />,
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
                if (selectedKeys[0]) {
                  setFilters(prev => ({ ...prev, order_date_range: selectedKeys[0] }))
                }
                confirm()
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                setFilters(prev => ({ ...prev, order_date_range: null }))
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
      render: (v: string, r: OrderRow) => <DateCell value={v} overdue={!!(v && v < today() && r.status !== 'closed')} />, sorter: true,
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
                if (selectedKeys[0]) {
                  setFilters(prev => ({ ...prev, promised_date_range: selectedKeys[0] }))
                }
                confirm()
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                setFilters(prev => ({ ...prev, promised_date_range: null }))
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
      render: (v: string) => v ? <span style={{ color: '#ca8a04', fontWeight: 500 }}>{v}</span> : <span style={{ color: '#cbd5e1' }}>-</span>, sorter: true,
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
                if (selectedKeys[0]) {
                  setFilters(prev => ({ ...prev, shipping_plan_range: selectedKeys[0] }))
                }
                confirm()
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                setFilters(prev => ({ ...prev, shipping_plan_range: null }))
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
                if (selectedKeys[0]) {
                  const newFilters = { ...filters }
                  newFilters.customer_inspection_date_range = selectedKeys[0]
                  setFilters(newFilters)
                }
                confirm()
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters }
                newFilters.customer_inspection_date_range = null
                setFilters(newFilters)
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
                if (selectedKeys[0]) {
                  const newFilters = { ...filters }
                  newFilters.planned_start_date_range = selectedKeys[0]
                  setFilters(newFilters)
                }
                confirm()
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters }
                newFilters.planned_start_date_range = null
                setFilters(newFilters)
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
      render: (v: string) => {
        if (!v) return '-'
        const color = v === 'OK' || v === '通过' ? '#16a34a' : v === 'NG' ? '#e11d48' : undefined
        return <span style={{ color, fontWeight: 600 }}>{v}</span>
      },
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
      render: (v: string) => {
        if (!v) return '-'
        const isBlue = v.includes('完成') && !v.includes('入库')
        const isGreen = v.includes('入库')
        return <span style={{ color: isGreen ? '#16a34a' : isBlue ? '#2563eb' : undefined }}>{v}</span>
      },
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
      render: (v: string) => <DateCell value={v} />, sorter: true,
    },
    {
      title: '料齐套时间', dataIndex: 'material_ready_date', key: 'material_ready_date', minWidth: 85,
      render: (v: string) => <GreenDateCell value={v} />, sorter: true,
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
                if (selectedKeys[0]) {
                  const newFilters = { ...filters }
                  newFilters.material_ready_date_range = selectedKeys[0]
                  setFilters(newFilters)
                }
                confirm()
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters }
                newFilters.material_ready_date_range = null
                setFilters(newFilters)
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
      render: (v: string) => {
        if (!v) return '-'
        const overdue = v.includes('超期')
        return <span style={{ color: overdue ? '#e11d48' : undefined }}>{v}</span>
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
        const val = r.material_dates?.[key]
        if (!val) return <span style={{ color: '#cbd5e1' }}>-</span>
        return <span style={{ fontSize: 12 }}>{formatDate(val)}</span>
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
                if (selectedKeys[0]) {
                  const newFilters = { ...filters }
                  const materialKey = `${key}_date_range` as keyof Filters
                  ;(newFilters as any)[materialKey] = selectedKeys[0]
                  setFilters(newFilters)
                }
                confirm()
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
                if (selectedKeys[0]) {
                  const newFilters = { ...filters }
                  newFilters.front_process_date_range = selectedKeys[0]
                  setFilters(newFilters)
                }
                confirm()
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters }
                newFilters.front_process_date_range = null
                setFilters(newFilters)
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
                if (selectedKeys[0]) {
                  const newFilters = { ...filters }
                  newFilters.first_article_date_range = selectedKeys[0]
                  setFilters(newFilters)
                }
                confirm()
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters }
                newFilters.first_article_date_range = null
                setFilters(newFilters)
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
                if (selectedKeys[0]) {
                  const newFilters = { ...filters }
                  newFilters.assembly_start_date_range = selectedKeys[0]
                  setFilters(newFilters)
                }
                confirm()
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters }
                newFilters.assembly_start_date_range = null
                setFilters(newFilters)
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
      render: (v: string) => <GreenDateCell value={v} />, sorter: true,
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
                if (selectedKeys[0]) {
                  const newFilters = { ...filters }
                  newFilters.assembly_complete_date_range = selectedKeys[0]
                  setFilters(newFilters)
                }
                confirm()
              }}
              size="small"
            >
              筛选
            </Button>
            <Button
              onClick={() => {
                clearFilters()
                const newFilters = { ...filters }
                newFilters.assembly_complete_date_range = null
                setFilters(newFilters)
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
      title: '备注', dataIndex: 'remark', key: 'remark', minWidth: 120, fixed: 'right' as const,
      ellipsis: true,
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
  )

  return (
    <div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '总订单', value: summary.total, icon: <ShoppingCartOutlined />, color: '#6366f1' },
          { title: '高风险', value: summary.red, icon: <WarningOutlined />, color: '#e11d48' },
          { title: '中风险', value: summary.yellow, icon: <ExclamationCircleOutlined />, color: '#f59e0b' },
          { title: '低风险', value: summary.blue, icon: <CheckCircleOutlined />, color: '#2563eb' },
          { title: '正常', value: summary.green, icon: <CheckCircleOutlined />, color: '#16a34a' },
        ].map((card, i) => (
          <Col flex={1} key={i}>
            <Card size="small" className="card-modern" style={{ padding: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ width: 44, height: 44, borderRadius: 10, background: `${card.color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, color: card.color }}>
                  {card.icon}
                </div>
                <div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>{card.value}</div>
                  <div style={{ fontSize: 12, color: '#64748b' }}>{card.title}</div>
                </div>
              </div>
            </Card>
          </Col>
        ))}
      </Row>

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
          <Col flex="auto" />
          <Col>
            <Space>
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
                  { title: '明细ID', dataIndex: 'erp_line_id', width: 120, ellipsis: true, render: (v: string) => v || '-' },
                  { title: '产品编码', dataIndex: 'product_code', width: 150, ellipsis: true },
                  { title: '产品名称', dataIndex: 'product_name', width: 200, ellipsis: true },
                  { title: '数量', dataIndex: 'order_qty', width: 100, render: (v: number) => v?.toLocaleString() || '-' },
                  { title: '交期', dataIndex: 'promised_date', width: 120, render: (v: string) => <DateCell value={v} overdue={!!(v && v < today())} /> },
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
            <Col span={4}><span style={{ color: '#64748b', fontSize: 12 }}>客户</span><div style={{ fontWeight: 500 }}>{editingRecord?.customer_code || '-'}</div></Col>
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
          <div style={{ margin: '8px 0 4px', fontWeight: 600, fontSize: 13, color: '#334155' }}>物料分类到料日期</div>
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
          <div style={{ margin: '12px 0 4px', fontWeight: 600, fontSize: 13, color: '#334155' }}>生产节点</div>
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
    </div>
  )
}
