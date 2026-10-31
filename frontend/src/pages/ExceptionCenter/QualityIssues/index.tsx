import { useEffect, useState, useCallback } from 'react'
import {
  Table, Tag, Input, Select, Button, Space, message, Modal, Form,
  DatePicker, InputNumber, Row, Col, Popconfirm, Dropdown, Popover, Checkbox,
} from 'antd'
import {
  ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined,
  DownloadOutlined, DownOutlined, SettingOutlined, HolderOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { exceptionApi } from '../../../services/api'
import { formatDate } from '../../../utils'
import { useExport } from '../../../hooks/useExport'
import { useUiPreferencesStore } from '../../../store/uiPreferences'
import AnalysisReportDrawer, { QualityAnalysisReportOut } from './components/AnalysisReportDrawer'

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  open: { label: '待处理', color: 'error' },
  in_progress: { label: '处理中', color: 'processing' },
  closed: { label: '已关闭', color: 'success' },
}

const WORKFLOW_STATUS_MAP: Record<string, { label: string; color: string }> = {
  '创建': { label: '创建', color: 'default' },
  '提交': { label: '提交', color: 'processing' },
  '批准': { label: '批准', color: 'success' },
  '归档': { label: '归档', color: 'default' },
}

const WORKFLOW_STATUS_OPTIONS = ['创建', '提交', '批准', '归档']

const DEPT_OPTIONS = ['计划', '采购', '品质', '仓库', '生产', '销售', '工程', '研发']

const QUALITY_PAGE_KEY = 'exception_quality_columns'

const CONFIGURABLE_COLUMNS: { key: string; title: string }[] = [
  { key: 'issue_no', title: '编号' },
  { key: 'order_no', title: '订单编号' },
  { key: 'product_code', title: '产品代码' },
  { key: 'submit_dept', title: '提出部门' },
  { key: 'submit_date', title: '提出日期' },
  { key: 'submitter', title: '提出人' },
  { key: 'product_name', title: '产品名称' },
  { key: 'process', title: '工序' },
  { key: 'defect_type', title: '缺陷类型' },
  { key: 'description', title: '异常描述' },
  { key: 'root_cause', title: '真实原因' },
  { key: 'responsible_person', title: '责任人' },
  { key: 'responsible_dept', title: '责任部门' },
  { key: 'batch_qty', title: '批量数' },
  { key: 'sample_qty', title: '抽样数量' },
  { key: 'defect_qty', title: '不良数' },
  { key: 'improvement_countermeasures', title: '改善对策' },
  { key: 'improvement_countermeasures_date', title: '改善对策日期' },
  { key: 'temporary_countermeasure', title: '临时对策' },
  { key: 'temporary_countermeasure_date', title: '临时对策时间' },
  { key: 'preliminary_analysis_person', title: '初步分析负责人' },
  { key: 'quality_manager_approval', title: '品质经理审批' },
  { key: 'defect_rate', title: '不良率' },
]

const DEFAULT_COLUMN_ORDER = CONFIGURABLE_COLUMNS.map(c => c.key)

const FIXED_RIGHT_KEYS = ['workflow_status', 'status', '__action__']

