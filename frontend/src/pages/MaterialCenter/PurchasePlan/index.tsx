import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import {
  Table, Tag, Input, InputNumber, Select, Button, Space, message, Modal, Form,
  DatePicker, Upload, Tooltip, Row, Col, Card, Dropdown, Switch,
} from 'antd'
import {
  SearchOutlined, FilterOutlined, ReloadOutlined, UploadOutlined, PlusOutlined, EditOutlined,
  ShoppingOutlined, ClockCircleOutlined, CheckCircleOutlined,
  WarningOutlined, ExclamationCircleOutlined, StopOutlined,
  DownloadOutlined, DownOutlined, MessageOutlined, CopyOutlined,
  BarChartOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { materialApi, orderApi, userApi } from '../../../services/api'
import { formatDate } from '../../../utils'
import { useExport } from '../../../hooks/useExport'
import { useAuthStore } from '../../../store/auth'
import AnalysisCharts from './components/AnalysisCharts'
import SupplierChatModal from './components/SupplierChatModal'

interface PlanRow {
  id: number
  po_no: string
  supplier_name: string | null
  supplier_account: string | null
  material_code: string
  material_name: string | null
  spec_model: string | null
  unit: string | null
  po_qty: number | null
  received_qty: number | null
  original_eta: string | null
  eta: string | null
  order_no: string | null
  actual_arrival_date: string | null
  arrival_hour_note: string | null
  inspection_date: string | null
  po_status: string
  is_stagnant: boolean
  stagnant_qty: number | null
  shortage_qty: number | null
  owner: string | null
  owner_id: number | null
  po_date: string | null
  is_closed: number
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  fully_received: { label: '已到齐', color: 'success' },
  partial_received: { label: '部分到', color: 'warning' },
  overdue: { label: '逾期未到', color: 'error' },
  pending: { label: '待到料', color: 'default' },
  stagnant: { label: '呆滞物料', color: 'warning' },
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

export default function PurchasePlan() {
  const hasPermission = useAuthStore((s) => s.hasPermission)
  const canCreate = hasPermission('materials.purchase_plan', 'create')
  const canUpdate = hasPermission('materials.purchase_plan', 'update')
  const canImport = hasPermission('materials.purchase_plan', 'import')
  const [data, setData] = useState<PlanRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState({
    keyword: '',
    po_status: [] as string[],
    supplier_name: '',
    supplier_account: '',
    material_code: '',
    material_name: '',
    material_property: undefined as number | undefined,
    spec_model: '',
    unit: '',
    owner: '',
    order_no: '',
    arrival_hour_note: '',
    po_no: '',
    po_date: null as [string, string] | null,
    eta: null as [string, string] | null,
    actual_arrival_date: null as [string, string] | null,
    inspection_date: null as [string, string] | null,
    po_qty: null as [number, number] | null,
    received_qty: null as [number, number] | null,
    only_shortage: false,
    is_closed: [] as string[],
  })
  const [sortBy, setSortBy] = useState<string>('')
  const [sortOrder, setSortOrder] = useState<string>('')
  const [editModal, setEditModal] = useState(false)
  const [editRecord, setEditRecord] = useState<PlanRow | null>(null)
  const [addModal, setAddModal] = useState(false)
  const [orderList, setOrderList] = useState<any[]>([])
  const [orderLoading, setOrderLoading] = useState(false)
  const [form] = Form.useForm()
  const [batchForm] = Form.useForm()
  const uploadRef = useRef<any>(null)
  const { exporting, exportData } = useExport()
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([])
  const [batchEditModal, setBatchEditModal] = useState(false)
  const [chatModalOpen, setChatModalOpen] = useState(false)
  const [chatRecord, setChatRecord] = useState<PlanRow | null>(null)
  const [userOptions, setUserOptions] = useState<{ value: number; label: string; display_name: string }[]>([])
  const [userSearching, setUserSearching] = useState(false)
  const [batchUserOptions, setBatchUserOptions] = useState<{ value: number; label: string; display_name: string }[]>([])
  const [addUserOptions, setAddUserOptions] = useState<{ value: number; label: string; display_name: string }[]>([])
  const [savingCell, setSavingCell] = useState<string | null>(null)
  const [editingCell, setEditingCell] = useState<string | null>(null)

  const apiFilterParams = useMemo(() => {
    const p: Record<string, any> = {}
    if (filters.keyword) p.keyword = filters.keyword
    if (filters.po_status.length) p.po_status = filters.po_status.join(',')
    const textKeys = ['supplier_name', 'supplier_account', 'material_code', 'material_name', 'spec_model', 'unit', 'owner', 'order_no', 'arrival_hour_note', 'po_no'] as const
    textKeys.forEach(k => { if (filters[k]) p[k] = filters[k] })
    if (filters.po_date) { p.po_date_start = filters.po_date[0]; p.po_date_end = filters.po_date[1] }
    if (filters.eta) { p.eta_start = filters.eta[0]; p.eta_end = filters.eta[1] }
    if (filters.actual_arrival_date) { p.actual_arrival_start = filters.actual_arrival_date[0]; p.actual_arrival_end = filters.actual_arrival_date[1] }
    if (filters.inspection_date) { p.inspection_start = filters.inspection_date[0]; p.inspection_end = filters.inspection_date[1] }
    if (filters.po_qty) { p.po_qty_min = filters.po_qty[0]; p.po_qty_max = filters.po_qty[1] }
    if (filters.received_qty) { p.received_qty_min = filters.received_qty[0]; p.received_qty_max = filters.received_qty[1] }
    if (filters.material_property !== undefined) p.material_property = filters.material_property
    if (filters.only_shortage) p.only_shortage = true
    if (filters.is_closed.length) p.is_closed = filters.is_closed.join(',')
    return p
  }, [filters])

  const handleExport = (format: 'xlsx' | 'csv') => {
    const params: Record<string, any> = { format, ...apiFilterParams }
    if (sortBy) { params.sort_by = sortBy; params.sort_order = sortOrder || 'asc' }
    const ext = format === 'csv' ? 'csv' : 'xlsx'
    exportData(`/api/v1/materials/purchase-plan/export`, params, `采购到料计划.${ext}`)
  }
  const [stats, setStats] = useState({ total: 0, pending: 0, partial_received: 0, fully_received: 0, overdue: 0, stagnant: 0, closed: 0 })
  const [showCharts, setShowCharts] = useState(false)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisData, setAnalysisData] = useState<{
    status_distribution: { name: string; value: number; color?: string }[]
    supplier_overdue_top5: { name: string; value: number }[]
    material_shortage_top5: { name: string; value: number }[]
  }>({ status_distribution: [], supplier_overdue_top5: [], material_shortage_top5: [] })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await materialApi.listPurchasePlan({
        page, page_size: pageSize,
        ...apiFilterParams,
        ...(sortBy ? { sort_by: sortBy, sort_order: sortOrder || 'asc' } : {}),
      })
      setData(res.data.items)
      setTotal(res.data.total)
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, apiFilterParams, sortBy, sortOrder])

  const loadOrders = useCallback(async (keyword = '') => {
    setOrderLoading(true)
    try {
      const res: any = await orderApi.list({ page: 1, page_size: 100, keyword })
      setOrderList(res.data.items || [])
    } catch (e: any) {
      message.error('加载订单列表失败')
    } finally {
      setOrderLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const loadStats = useCallback(async () => {
    try {
      const res: any = await materialApi.getPurchasePlanStats(apiFilterParams)
      setStats(res.data)
    } catch (e: any) {
      console.error('加载统计数据失败', e)
    }
  }, [apiFilterParams])

  useEffect(() => { loadStats() }, [loadStats])

  const loadAnalysis = useCallback(async () => {
    setAnalysisLoading(true)
    try {
      const res: any = await materialApi.getPurchasePlanAnalysis(apiFilterParams)
      setAnalysisData(res.data)
    } catch (e: any) {
      console.error('加载分析数据失败', e)
    } finally {
      setAnalysisLoading(false)
    }
  }, [apiFilterParams])

  const toggleCharts = () => {
    const next = !showCharts
    setShowCharts(next)
    if (next) {
      loadAnalysis()
    }
  }

  const searchUsers = useCallback(async (keyword: string, mode: 'edit' | 'batch' | 'add' = 'edit') => {
    setUserSearching(true)
    try {
      const res: any = await userApi.employeeOptions({ keyword: keyword || undefined })
      const options = (res.data || []).map((u: any) => ({
        value: u.id,
        label: u.display_name || u.username,
        display_name: u.display_name || u.username,
      }))
      if (mode === 'batch') {
        setBatchUserOptions(options)
      } else if (mode === 'add') {
        setAddUserOptions(options)
      } else {
        setUserOptions(options)
      }
    } catch {
      // ignore
    } finally {
      setUserSearching(false)
    }
  }, [])

  const openEdit = (row: PlanRow) => {
    setEditRecord(row)
    loadOrders()
    form.setFieldsValue({
      supplier_name: row.supplier_name,
      supplier_account: row.supplier_account,
      material_code: row.material_code,
      material_name: row.material_name,
      spec_model: row.spec_model,
      unit: row.unit,
      po_qty: row.po_qty,
      received_qty: row.received_qty,
      eta: row.eta ? dayjs(row.eta) : null,
      order_no: row.order_no,
      actual_arrival_date: row.actual_arrival_date ? dayjs(row.actual_arrival_date) : null,
      arrival_hour_note: row.arrival_hour_note,
      inspection_date: row.inspection_date ? dayjs(row.inspection_date) : null,
      owner: row.owner,
      owner_id: row.owner_id,
      is_closed: row.is_closed,
    })
    setEditModal(true)
    if (row.owner) {
      searchUsers(row.owner, 'edit')
    }
  }

  const handleEditSubmit = async (values: any) => {
    try {
      if (!editRecord) return
      const payload: Record<string, any> = {
        supplier_name: values.supplier_name,
        supplier_account: values.supplier_account || null,
        material_name: values.material_name,
        spec_model: values.spec_model,
        unit: values.unit,
        po_qty: values.po_qty,
        received_qty: values.received_qty,
        eta: values.eta ? dayjs(values.eta).format('YYYY-MM-DD') : null,
        order_no: values.order_no,
        actual_arrival_date: values.actual_arrival_date ? dayjs(values.actual_arrival_date).format('YYYY-MM-DD') : null,
        arrival_hour_note: values.arrival_hour_note,
        inspection_date: values.inspection_date ? dayjs(values.inspection_date).format('YYYY-MM-DD') : null,
        owner: values.owner || null,
        owner_id: values.owner_id || null,
        is_closed: values.is_closed ? 1 : 0,
      }
      await materialApi.updatePurchasePlan(editRecord.id, payload)
      message.success('保存成功')
      setEditModal(false)
      load()
      loadStats()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const handleCellSave = async (row: PlanRow, field: keyof PlanRow, value: any) => {
    const cellKey = `${row.id}-${String(field)}`
    if (savingCell) return
    setSavingCell(cellKey)
    try {
      const payload = { [field]: value ?? null }
      const res: any = await materialApi.updatePurchasePlan(row.id, payload)
      setData(prev => prev.map(item => (item.id === row.id ? { ...item, ...res.data } : item)))
      loadStats()
      message.success('保存成功')
    } catch (e: any) {
      message.error(e.message || '保存失败')
    } finally {
      setSavingCell(null)
    }
  }

  const editableText = (field: keyof PlanRow) => (value: string | null, row: PlanRow) => {
    if (!canUpdate) {
      return <div style={{ padding: '4px 8px', minHeight: '24px' }}>{value || <span style={{ color: '#cbd5e1' }}>-</span>}</div>
    }
    const cellKey = `${row.id}-${String(field)}`
    const isEditing = editingCell === cellKey
    return (
      isEditing ? (
        <Input
          size="small"
          defaultValue={value || ''}
          disabled={savingCell === cellKey}
          autoFocus
          onBlur={e => {
            const next = e.target.value.trim()
            if ((value || '') !== next) handleCellSave(row, field, next || null)
            setEditingCell(null)
          }}
          onPressEnter={e => e.currentTarget.blur()}
        />
      ) : (
        <div
          onClick={() => !savingCell && setEditingCell(cellKey)}
          style={{ cursor: 'pointer', padding: '4px 8px', minHeight: '24px' }}
        >
          {value || <span style={{ color: '#cbd5e1' }}>-</span>}
        </div>
      )
    )
  }

  const editableNumber = (field: keyof PlanRow, min = 0) => (value: number | null, row: PlanRow) => {
    if (!canUpdate) {
      return <div style={{ padding: '4px 8px', textAlign: 'right' }}>{value != null ? value : <span style={{ color: '#cbd5e1' }}>-</span>}</div>
    }
    const cellKey = `${row.id}-${String(field)}`
    const isEditing = editingCell === cellKey
    return (
      isEditing ? (
        <InputNumber
          size="small"
          min={min}
          defaultValue={value ?? undefined}
          disabled={savingCell === cellKey}
          style={{ width: '100%' }}
          autoFocus
          onBlur={e => {
            const raw = e.target.value
            const next = raw === '' ? null : Number(raw)
            if ((value ?? null) !== next && (next == null || !Number.isNaN(next))) handleCellSave(row, field, next)
            setEditingCell(null)
          }}
          onPressEnter={e => e.currentTarget.blur()}
        />
      ) : (
        <div
          onClick={() => !savingCell && setEditingCell(cellKey)}
          style={{ cursor: 'pointer', padding: '4px 8px', textAlign: 'right' }}
        >
          {value != null ? value : <span style={{ color: '#cbd5e1' }}>-</span>}
        </div>
      )
    )
  }

  const editableDate = (field: keyof PlanRow) => (value: string | null, row: PlanRow) => {
    if (!canUpdate) {
      return <div style={{ padding: '4px 8px' }}>{value ? dayjs(value).format('YYYY-MM-DD') : <span style={{ color: '#cbd5e1' }}>-</span>}</div>
    }
    const cellKey = `${row.id}-${String(field)}`
    const isEditing = editingCell === cellKey
    return (
      isEditing ? (
        <DatePicker
          size="small"
          value={value ? dayjs(value) : null}
          disabled={savingCell === cellKey}
          style={{ width: '100%' }}
          autoFocus
          onChange={(d) => {
            handleCellSave(row, field, d ? d.format('YYYY-MM-DD') : null)
            setEditingCell(null)
          }}
          onOpenChange={(open) => {
            if (!open) setEditingCell(null)
          }}
        />
      ) : (
        <div
          onClick={() => !savingCell && setEditingCell(cellKey)}
          style={{ cursor: 'pointer', padding: '4px 8px' }}
        >
          {value ? dayjs(value).format('YYYY-MM-DD') : <span style={{ color: '#cbd5e1' }}>-</span>}
        </div>
      )
    )
  }

  const handleAdd = async (values: any) => {
    try {
      const payload = {
        po_no: `CSV-MANUAL-${Date.now()}`,
        material_code: values.material_code,
        supplier_name: values.supplier_name,
        supplier_account: values.supplier_account || null,
        material_name: values.material_name,
        spec_model: values.spec_model,
        unit: values.unit,
        po_qty: values.po_qty,
        received_qty: values.received_qty,
        eta: values.eta ? dayjs(values.eta).format('YYYY-MM-DD') : null,
        order_no: values.order_no,
        owner: values.owner || null,
        owner_id: values.owner_id || null,
        po_status: 'pending',
        data_source: 'csv_plan',
      }
      await materialApi.createPurchasePlan(payload)
      message.success('新增成功')
      setAddModal(false)
      form.resetFields()
      load()
      loadStats()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const handleImport = async (file: File) => {
    try {
      const res: any = await materialApi.importPurchasePlan(file)
      message.success(`导入完成：新增 ${res.data.created}，更新 ${res.data.updated}，跳过 ${res.data.skipped}`)
      load()
      loadStats()
    } catch (e: any) {
      message.error(`导入失败：${e.message}`)
    }
    return false
  }

  const handleBatchEdit = async (values: any) => {
    try {
      const payload: {
        ids: number[]
        eta?: string
        owner?: string
        owner_id?: number
        supplier_account?: string
        actual_arrival_date?: string
        inspection_date?: string
        is_closed?: boolean
        clear_fields?: string[]
      } = { ids: selectedRowKeys }
      if (values.eta) payload.eta = dayjs(values.eta).format('YYYY-MM-DD')
      if (values.owner !== undefined && values.owner !== '') payload.owner = values.owner
      if (values.owner_id !== undefined && values.owner_id !== null) {
        payload.owner_id = values.owner_id
        const opt = batchUserOptions.find(u => u.value === values.owner_id)
        if (opt && !values.owner) payload.owner = opt.display_name
      }
      if (values.supplier_account !== undefined && values.supplier_account !== '') payload.supplier_account = values.supplier_account
      if (values.actual_arrival_date) payload.actual_arrival_date = dayjs(values.actual_arrival_date).format('YYYY-MM-DD')
      if (values.inspection_date) payload.inspection_date = dayjs(values.inspection_date).format('YYYY-MM-DD')
      if (values.is_closed !== undefined && values.is_closed !== null) payload.is_closed = values.is_closed
      payload.clear_fields = values.clear_fields || []
      if (
        !payload.eta
        && !payload.owner
        && !payload.owner_id
        && !payload.supplier_account
        && !payload.actual_arrival_date
        && !payload.inspection_date
        && payload.is_closed === undefined
        && (!payload.clear_fields || payload.clear_fields.length === 0)
      ) {
        message.warning('请至少填写一个更新字段或选择清空字段')
        return
      }
      await materialApi.batchUpdatePurchasePlan(payload)
      message.success(`批量更新成功，共更新 ${selectedRowKeys.length} 条记录`)
      setBatchEditModal(false)
      batchForm.resetFields()
      setSelectedRowKeys([])
      load()
      loadStats()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const openContact = (row: PlanRow) => {
    setChatRecord(row)
    setChatModalOpen(true)
  }

  const getTextFilterProps = (dataIndex: string) => ({
    filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
      <div style={{ padding: 8 }}>
        <Input
          placeholder="输入筛选内容"
          value={selectedKeys[0]}
          onChange={e => setSelectedKeys(e.target.value ? [e.target.value] : [])}
          onPressEnter={() => { confirm(); setPage(1) }}
          style={{ marginBottom: 8, display: 'block', width: 188 }}
        />
        <Space>
          <Button type="primary" onClick={() => { confirm(); setPage(1) }} icon={<SearchOutlined />} size="small" style={{ width: 90 }}>搜索</Button>
          <Button onClick={() => { clearFilters?.(); confirm(); setPage(1) }} size="small" style={{ width: 90 }}>重置</Button>
        </Space>
      </div>
    ),
    filterIcon: (filtered: boolean) => <SearchOutlined style={{ color: filtered ? '#1677ff' : undefined }} />,
    filteredValue: (filters as any)[dataIndex] ? [(filters as any)[dataIndex]] : null,
  })

  const getDateFilterProps = (dataIndex: string) => ({
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
          style={{ marginBottom: 8 }}
        />
        <div>
          <Space>
            <Button type="primary" onClick={() => { confirm(); setPage(1) }} size="small" style={{ width: 90 }}>确定</Button>
            <Button onClick={() => { clearFilters?.(); confirm(); setPage(1) }} size="small" style={{ width: 90 }}>重置</Button>
          </Space>
        </div>
      </div>
    ),
    filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1677ff' : undefined }} />,
    filteredValue: (filters as any)[dataIndex] || null,
  })

  const getNumberFilterProps = (dataIndex: string) => ({
    filterDropdown: ({ setSelectedKeys, selectedKeys, confirm, clearFilters }: any) => (
      <div style={{ padding: 8 }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
          <InputNumber
            placeholder="最小值"
            value={selectedKeys?.[0]}
            onChange={v => setSelectedKeys(v != null ? [v, selectedKeys?.[1]] : [undefined, selectedKeys?.[1]])}
            style={{ width: 90 }}
          />
          <span style={{ lineHeight: '32px' }}>-</span>
          <InputNumber
            placeholder="最大值"
            value={selectedKeys?.[1]}
            onChange={v => setSelectedKeys([selectedKeys?.[0], v != null ? v : undefined])}
            style={{ width: 90 }}
          />
        </div>
        <Space>
          <Button type="primary" onClick={() => { confirm(); setPage(1) }} size="small" style={{ width: 90 }}>确定</Button>
          <Button onClick={() => { clearFilters?.(); confirm(); setPage(1) }} size="small" style={{ width: 90 }}>重置</Button>
        </Space>
      </div>
    ),
    filterIcon: (filtered: boolean) => <FilterOutlined style={{ color: filtered ? '#1677ff' : undefined }} />,
    filteredValue: (filters as any)[dataIndex] || null,
  })

  const getSelectFilterProps = (dataIndex: string, options: { value: number; label: string }[]) => ({
    filters: options.map(option => ({ text: option.label, value: option.value })),
    filteredValue: (filters as any)[dataIndex] !== undefined ? [(filters as any)[dataIndex]] : null,
  })

  const columns = [
    {
      title: '供应商', dataIndex: 'supplier_name', maxWidth: 100, ellipsis: true, fixed: 'left' as const, sorter: true,
      ...getTextFilterProps('supplier_name'),
      onCell: () => ({ style: { maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }),
      render: editableText('supplier_name'),
    },
    {
      title: '供应商账号', dataIndex: 'supplier_account', width: 120, sorter: true,
      ...getTextFilterProps('supplier_account'),
      render: editableText('supplier_account'),
    },
    {
      title: '采购单号', dataIndex: 'po_no', width: 120, sorter: true,
      ...getTextFilterProps('po_no'),
      onCell: () => ({ style: { maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }),
      render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    {
      title: '物料长代码', dataIndex: 'material_code', maxWidth: 100, ellipsis: true, fixed: 'left' as const, sorter: true,
      ...getTextFilterProps('material_code'),
      onCell: () => ({ style: { maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }),
      render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    {
      title: '物料名称', dataIndex: 'material_name', maxWidth: 100, ellipsis: true, fixed: 'left' as const, sorter: true,
      ...getTextFilterProps('material_name'),
      onCell: () => ({ style: { maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }),
      render: editableText('material_name'),
    },
    {
      title: '物料属性', dataIndex: 'material_property', width: 90, sorter: true,
      ...getSelectFilterProps('material_property', MATERIAL_PROPERTY_OPTIONS),
      render: (v: number | null) => v ? (MATERIAL_PROPERTY_MAP[v] || v) : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    { title: '规格型号', dataIndex: 'spec_model', maxWidth: 150, ellipsis: true, sorter: true,
      ...getTextFilterProps('spec_model'),
      onCell: () => ({ style: { maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }),
      render: editableText('spec_model'),
    },
    { title: '单位', dataIndex: 'unit', width: 60,
      ...getTextFilterProps('unit'),
      render: editableText('unit'),
    },
    {
      title: '下单日期', dataIndex: 'po_date', width: 120, sorter: true,
      ...getDateFilterProps('po_date'),
      render: (v: string | null) => v ? formatDate(v) : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '数量', dataIndex: 'po_qty', width: 80,
      ...getNumberFilterProps('po_qty'),
      render: editableNumber('po_qty'),
      sorter: true,
    },
    {
      title: <Tooltip title="实际入库数量">收料数量</Tooltip>, dataIndex: 'received_qty', width: 90,
      ...getNumberFilterProps('received_qty'),
      render: editableNumber('received_qty'),
      sorter: true,
    },
    {
      title: <Tooltip title="计划数量 - 收料数量，正数表示缺料">缺料</Tooltip>, dataIndex: 'shortage_qty', width: 80,
      filters: [{ text: '仅看缺料', value: 'shortage' }],
      filteredValue: filters.only_shortage ? ['shortage'] as (string | number | boolean)[] : null,
      render: (v: number | null, row: PlanRow) => {
        if (v == null || v <= 0) return <span style={{ color: '#cbd5e1' }}>-</span>
        return <Tooltip title={`计划${row.po_qty} - 收料${row.received_qty ?? 0} = 缺${v}`}>
          <span style={{ color: '#e11d48', fontWeight: 500 }}>-{v}</span>
        </Tooltip>
      },
    },
    {
      title: <Tooltip title="同步或导入带入的原始交货日期">同步交期</Tooltip>, dataIndex: 'original_eta', width: 120,
      render: (v: string | null) => v ? formatDate(v) : <span style={{ color: '#cbd5e1' }}>-</span>,
      sorter: true,
    },
    {
      title: <Tooltip title="供应商承诺交货日期">交货日期</Tooltip>, dataIndex: 'eta', width: 120,
      ...getDateFilterProps('eta'),
      render: editableDate('eta'),
      sorter: true,
    },
    {
      title: <Tooltip title="关联生产订单号">订单号</Tooltip>, dataIndex: 'order_no', width: 80,
      ...getTextFilterProps('order_no'),
      render: editableText('order_no'),
      sorter: true,
    },
    {
      title: <Tooltip title="实际入库日期">到料时间</Tooltip>, dataIndex: 'actual_arrival_date', width: 120,
      ...getDateFilterProps('actual_arrival_date'),
      render: editableDate('actual_arrival_date'),
      sorter: true,
    },
    {
      title: '小时节点', dataIndex: 'arrival_hour_note', ellipsis: true,
      ...getTextFilterProps('arrival_hour_note'),
      render: editableText('arrival_hour_note'),
    },
    {
      title: '责任人', dataIndex: 'owner', width: 80, fixed: 'right' as const, sorter: true,
      ...getTextFilterProps('owner'),
      render: (v: string | null) => (
        <div style={{ padding: '4px 8px', minHeight: '24px' }}>
          {v || <span style={{ color: '#cbd5e1' }}>-</span>}
        </div>
      ),
    },
    {
      title: <Tooltip title="检验单日期">检验日期</Tooltip>, dataIndex: 'inspection_date', width: 120,
      ...getDateFilterProps('inspection_date'),
      render: editableDate('inspection_date'),
      sorter: true,
    },
    {
      title: '关闭', dataIndex: 'is_closed', width: 70, fixed: 'right' as const, sorter: true,
      filters: [{ text: '已关闭', value: 'closed' }, { text: '未关闭', value: 'open' }],
      filteredValue: (filters as any).is_closed || null,
      render: (v: number) => {
        if (v === 1) return <Tag color="error">已关闭</Tag>
        return <span style={{ color: '#cbd5e1' }}>-</span>
      },
    },
    {
      title: <Tooltip title="呆滞物料：收料数量超过下单数量">呆滞</Tooltip>, dataIndex: 'is_stagnant', width: 80, fixed: 'right' as const, sorter: true,
      filters: [{ text: '呆滞物料', value: 'stagnant' }],
      filteredValue: filters.po_status.includes('stagnant') ? ['stagnant'] as (string | number | boolean)[] : null,
      render: (v: boolean, row: PlanRow) => {
        if (!v) return <span style={{ color: '#cbd5e1' }}>-</span>
        return <Tooltip title={`超量 ${row.stagnant_qty}，收料${row.received_qty} > 下单${row.po_qty}`}><Tag color="warning">呆滞 +{row.stagnant_qty}</Tag></Tooltip>
      },
    },
    {
      title: <Tooltip title="待到料 / 部分到 / 已到齐 / 逾期未到，依据收料数量自动计算">状态</Tooltip>, dataIndex: 'po_status', width: 90, fixed: 'right' as const, sorter: true,
      filters: Object.entries(STATUS_MAP).filter(([key]) => key !== 'stagnant').map(([key, val]) => ({ text: val.label, value: key })),
      filteredValue: filters.po_status.filter(s => s !== 'stagnant' && s !== 'closed').length ? filters.po_status.filter(s => s !== 'stagnant' && s !== 'closed') as (string | number | boolean)[] : null,
      render: (v: string, row: PlanRow) => {
        const s = STATUS_MAP[v] || { label: v, color: 'default' }
        return <Tag color={s.color}>{s.label}</Tag>
      },
    },
    {
      title: '操作', width: 88, fixed: 'right' as const,
      render: (_: any, row: PlanRow) => (
        <Space size={4}>
          <Tooltip title="和供应商沟通">
            <Button size="small" icon={<MessageOutlined />} onClick={() => openContact(row)} />
          </Tooltip>
          {canUpdate && (
            <Tooltip title="编辑">
              <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
            </Tooltip>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div>
      {/* 统计卡 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '计划总数', value: stats.total, icon: <ShoppingOutlined />, color: '#6366f1' },
          { title: '待到料', value: stats.pending, icon: <ClockCircleOutlined />, color: '#f59e0b' },
          { title: '部分到', value: stats.partial_received, icon: <WarningOutlined />, color: '#f59e0b' },
          { title: '已到齐', value: stats.fully_received, icon: <CheckCircleOutlined />, color: '#16a34a' },
          { title: '逾期未到', value: stats.overdue, icon: <WarningOutlined />, color: '#e11d48' },
          { title: '呆滞物料', value: stats.stagnant, icon: <StopOutlined />, color: '#d97706' },
          { title: '已关闭', value: stats.closed, icon: <CheckCircleOutlined />, color: '#94a3b8' },
        ].map((card, i) => (
          <Col flex={1} key={i}>
            <Card
              size="small"
              className="card-modern"
              style={{ padding: 0 }}
            >
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

      {showCharts && (
        <AnalysisCharts
          loading={analysisLoading}
          statusDistribution={analysisData.status_distribution}
          supplierOverdueTop5={analysisData.supplier_overdue_top5}
          materialShortageTop5={analysisData.material_shortage_top5}
        />
      )}

      <div className="card-modern" style={{ padding: '14px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索物料/供应商/订单号/采购单号"
              value={filters.keyword}
              onChange={e => { setFilters(f => ({ ...f, keyword: e.target.value })); setPage(1) }}
              style={{ width: 240 }}
              allowClear
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button
                icon={<BarChartOutlined />}
                type={showCharts ? 'primary' : 'default'}
                onClick={toggleCharts}
              >
                {showCharts ? '隐藏图表' : '分析图表'}
              </Button>
              {canUpdate && selectedRowKeys.length > 0 && (
                <Button type="primary" icon={<EditOutlined />} onClick={() => setBatchEditModal(true)}>
                  批量编辑 ({selectedRowKeys.length})
                </Button>
              )}
              <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
              <Dropdown
                menu={{
                  items: [
                    { key: 'xlsx', label: '导出 Excel', icon: <DownloadOutlined /> },
                    { key: 'csv', label: '导出 CSV', icon: <DownloadOutlined /> },
                  ],
                  onClick: ({ key }) => handleExport(key as 'xlsx' | 'csv'),
                }}
              >
                <Button icon={<DownloadOutlined />} loading={exporting}>导出 <DownOutlined /></Button>
              </Dropdown>
              {canImport && (
                <Upload beforeUpload={(f) => { handleImport(f); return false }} showUploadList={false} accept=".csv">
                  <Button icon={<UploadOutlined />}>导入CSV</Button>
                </Upload>
              )}
              {canCreate && <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddModal(true)}>新增</Button>}
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '2px 0 0' }}>
        <div className="table-modern">
          <Table
          rowKey="id"
          dataSource={data}
          columns={columns}
          loading={loading}
          rowSelection={canUpdate ? {
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys as number[]),
          } : undefined}
          scroll={{ x: 'max-content', y: 'calc(100vh - 380px)' }}
          size="small"
          tableLayout="fixed"
          pagination={{
            total, current: page, pageSize,
            showSizeChanger: true, showTotal: t => `共 ${t} 条`,
            pageSizeOptions: ['20', '50', '100'],
            style: { padding: '0 16px' },
          }}
          onChange={(pagination, tableFilters, sorter: any) => {
            setPage(pagination.current || 1)
            setPageSize(pagination.pageSize || 20)
            // 状态筛选（合并 po_status 和 is_stagnant）
            const statusFilter = (tableFilters?.po_status as string[] | undefined) || []
            const stagnantFilter = (tableFilters?.is_stagnant as string[] | undefined) || []
            // 文本列筛选
            const textKeys = ['supplier_name', 'supplier_account', 'material_code', 'material_name', 'spec_model', 'unit', 'owner', 'order_no', 'arrival_hour_note', 'po_no'] as const
            const textUpdates: Record<string, string> = {}
            textKeys.forEach(k => { textUpdates[k] = (tableFilters?.[k]?.[0] as string) || '' })
            const materialProperty = tableFilters?.material_property?.[0] as number | undefined
            // 日期范围列筛选
            const dateKeys = ['po_date', 'eta', 'actual_arrival_date', 'inspection_date'] as const
            const dateUpdates: Record<string, [string, string] | null> = {}
            dateKeys.forEach(k => {
              const v = tableFilters?.[k] as string[] | null
              dateUpdates[k] = v && v.length === 2 ? [v[0], v[1]] : null
            })
            // 数值范围列筛选
            const numKeys = ['po_qty', 'received_qty'] as const
            const numUpdates: Record<string, [number, number] | null> = {}
            numKeys.forEach(k => {
              const v = tableFilters?.[k] as (number | undefined)[] | null
              numUpdates[k] = v && (v[0] != null || v[1] != null) ? [v[0] as number, v[1] as number] : null
            })
            setFilters(prev => ({
              ...prev,
              ...textUpdates,
              material_property: materialProperty,
              ...dateUpdates,
              ...numUpdates,
              po_status: [...statusFilter, ...stagnantFilter],
              only_shortage: ((tableFilters?.shortage_qty as string[] | undefined) || []).includes('shortage'),
              is_closed: (tableFilters?.is_closed as string[] | undefined) || [],
            } as typeof prev))
            // 排序
            const sortField = sorter.field as string | undefined
            const sortDir = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : ''
            setSortBy(sortField || '')
            setSortOrder(sortDir)
          }}
        />
        </div>
      </div>

      <SupplierChatModal
        open={chatModalOpen}
        record={chatRecord}
        onClose={() => setChatModalOpen(false)}
      />

      <Modal
        title="新增采购到料计划"
        open={addModal}
        onCancel={() => { setAddModal(false); form.resetFields() }}
        onOk={() => form.submit()}
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleAdd}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="owner_id" label="责任人" shouldUpdate>
                {({ getFieldValue, setFieldValue }) => (
                  <Select
                    showSearch
                    allowClear
                    placeholder="搜索选择责任人"
                    loading={userSearching}
                    filterOption={false}
                    onSearch={(val) => searchUsers(val, 'add')}
                    onChange={(val: number | undefined) => {
                      setFieldValue('owner_id', val || null)
                      if (val) {
                        const opt = addUserOptions.find(u => u.value === val)
                        if (opt) setFieldValue('owner', opt.display_name)
                      } else {
                        setFieldValue('owner', null)
                      }
                    }}
                    value={getFieldValue('owner_id')}
                    onFocus={() => {
                      if (addUserOptions.length === 0) searchUsers('', 'add')
                    }}
                  >
                    {addUserOptions.map(u => (
                      <Select.Option key={u.value} value={u.value}>{u.label}</Select.Option>
                    ))}
                  </Select>
                )}
              </Form.Item>
            </Col>
            <Form.Item name="owner" hidden>
              <Input />
            </Form.Item>
            <Col span={12}>
              <Form.Item name="supplier_account" label="供应商账号">
                <Input placeholder="用于供应商登录/同步" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="owner_id" label="责任人" shouldUpdate>
                {({ getFieldValue, setFieldValue }) => (
                  <Select
                    showSearch
                    allowClear
                    placeholder="搜索选择责任人"
                    loading={userSearching}
                    filterOption={false}
                    onSearch={(val) => searchUsers(val, 'edit')}
                    onChange={(val: number | undefined) => {
                      setFieldValue('owner_id', val || null)
                      if (val) {
                        const opt = userOptions.find(u => u.value === val)
                        if (opt) setFieldValue('owner', opt.display_name)
                      } else {
                        setFieldValue('owner', null)
                      }
                    }}
                    value={getFieldValue('owner_id')}
                    onFocus={() => {
                      if (userOptions.length === 0) searchUsers('', 'edit')
                    }}
                  >
                    {userOptions.map(u => (
                      <Select.Option key={u.value} value={u.value}>{u.label}</Select.Option>
                    ))}
                  </Select>
                )}
              </Form.Item>
            </Col>
            <Form.Item name="owner" hidden>
              <Input />
            </Form.Item>
            <Col span={12}>
              <Form.Item name="material_name" label="物料名称">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="material_property" label="物料属性">
                <Select allowClear options={MATERIAL_PROPERTY_OPTIONS} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="spec_model" label="规格型号">
                <Input />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="unit" label="单位">
                <Input />
              </Form.Item>
            </Col>
            <Col span={9}>
              <Form.Item name="po_qty" label="数量">
                <Input type="number" />
              </Form.Item>
            </Col>
            <Col span={9}>
              <Form.Item name="received_qty" label="收料数量">
                <Input type="number" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="eta" label="交货日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="order_no" label="订单号">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="owner" label="责任人">
                <Input />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        title="编辑采购到料计划"
        open={editModal}
        onCancel={() => { setEditModal(false); form.resetFields() }}
        onOk={() => form.submit()}
        width={600}
        style={{ top: 32 }}
      >
        <Form form={form} layout="vertical" size="small" onFinish={handleEditSubmit}>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="supplier_name" label="供应商">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="supplier_account" label="供应商账号">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="material_code" label="物料长代码">
                <Input disabled />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="material_name" label="物料名称">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="material_property" label="物料属性">
                <Select allowClear options={MATERIAL_PROPERTY_OPTIONS} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="spec_model" label="规格型号">
                <Input />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="unit" label="单位">
                <Input />
              </Form.Item>
            </Col>
            <Col span={9}>
              <Form.Item name="po_qty" label="数量">
                <Input type="number" />
              </Form.Item>
            </Col>
            <Col span={9}>
              <Form.Item name="received_qty" label="收料数量">
                <Input type="number" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="eta" label="交货日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="order_no" label="订单号">
                <Select
                  showSearch
                  placeholder="选择或搜索订单"
                  optionFilterProp="children"
                  loading={orderLoading}
                  onSearch={(value) => loadOrders(value)}
                  filterOption={false}
                  allowClear
                >
                  {orderList.map((order: any) => (
                    <Select.Option key={order.order_no} value={order.order_no}>
                      {order.order_no}
                    </Select.Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="actual_arrival_date" label="到料时间">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="inspection_date" label="检验日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="arrival_hour_note" label="小时节点">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="owner" label="责任人">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="is_closed" label="关闭订单" valuePropName="checked" getValueFromEvent={(checked: boolean) => checked ? 1 : 0} getValueProps={(value: number) => ({ checked: value === 1 })}>
                <Switch checkedChildren="已关闭" unCheckedChildren="开启" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        title={`批量编辑（已选 ${selectedRowKeys.length} 条）`}
        open={batchEditModal}
        onCancel={() => { setBatchEditModal(false); batchForm.resetFields() }}
        onOk={() => batchForm.submit()}
        width={400}
      >
        <Form form={batchForm} layout="vertical" onFinish={handleBatchEdit}>
          <p style={{ color: '#64748b', marginBottom: 16 }}>已选择 {selectedRowKeys.length} 条。仅填写需要修改的字段，留空则不修改。</p>
          <Form.Item name="eta" label="交货时间">
            <DatePicker style={{ width: '100%' }} placeholder="选择交货日期" />
          </Form.Item>
          <Form.Item name="owner_id" label="责任人" shouldUpdate>
            {({ getFieldValue, setFieldValue }) => (
              <Select
                showSearch
                allowClear
                placeholder="搜索选择责任人"
                loading={userSearching}
                filterOption={false}
                onSearch={(val) => searchUsers(val, 'batch')}
                onChange={(val: number | undefined) => {
                  setFieldValue('owner_id', val || null)
                  if (val) {
                    const opt = batchUserOptions.find(u => u.value === val)
                    if (opt) setFieldValue('owner', opt.display_name)
                  } else {
                    setFieldValue('owner', null)
                  }
                }}
                value={getFieldValue('owner_id')}
                onFocus={() => {
                  if (batchUserOptions.length === 0) searchUsers('', 'batch')
                }}
              >
                {batchUserOptions.map(u => (
                  <Select.Option key={u.value} value={u.value}>{u.label}</Select.Option>
                ))}
              </Select>
            )}
          </Form.Item>
          <Form.Item name="owner" hidden>
            <Input />
          </Form.Item>
          <Form.Item name="supplier_account" label="供应商账号">
            <Input placeholder="输入供应商账号" />
          </Form.Item>
          <Form.Item name="actual_arrival_date" label="到料时间">
            <DatePicker style={{ width: '100%' }} placeholder="选择到料日期" />
          </Form.Item>
          <Form.Item name="inspection_date" label="检验日期">
            <DatePicker style={{ width: '100%' }} placeholder="选择检验日期" />
          </Form.Item>
          <Form.Item name="is_closed" label="关闭订单" valuePropName="checked" getValueFromEvent={(checked: boolean) => checked ? 1 : 0} getValueProps={(value: number) => ({ checked: value === 1 })}>
            <Switch checkedChildren="已关闭" unCheckedChildren="开启" />
          </Form.Item>
          <Form.Item name="clear_fields" label="清空字段">
            <Select
              mode="multiple"
              allowClear
              placeholder="选择要清空的字段"
              options={[
                { label: '交货时间', value: 'eta' },
                { label: '责任人', value: 'owner' },
                { label: '供应商账号', value: 'supplier_account' },
                { label: '到料时间', value: 'actual_arrival_date' },
                { label: '检验日期', value: 'inspection_date' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