const ColumnSettingsPanel: React.FC<{
  order: string[]
  visibleKeys: string[]
  onToggle: (key: string) => void
  onReorder: (from: number, to: number) => void
  onReset: () => void
}> = ({ order, visibleKeys, onToggle, onReorder, onReset }) => {
  const [dragIndex, setDragIndex] = useState<number | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)

  return (
    <div style={{ width: 260, maxHeight: 420, overflowY: 'auto', padding: 4 }}>
      <div style={{ marginBottom: 8, fontWeight: 600, fontSize: 13 }}>
        列设置
        <span style={{ fontWeight: 400, color: '#999', fontSize: 12 }}>（拖动 ⠿ 调序）</span>
      </div>
      {order.map((key, idx) => {
        const meta = CONFIGURABLE_COLUMNS.find(m => m.key === key)
        if (!meta) return null
        const visible = visibleKeys.includes(key)
        const isDragging = dragIndex === idx
        const isOverTarget = overIndex === idx && dragIndex !== null && dragIndex !== idx
        return (
          <div
            key={key}
            onDragOver={e => {
              e.preventDefault()
              e.dataTransfer.dropEffect = 'move'
              if (overIndex !== idx) setOverIndex(idx)
            }}
            onDrop={e => {
              e.preventDefault()
              if (dragIndex !== null && dragIndex !== idx) onReorder(dragIndex, idx)
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
              border: isOverTarget ? '1px dashed #1890ff' : '1px solid transparent',
              background: isDragging ? '#f5f5f5' : isOverTarget ? '#e6f7ff' : 'transparent',
              opacity: isDragging ? 0.4 : 1,
              transition: 'border-color 0.1s, background 0.1s',
            }}
          >
            <span
              draggable
              onDragStart={e => {
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
        <Button size="small" onClick={onReset}>重置默认</Button>
      </div>
    </div>
  )
}

export default function QualityIssues() {
  const [data, setData] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [modalOpen, setModalOpen] = useState(false)
  const [editRecord, setEditRecord] = useState<any>(null)
  const [keyword, setKeyword] = useState('')
  const [tableFilters, setTableFilters] = useState<Record<string, any[] | null>>({})
  const [sorterState, setSorterState] = useState<{ field?: string; order?: string }>({})
  const [form] = Form.useForm()
  const { exporting, exportData } = useExport()
  const [showAnalysis, setShowAnalysis] = useState(false)
  const [statistics, setStatistics] = useState<any>(null)
  const [analysisLoading, setAnalysisLoading] = useState(false)
  const [analysisReport, setAnalysisReport] = useState<QualityAnalysisReportOut | null>(null)
  const [analysisDrawerOpen, setAnalysisDrawerOpen] = useState(false)
  const [analysisError, setAnalysisError] = useState<string | null>(null)
  const getColumnVisibility = useUiPreferencesStore(s => s.getColumnVisibility)
  const setColumnVisibility = useUiPreferencesStore(s => s.setColumnVisibility)
  const getColumnOrder = useUiPreferencesStore(s => s.getColumnOrder)
  const setColumnOrder = useUiPreferencesStore(s => s.setColumnOrder)
  const [visibleColumnKeys, setVisibleColumnKeys] = useState<string[]>(
    () => getColumnVisibility(QUALITY_PAGE_KEY, DEFAULT_COLUMN_ORDER)
  )
  const [columnOrder, setColumnOrderState] = useState<string[]>(
    () => getColumnOrder(QUALITY_PAGE_KEY, DEFAULT_COLUMN_ORDER)
  )

  const handleToggleColumn = (key: string) => {
    const prev = visibleColumnKeys
    const next = prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    if (next.length === 0) return
    setVisibleColumnKeys(next)
    setColumnVisibility(QUALITY_PAGE_KEY, next)
  }

  const handleReorderColumn = (from: number, to: number) => {
    const next = [...columnOrder]
    const [moved] = next.splice(from, 1)
    next.splice(to, 0, moved)
    setColumnOrderState(next)
    setColumnOrder(QUALITY_PAGE_KEY, next)
  }

  const handleResetColumns = () => {
    setVisibleColumnKeys(DEFAULT_COLUMN_ORDER)
    setColumnOrderState(DEFAULT_COLUMN_ORDER)
    setColumnVisibility(QUALITY_PAGE_KEY, DEFAULT_COLUMN_ORDER)
    setColumnOrder(QUALITY_PAGE_KEY, DEFAULT_COLUMN_ORDER)
  }

  const handleExport = (format: 'xlsx' | 'csv') => {
    const params: Record<string, any> = { format }
    if (keyword.trim()) params.keyword = keyword.trim()
    Object.entries(tableFilters).forEach(([field, values]) => {
      if (values && values.length) params[field] = values
    })
    if (sorterState.field && sorterState.order) {
      params.sort_field = sorterState.field
      params.sort_order = sorterState.order
    }
    const ext = format === 'csv' ? 'csv' : 'xlsx'
    const qs = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        value.forEach(v => qs.append(key, v))
      } else {
        qs.append(key, String(value))
      }
    })
    exportData(`/api/v1/exceptions/quality/export?${qs.toString()}`, {}, `品质异常.${ext}`)
  }

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = { page, page_size: pageSize }
      if (keyword.trim()) params.keyword = keyword.trim()
      Object.entries(tableFilters).forEach(([field, values]) => {
        if (values && values.length) params[field] = values
      })
      if (sorterState.field && sorterState.order) {
        params.sort_field = sorterState.field
        params.sort_order = sorterState.order
      }
      const res: any = await exceptionApi.listQuality(params)
      setData(res.data.items)
      setTotal(res.data.total)
      
    } catch (e: any) {
      // 错误已由全局拦截器提示
    } finally {
        setLoading(false)
    }
  }, [page, pageSize, keyword, tableFilters, sorterState])

  useEffect(() => { load() }, [load])

  const loadStatistics = useCallback(async () => {
    try {
      const params: any = {}
      if (keyword.trim()) params.keyword = keyword.trim()
      Object.entries(tableFilters).forEach(([field, values]) => {
        if (values && values.length) params[field] = values
      })
      const res: any = await exceptionApi.getQualityStatistics(params)
      setStatistics(res.data)
    } catch (e: any) {
      // 错误已由全局拦截器提示
    }
  }, [keyword, tableFilters])

  useEffect(() => { loadStatistics() }, [loadStatistics])

  const handleAnalyze = useCallback(async () => {
    const params: any = {}
    if (keyword.trim()) params.keyword = keyword.trim()
    Object.entries(tableFilters).forEach(([field, values]) => {
      if (values && values.length) params[field] = values
    })
    setAnalysisLoading(true)
    setAnalysisError(null)
    setAnalysisDrawerOpen(true)
    try {
      const res: any = await exceptionApi.analyzeQuality(params)
      setAnalysisReport(res.data)
    } catch (e: any) {
      setAnalysisError(e?.message || '分析失败，请稍后重试')
    } finally {
      setAnalysisLoading(false)
    }
  }, [keyword, tableFilters])

  const openCreate = () => {
    setEditRecord(null)
    form.resetFields()
    setModalOpen(true)
  }

  const openEdit = (row: any) => {
    setEditRecord(row)
    form.setFieldsValue({
      status: row.status,
      workflow_status: row.workflow_status,
      improvement_countermeasures: row.improvement_countermeasures,
      improvement_countermeasures_date: row.improvement_countermeasures_date ? dayjs(row.improvement_countermeasures_date) : null,
      temporary_countermeasure: row.temporary_countermeasure,
      temporary_countermeasure_date: row.temporary_countermeasure_date ? dayjs(row.temporary_countermeasure_date) : null,
      preliminary_analysis: row.preliminary_analysis,
      preliminary_analysis_person: row.preliminary_analysis_person,
      root_cause_analysis_person: row.root_cause_analysis_person,
      audit_comment: row.audit_comment,
      auditor: row.auditor,
      quality_manager_approval: row.quality_manager_approval,
      general_manager_approval: row.general_manager_approval,
      missed_inspector: row.missed_inspector,
    })
    setModalOpen(true)
  }

  const handleSubmit = async (values: any) => {
    const payload = editRecord
      ? {
          status: values.status,
          workflow_status: values.workflow_status,
          improvement_countermeasures: values.improvement_countermeasures,
          improvement_countermeasures_date: values.improvement_countermeasures_date ? dayjs(values.improvement_countermeasures_date).format('YYYY-MM-DD') : null,
          temporary_countermeasure: values.temporary_countermeasure,
          temporary_countermeasure_date: values.temporary_countermeasure_date ? dayjs(values.temporary_countermeasure_date).format('YYYY-MM-DD') : null,
          preliminary_analysis: values.preliminary_analysis,
          preliminary_analysis_person: values.preliminary_analysis_person,
          root_cause_analysis_person: values.root_cause_analysis_person,
          audit_comment: values.audit_comment,
          auditor: values.auditor,
          quality_manager_approval: values.quality_manager_approval,
          general_manager_approval: values.general_manager_approval,
          missed_inspector: values.missed_inspector,
        }
      : {
          ...values,
          submit_date: values.submit_date ? dayjs(values.submit_date).format('YYYY-MM-DD') : null,
          improvement_countermeasures_date: values.improvement_countermeasures_date ? dayjs(values.improvement_countermeasures_date).format('YYYY-MM-DD') : null,
          temporary_countermeasure_date: values.temporary_countermeasure_date ? dayjs(values.temporary_countermeasure_date).format('YYYY-MM-DD') : null,
        }
    try {
      if (editRecord) {
        await exceptionApi.updateQuality(editRecord.id, payload)
        message.success('更新成功')
      } else {
        await exceptionApi.createQuality(payload)
        message.success('新增成功')
      }
      setModalOpen(false)
      load()
    } catch (e: any) {
      // 错误已由全局拦截器提示
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await exceptionApi.deleteQuality(id)
      message.success('删除成功')
      load()
    } catch (e: any) {
      // 错误已由全局拦截器提示
    }
  }

  const handleTableChange = (pagination: any, filters: Record<string, any[] | null>, sorter: any) => {
    setPage(pagination.current || 1)
    setPageSize(pagination.pageSize || pageSize)
    setTableFilters(filters)
    setSorterState({
      field: sorter?.field,
      order: sorter?.order,
    })
  }

  const uniqueFilters = (field: string) => Array.from(new Set(data.map(item => item[field]).filter(Boolean))).map(value => ({ text: String(value), value: String(value) }))
  const serverColumn = (field: string) => ({
    sorter: true,
    filters: uniqueFilters(field),
  })

  const columnByKey: Record<string, any> = {
    issue_no: { title: '编号', dataIndex: 'issue_no', key: 'issue_no', width: 120, ...serverColumn('issue_no') },
    order_no: { title: '订单编号', dataIndex: 'order_no', key: 'order_no', width: 120, ...serverColumn('order_no') },
    product_code: { title: '产品代码', dataIndex: 'product_code', key: 'product_code', width: 120, ...serverColumn('product_code') },
    submit_dept: { title: '提出部门', dataIndex: 'submit_dept', key: 'submit_dept', width: 80, ...serverColumn('submit_dept') },
    submit_date: { title: '提出日期', dataIndex: 'submit_date', key: 'submit_date', width: 100, ...serverColumn('submit_date'), render: (v: string) => formatDate(v) },
    submitter: { title: '提出人', dataIndex: 'submitter', key: 'submitter', width: 75, ...serverColumn('submitter') },
    product_name: { title: '产品名称', dataIndex: 'product_name', key: 'product_name', width: 120, ellipsis: true, ...serverColumn('product_name') },
    process: { title: '工序', dataIndex: 'process', key: 'process', width: 80, ...serverColumn('process') },
    defect_type: { title: '缺陷类型', dataIndex: 'defect_type', key: 'defect_type', width: 90, ...serverColumn('defect_type') },
    description: {
      title: '异常描述', dataIndex: 'description', key: 'description', ellipsis: true, width: 200,
      ...serverColumn('description'),
      render: (v: string | null) => <span title={v || ''}>{v || '-'}</span>,
    },
    root_cause: {
      title: '真实原因', dataIndex: 'root_cause', key: 'root_cause', ellipsis: true, width: 180,
      ...serverColumn('root_cause'),
      render: (v: string | null) => <span title={v || ''}>{v || '-'}</span>,
    },
    responsible_person: { title: '责任人', dataIndex: 'responsible_person', key: 'responsible_person', width: 75, ...serverColumn('responsible_person') },
    responsible_dept: { title: '责任部门', dataIndex: 'responsible_dept', key: 'responsible_dept', width: 80, ...serverColumn('responsible_dept') },
    batch_qty: { title: '批量数', dataIndex: 'batch_qty', key: 'batch_qty', width: 70, ...serverColumn('batch_qty'), render: (v: number | null) => v ?? '-' },
    sample_qty: { title: '抽样数量', dataIndex: 'sample_qty', key: 'sample_qty', width: 75, ...serverColumn('sample_qty'), render: (v: number | null) => v ?? '-' },
    defect_qty: { title: '不良数', dataIndex: 'defect_qty', key: 'defect_qty', width: 70, ...serverColumn('defect_qty'), render: (v: number | null) => v ?? '-' },
    improvement_countermeasures: {
      title: '改善对策', dataIndex: 'improvement_countermeasures', key: 'improvement_countermeasures',
      width: 150, ellipsis: true, ...serverColumn('improvement_countermeasures'),
      render: (v: string | null) => <span title={v || ''}>{v || '-'}</span>,
    },
    improvement_countermeasures_date: { title: '改善对策日期', dataIndex: 'improvement_countermeasures_date', key: 'improvement_countermeasures_date', width: 110, ...serverColumn('improvement_countermeasures_date'), render: (v: string) => formatDate(v) },
    temporary_countermeasure: {
      title: '临时对策', dataIndex: 'temporary_countermeasure', key: 'temporary_countermeasure',
      width: 120, ellipsis: true, ...serverColumn('temporary_countermeasure'),
      render: (v: string | null) => <span title={v || ''}>{v || '-'}</span>,
    },
    temporary_countermeasure_date: { title: '临时对策时间', dataIndex: 'temporary_countermeasure_date', key: 'temporary_countermeasure_date', width: 110, ...serverColumn('temporary_countermeasure_date'), render: (v: string) => formatDate(v) },
    preliminary_analysis_person: {
      title: '初步分析负责人', dataIndex: 'preliminary_analysis_person', key: 'preliminary_analysis_person',
      width: 100, ...serverColumn('preliminary_analysis_person'),
      render: (v: string | null) => v || '-',
    },
    quality_manager_approval: {
      title: '品质经理审批', dataIndex: 'quality_manager_approval', key: 'quality_manager_approval',
      width: 180, ellipsis: true, ...serverColumn('quality_manager_approval'),
      render: (v: string | null) => <span title={v || ''}>{v || '-'}</span>,
    },
    defect_rate: {
      title: '不良率', dataIndex: 'defect_rate', key: 'defect_rate', width: 80, sorter: true,
      render: (_: any, row: any) => {
        const sampleQty = Number(row.sample_qty || 0)
        const defectQty = Number(row.defect_qty || 0)
        if (!sampleQty) return '-'
        return `${((defectQty / sampleQty) * 100).toFixed(2)}%`
      },
    },
    workflow_status: {
      title: '流程状态', dataIndex: 'workflow_status', key: 'workflow_status', width: 90, fixed: 'right' as const,
      sorter: true,
      filters: WORKFLOW_STATUS_OPTIONS.map(v => ({ text: v, value: v })),
      render: (v: string) => {
        const s = WORKFLOW_STATUS_MAP[v] || { label: v || '-', color: 'default' }
        return <Tag color={s.color}>{s.label}</Tag>
      },
    },
    status: {
      title: '状态', dataIndex: 'status', key: 'status', width: 85, fixed: 'right' as const,
      sorter: true,
      filters: [
        { text: '待处理', value: 'open' },
        { text: '处理中', value: 'in_progress' },
        { text: '已关闭', value: 'closed' },
      ],
      render: (v: string) => {
        const s = STATUS_MAP[v] || { label: v, color: 'default' }
        return <Tag color={s.color}>{s.label}</Tag>
      },
    },
    __action__: {
      title: '操作', key: '__action__', width: 90, fixed: 'right' as const,
      render: (_: any, row: any) => (
        <Space size={4}>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(row.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  }

  const orderedVisible = [
    ...columnOrder.filter(k => visibleColumnKeys.includes(k)),
    ...visibleColumnKeys.filter(k => !columnOrder.includes(k)),
  ]
  const columns = [
    ...orderedVisible.map(k => columnByKey[k]).filter(Boolean),
    ...FIXED_RIGHT_KEYS.map(k => columnByKey[k]).filter(Boolean),
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col flex="auto">
            <Input
              allowClear
              placeholder="模糊查询：订单编号、产品代码、提出部门、提出人、产品名称、工序、缺陷类型、异常描述、真实原因、责任人、责任部门、改善对策"
              value={keyword}
              onChange={e => {
                setKeyword(e.target.value)
                if (page !== 1) setPage(1)
              }}
              style={{ maxWidth: 720 }}
            />
          </Col>
          <Col>
            <Space>
              <Button onClick={() => setShowAnalysis(!showAnalysis)}>
                {showAnalysis ? '隐藏分析' : '统计分析'}
              </Button>
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
              <Popover
                trigger="click"
                placement="bottomRight"
                content={
                  <ColumnSettingsPanel
                    order={columnOrder}
                    visibleKeys={visibleColumnKeys}
                    onToggle={handleToggleColumn}
                    onReorder={handleReorderColumn}
                    onReset={handleResetColumns}
                  />
                }
              >
                <Button icon={<SettingOutlined />}>列设置</Button>
              </Popover>
              <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增品质异常</Button>
            </Space>
          </Col>
        </Row>
      </div>

      {/* 统计分析面板 */}
      {showAnalysis && statistics && (
        <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <span style={{ fontSize: 16, fontWeight: 600 }}>品质异常统计分析</span>
            <Button type="primary" icon={<ThunderboltOutlined />} loading={analysisLoading} onClick={handleAnalyze}>
              分析
            </Button>
          </div>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <div style={{ background: '#f8fafc', padding: 16, borderRadius: 8 }}>
                <div style={{ color: '#64748b', fontSize: 12, marginBottom: 4 }}>异常总数</div>
                <div style={{ fontSize: 24, fontWeight: 700, color: '#1e293b' }}>{statistics.total}</div>
              </div>
            </Col>
            <Col span={6}>
              <div style={{ background: '#fef2f2', padding: 16, borderRadius: 8 }}>
                <div style={{ color: '#dc2626', fontSize: 12, marginBottom: 4 }}>待处理</div>
                <div style={{ fontSize: 24, fontWeight: 700, color: '#dc2626' }}>{statistics.openCount}</div>
              </div>
            </Col>
            <Col span={6}>
              <div style={{ background: '#fef3c7', padding: 16, borderRadius: 8 }}>
                <div style={{ color: '#d97706', fontSize: 12, marginBottom: 4 }}>处理中</div>
                <div style={{ fontSize: 24, fontWeight: 700, color: '#d97706' }}>{statistics.inProgressCount}</div>
              </div>
            </Col>
            <Col span={6}>
              <div style={{ background: '#f0fdf4', padding: 16, borderRadius: 8 }}>
                <div style={{ color: '#16a34a', fontSize: 12, marginBottom: 4 }}>已关闭</div>
                <div style={{ fontSize: 24, fontWeight: 700, color: '#16a34a' }}>{statistics.closedCount}</div>
              </div>
            </Col>
          </Row>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={8}>
              <div style={{ background: '#f8fafc', padding: 16, borderRadius: 8 }}>
                <div style={{ color: '#64748b', fontSize: 12, marginBottom: 4 }}>总不良数</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: '#1e293b' }}>{statistics.totalDefectQty}</div>
              </div>
            </Col>
            <Col span={8}>
              <div style={{ background: '#f8fafc', padding: 16, borderRadius: 8 }}>
                <div style={{ color: '#64748b', fontSize: 12, marginBottom: 4 }}>总抽样数</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: '#1e293b' }}>{statistics.totalSampleQty}</div>
              </div>
            </Col>
            <Col span={8}>
              <div style={{ background: '#f8fafc', padding: 16, borderRadius: 8 }}>
                <div style={{ color: '#64748b', fontSize: 12, marginBottom: 4 }}>平均不良率</div>
                <div style={{ fontSize: 20, fontWeight: 700, color: '#dc2626' }}>{statistics.avgDefectRate}%</div>
              </div>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <div style={{ marginBottom: 8, fontWeight: 600, fontSize: 14 }}>按缺陷类型分布</div>
              <div style={{ maxHeight: 200, overflowY: 'auto', background: '#f8fafc', padding: 12, borderRadius: 8 }}>
                {Object.entries(statistics.byDefectType).map(([type, count]) => (
                  <div key={type} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #e2e8f0' }}>
                    <span>{type}</span>
                    <span style={{ fontWeight: 600 }}>{count as number}</span>
                  </div>
                ))}
              </div>
            </Col>
            <Col span={12}>
              <div style={{ marginBottom: 8, fontWeight: 600, fontSize: 14 }}>按部门分布</div>
              <div style={{ maxHeight: 200, overflowY: 'auto', background: '#f8fafc', padding: 12, borderRadius: 8 }}>
                {Object.entries(statistics.byDept).map(([dept, count]) => (
                  <div key={dept} style={{ display: 'flex', justifyContent: 'space-between', padding: '4px 0', borderBottom: '1px solid #e2e8f0' }}>
                    <span>{dept}</span>
                    <span style={{ fontWeight: 600 }}>{count as number}</span>
                  </div>
                ))}
              </div>
            </Col>
          </Row>
        </div>
      )}

      <div className="card-modern qi-table" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="id"
          dataSource={data}
          columns={columns}
          loading={loading}
          onChange={handleTableChange}
          scroll={{ x: 2600, y: 'calc(100vh - 264px)' }}
          size="small"
          pagination={{
            total, current: page, pageSize,
            onChange: (p, ps) => { setPage(p); setPageSize(ps) },
            showSizeChanger: true, showTotal: t => `共 ${t} 条`,
          }}
        />
      </div>

      <Modal
        title={editRecord ? '编辑品质异常' : '新增品质异常'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        width={editRecord ? 800 : 800}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit} initialValues={{ status: 'open' }}>
          {editRecord ? (
            <>
              <Form.Item name="status" label="状态">
                <Select>
                  <Select.Option value="open">待处理</Select.Option>
                  <Select.Option value="in_progress">处理中</Select.Option>
                  <Select.Option value="closed">已关闭</Select.Option>
                </Select>
              </Form.Item>
              <Form.Item name="workflow_status" label="流程状态">
                <Select>
                  {WORKFLOW_STATUS_OPTIONS.map(v => (
                    <Select.Option key={v} value={v}>{v}</Select.Option>
                  ))}
                </Select>
              </Form.Item>
              <Form.Item name="improvement_countermeasures" label="改善对策">
                <Input.TextArea rows={2} />
              </Form.Item>
              <Form.Item name="improvement_countermeasures_date" label="改善对策日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="temporary_countermeasure" label="临时对策">
                <Input.TextArea rows={2} />
              </Form.Item>
              <Form.Item name="temporary_countermeasure_date" label="临时对策时间">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item name="preliminary_analysis" label="初步分析">
                <Input.TextArea rows={2} />
              </Form.Item>
              <Form.Item name="preliminary_analysis_person" label="初步分析负责人">
                <Input />
              </Form.Item>
              <Form.Item name="root_cause_analysis_person" label="真因分析负责人">
                <Input />
              </Form.Item>
              <Form.Item name="audit_comment" label="审核意见">
                <Input.TextArea rows={2} />
              </Form.Item>
              <Form.Item name="auditor" label="审核人">
                <Input />
              </Form.Item>
              <Form.Item name="quality_manager_approval" label="品质经理审批">
                <Input.TextArea rows={2} />
              </Form.Item>
              <Form.Item name="general_manager_approval" label="总经理审批">
                <Select allowClear>
                  <Select.Option value="pending">待审批</Select.Option>
                  <Select.Option value="approved">已批准</Select.Option>
                  <Select.Option value="rejected">已拒绝</Select.Option>
                </Select>
              </Form.Item>
              <Form.Item name="missed_inspector" label="漏检人">
                <Input />
              </Form.Item>
            </>
          ) : (
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="submit_dept" label="提出部门">
                <Select allowClear>
                  {DEPT_OPTIONS.map(d => (
                    <Select.Option key={d} value={d}>{d}</Select.Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}><Form.Item name="submit_date" label="提出日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="submitter" label="提出人"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="order_no" label="订单编号"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="product_code" label="产品代码"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="product_name" label="产品名称"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="process" label="工序"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="defect_type" label="缺陷类型"><Input /></Form.Item></Col>
            <Col span={8}>
              <Form.Item name="status" label="状态">
                <Select>
                  <Select.Option value="open">待处理</Select.Option>
                  <Select.Option value="in_progress">处理中</Select.Option>
                  <Select.Option value="closed">已关闭</Select.Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="workflow_status" label="流程状态" initialValue="创建">
                <Select>
                  {WORKFLOW_STATUS_OPTIONS.map(v => (
                    <Select.Option key={v} value={v}>{v}</Select.Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="description" label="异常描述">
                <Input.TextArea rows={3} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="root_cause" label="真实原因">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Col>
            <Col span={8}><Form.Item name="responsible_person" label="责任人"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="responsible_dept" label="责任部门"><Input /></Form.Item></Col>
            <Col span={8} />
            <Col span={8}><Form.Item name="batch_qty" label="批量数"><InputNumber style={{ width: '100%' }} min={0} /></Form.Item></Col>
            <Col span={8}><Form.Item name="sample_qty" label="抽样数量"><InputNumber style={{ width: '100%' }} min={0} /></Form.Item></Col>
            <Col span={8}><Form.Item name="defect_qty" label="不良数"><InputNumber style={{ width: '100%' }} min={0} /></Form.Item></Col>
            <Col span={24}>
              <Form.Item name="improvement_countermeasures" label="改善对策">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="improvement_countermeasures_date" label="改善对策日期">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={16} />
            
            {/* 临时对策 */}
            <Col span={24}>
              <Form.Item name="temporary_countermeasure" label="临时对策">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="temporary_countermeasure_date" label="临时对策时间">
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={16} />
            
            {/* 分析 */}
            <Col span={24}>
              <Form.Item name="preliminary_analysis" label="初步分析">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="preliminary_analysis_person" label="初步分析负责人">
                <Input />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="root_cause_analysis_person" label="真因分析负责人">
                <Input />
              </Form.Item>
            </Col>
            <Col span={8} />
            
            {/* 审批 */}
            <Col span={24}>
              <Form.Item name="audit_comment" label="审核意见">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="auditor" label="审核人">
                <Input />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="quality_manager_approval" label="品质经理审批">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="general_manager_approval" label="总经理审批">
                <Select allowClear>
                  <Select.Option value="pending">待审批</Select.Option>
                  <Select.Option value="approved">已批准</Select.Option>
                  <Select.Option value="rejected">已拒绝</Select.Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="missed_inspector" label="漏检人">
                <Input />
              </Form.Item>
            </Col>
            <Col span={16} />
            
            <Col span={24}>
              <Form.Item name="remark" label="备注">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Col>
          </Row>
          )}
        </Form>
      </Modal>
      <AnalysisReportDrawer
        open={analysisDrawerOpen}
        onClose={() => setAnalysisDrawerOpen(false)}
        report={analysisReport}
        loading={analysisLoading}
        error={analysisError}
        onRerun={handleAnalyze}
      />
    </div>
  )
}
