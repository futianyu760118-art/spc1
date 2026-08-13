import { useState, useEffect, useCallback } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, Space, message,
  Popconfirm, Tag, Alert, Divider, Tooltip, Empty, Switch, Row, Col,
  AutoComplete,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, PlayCircleOutlined,
  SwapOutlined, ThunderboltOutlined, SearchOutlined, MinusCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import api from '../../services/api'
import PermButton from '../../components/PermButton'
import { useAuthStore } from '../../store/auth'

const { TextArea } = Input

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */
interface SyncSqlItem {
  id: number
  sync_type: string
  description: string
  sql_text: string
  field_mapping_json: string | null
  condition_params_json: string | null
  is_active: boolean
  updated_at: string | null
  // 同步配置字段
  sync_interval: string
  sync_strategy: string
  sync_time_window: string | null
  sync_priority: number
  sync_enabled: boolean
  last_sync_time: string | null
  next_sync_time: string | null
  last_sync_status: string | null
  last_sync_message: string | null
}

interface SpcField {
  name: string
  type: string
  nullable: boolean
}

interface MappingRow {
  erp_field: string
  spc_field: string | null
  remark: string
}

interface ConditionParam {
  parameter_name: string
  parameter_type: 'string' | 'number' | 'date' | 'list' | 'boolean'
  label: string
  default_value?: string
  required: boolean
  description?: string
}

const SYNC_TYPE_LABELS: Record<string, string> = {
  orders: '订单数据',
  order_details: '订单明细数据',
  materials: '物料需求',
  purchase_orders: '采购订单',
  customers: '客户',
  suppliers: '供应商',
  materials_masterdata: '物料',
  skus: 'SKU',
  products: '产品',
  warehouses: '仓库',
  locations: '库位',
  processes: '工序',
  organizations: '组织',
  positions: '岗位',
  employees: '人员',
  employee_organizations: '员工组织关系',
  purchase_invoices: '采购开票',
  quality_issues: '品质异常',
  mrp_plan_orders: 'MRP计划订单',
  inventory: '即时库存',
  subcontract_orders: '委外订单',
  subcontract_order_details: '委外订单明细',
  subject_balances: '科目余额',
  production_daily_reports: '生产日报表',
  labor_price_audits: '工价审核数据',
}

const SYNC_INTERVAL_OPTIONS = [
  { value: '1h', label: '每小时' },
  { value: '2h', label: '每2小时' },
  { value: '6h', label: '每6小时' },
  { value: '12h', label: '每12小时' },
  { value: '1d', label: '每天' },
  { value: '1w', label: '每周' },
]

const SYNC_STRATEGY_OPTIONS = [
  { value: 'incremental', label: '增量同步' },
  { value: 'full', label: '全量同步' },
  { value: 'hybrid', label: '混合同步' },
]

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */
export default function SyncSqlConfig() {
  const [data, setData] = useState<SyncSqlItem[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingItem, setEditingItem] = useState<SyncSqlItem | null>(null)
  const [testResult, setTestResult] = useState<any>(null)
  const [testingId, setTestingId] = useState<number | null>(null)
  const [testModalOpen, setTestModalOpen] = useState(false)
  const [testingInModal, setTestingInModal] = useState(false)
  const [form] = Form.useForm()
  const [sortInfo, setSortInfo] = useState<{ sort_by?: string; sort_order?: string }>({})
  const [tableFilters, setTableFilters] = useState<Record<string, string>>({})

  // ---------- 字段映射状态 ----------
  const [spcFields, setSpcFields] = useState<SpcField[]>([])
  const [spcFieldsLoading, setSpcFieldsLoading] = useState(false)
  const [erpFields, setErpFields] = useState<string[]>([])
  const [erpFieldsLoading, setErpFieldsLoading] = useState(false)
  const [mappingRows, setMappingRows] = useState<MappingRow[]>([])

  // ---------- 条件参数状态 ----------
  const [conditionParams, setConditionParams] = useState<ConditionParam[]>([])

  // ---------- 动态同步类型 ----------
  const [availableTypes, setAvailableTypes] = useState<{value: string, label: string}[]>([])

  const syncTypeLabels: Record<string, string> = { ...SYNC_TYPE_LABELS }
  availableTypes.forEach(t => { if (t.label) syncTypeLabels[t.value] = t.label })

  const hasPermission = useAuthStore(s => s.hasPermission)
  const canCreate = hasPermission('settings', 'create')
  const canUpdate = hasPermission('settings', 'update')
  const canDelete = hasPermission('settings', 'delete')


  /* ================================================================ */
  /* Data fetching                                                     */
  /* ================================================================ */

  const fetchData = async () => {
    setLoading(true)
    try {
      const params: any = {}
      if (sortInfo.sort_by) params.sort_by = sortInfo.sort_by
      if (sortInfo.sort_order) params.sort_order = sortInfo.sort_order
      Object.entries(tableFilters).forEach(([k, v]) => { if (v) params[k] = v })
      const res: any = await api.get('/basicdata/sync-sql', { params })
      setData(res.data || [])
    } catch {
      // 错误已由全局拦截器提示
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [sortInfo, tableFilters]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    api.get('/basicdata/sync-sql/available-types')
      .then((res: any) => setAvailableTypes(res.data || []))
      .catch(() => {})
  }, [])

  const handleTableChange = (_pag: any, filters: any, sorter: any) => {
    const sortField = sorter.field
    const sortOrder = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : undefined
    setSortInfo({ sort_by: sortField, sort_order: sortOrder })
    const newFilters: Record<string, string> = {}
    if (filters.sync_type?.length) newFilters.sync_type = filters.sync_type.join(',')
    if (filters.sync_strategy?.length) newFilters.sync_strategy = filters.sync_strategy.join(',')
    if (filters.last_sync_status?.length) newFilters.last_sync_status = filters.last_sync_status.join(',')
    if (filters.sync_enabled?.length) newFilters.sync_enabled = filters.sync_enabled[0] === 'true' ? 'true' : 'false'
    setTableFilters(newFilters)
  }

  /* ================================================================ */
  /* SPC fields                                                        */
  /* ================================================================ */

  const loadSpcFields = useCallback(async (syncType: string) => {
    if (!syncType) { setSpcFields([]); return }
    setSpcFieldsLoading(true)
    try {
      const res: any = await api.get(`/basicdata/sync-sql/spc-fields/${syncType}`)
      setSpcFields(res.data || [])
    } catch {
      // 错误已由全局拦截器提示
      setSpcFields([])
    } finally {
      setSpcFieldsLoading(false)
    }
  }, [])

  /* ================================================================ */
  /* ERP fields — analyse SQL                                          */
  /* ================================================================ */

  const handleParseErpFields = async () => {
    const sqlText = form.getFieldValue('sql_text')
    if (!sqlText?.trim()) {
      message.warning('请先输入 SQL 语句')
      return
    }
    setErpFieldsLoading(true)
    try {
      const res: any = await api.post('/basicdata/sync-sql/parse-erp-fields', { sql_text: sqlText }, { timeout: 120000 })
      const cols: string[] = res.data || []
      setErpFields(cols)
      // 保留已有映射，新字段追加
      setMappingRows(prev => {
        const existing = new Set(prev.map(r => r.erp_field))
        const kept = prev.filter(r => cols.includes(r.erp_field))
        const added = cols.filter(c => !existing.has(c)).map(c => ({ erp_field: c, spc_field: null, remark: '' }))
        return [...kept, ...added]
      })
      message.success(`解析到 ${cols.length} 个 ERP 字段`)
    } catch (e: any) {
      // 错误已由全局拦截器提示
    } finally {
      setErpFieldsLoading(false)
    }
  }

  /* ================================================================ */
  /* AI Auto-match                                                     */
  /* ================================================================ */

  const [aiMatching, setAiMatching] = useState(false)

  const handleAutoMatch = async () => {
    if (!spcFields.length) {
      message.warning('请先选择同步类型以加载 SPC 字段')
      return
    }
    const syncType = editingItem?.sync_type || form.getFieldValue('sync_type')
    const sqlText = form.getFieldValue('sql_text')
    if (!sqlText || !sqlText.trim()) {
      message.warning('请先输入 SQL 语句')
      return
    }

    setAiMatching(true)
    try {
      const res: any = await api.post(
        '/basicdata/sync-sql/ai-auto-match',
        {
          sql_text: sqlText,
          sync_type: syncType,
          erp_fields: erpFields,
          spc_fields: spcFields,
        },
        { timeout: 180000 },
      )
      const aiMappings = res.data?.mappings || {}

      const updated = mappingRows.map(row => {
        const ai = aiMappings[row.erp_field]
        if (!ai || ai.spc_field === null || ai.spc_field === undefined) return row
        return { ...row, spc_field: ai.spc_field || null, remark: ai.remark || row.remark }
      })

      // 如果还有未匹配但 AI 有结果的字段，也补上
      const existingErp = new Set(mappingRows.map(r => r.erp_field))
      for (const [erpField, ai] of Object.entries(aiMappings)) {
        if (!existingErp.has(erpField) && ai && (ai as any).spc_field) {
          updated.push({ erp_field: erpField, spc_field: (ai as any).spc_field || null, remark: (ai as any).remark || '' })
        }
      }

      setMappingRows(updated)
      const matched = updated.filter(r => r.spc_field).length
      const withRemark = updated.filter(r => r.remark).length
      message.success(`AI 匹配完成：${matched}/${updated.length} 个字段已映射，${withRemark} 个字段已添加备注`)
    } catch (e: any) {
      const detail = e?.response?.data?.detail || e?.message || 'AI 匹配失败'
      if (detail.includes('AI 服务未配置')) {
        // fallback 到简单名称匹配
        message.warning('AI 服务未配置，使用简单名称匹配')
        simpleAutoMatch()
        return
      }
      // 错误已由全局拦截器提示
    } finally {
      setAiMatching(false)
    }
  }

  const simpleAutoMatch = () => {
    const spcNames = new Set(spcFields.map(f => f.name))
    const updated = mappingRows.map(row => {
      if (row.spc_field) return row
      const lower = row.erp_field.toLowerCase()
      if (spcNames.has(lower)) return { ...row, spc_field: lower }
      if (spcNames.has(row.erp_field)) return { ...row, spc_field: row.erp_field }
      return row
    })
    setMappingRows(updated)
    const matched = updated.filter(r => r.spc_field).length
    message.info(`简单匹配了 ${matched} / ${updated.length} 个字段`)
  }

  /* ================================================================ */
  /* Mapping row CRUD                                                  */
  /* ================================================================ */

  const updateMappingSpc = (index: number, value: string | null) => {
    setMappingRows(prev => prev.map((r, i) => i === index ? { ...r, spc_field: value } : r))
  }

  const updateMappingRemark = (index: number, value: string) => {
    setMappingRows(prev => prev.map((r, i) => i === index ? { ...r, remark: value } : r))
  }

  const removeMappingRow = (index: number) => {
    setMappingRows(prev => prev.filter((_, i) => i !== index))
  }

  // ---------- 条件参数 CRUD ----------
  const addConditionParam = () => {
    setConditionParams(prev => [...prev, {
      parameter_name: '',
      parameter_type: 'string',
      label: '',
      default_value: '',
      required: false,
      description: ''
    }])
  }

  const updateConditionParam = (index: number, field: keyof ConditionParam, value: any) => {
    setConditionParams(prev => prev.map((p, i) => i === index ? { ...p, [field]: value } : p))
  }

  const removeConditionParam = (index: number) => {
    setConditionParams(prev => prev.filter((_, i) => i !== index))
  }

  /* ================================================================ */
  /* Mapping JSON ↔ rows                                               */
  /* ================================================================ */

  const mappingToJson = (rows: MappingRow[]): string => {
    const obj: Record<string, string | { target: string; remark: string }> = {}
    rows.forEach(r => {
      if (r.spc_field) {
        if (r.remark) {
          obj[r.erp_field] = { target: r.spc_field, remark: r.remark }
        } else {
          obj[r.erp_field] = r.spc_field
        }
      }
    })
    return JSON.stringify(obj, null, 2)
  }

  const jsonToMapping = (json: string | null, erpCols: string[]): MappingRow[] => {
    let parsed: Record<string, any> = {}
    if (json) {
      try { parsed = JSON.parse(json) } catch { /* ignore */ }
    }
    const allErp = new Set([...Object.keys(parsed), ...erpCols])
    return Array.from(allErp).map(erp => {
      const val = parsed[erp]
      if (typeof val === 'object' && val !== null) {
        return { erp_field: erp, spc_field: val.target || null, remark: val.remark || '' }
      }
      return { erp_field: erp, spc_field: typeof val === 'string' ? val : null, remark: '' }
    })
  }

  const conditionParamsToJson = (params: ConditionParam[]): string => {
    return JSON.stringify(params, null, 2)
  }

  const jsonToConditionParams = (json: string | null): ConditionParam[] => {
    if (!json) return []
    try {
      return JSON.parse(json)
    } catch {
      return []
    }
  }

  /* ================================================================ */
  /* Modal open / save                                                 */
  /* ================================================================ */

  const openAdd = () => {
    setEditingItem(null)
    form.resetFields()
    form.setFieldsValue({
      sync_interval: '1h',
      sync_strategy: 'incremental',
      sync_time_window: null,
      sync_priority: 5,
      sync_enabled: true,
    })
    setTestResult(null)
    setSpcFields([])
    setErpFields([])
    setMappingRows([])
    setConditionParams([])
    setModalOpen(true)
  }

  const openEdit = (record: SyncSqlItem) => {
    setEditingItem(record)
    form.setFieldsValue(record)
    setTestResult(null)
    // 加载 SPC 字段
    loadSpcFields(record.sync_type)
    // 还原映射
    const rows = jsonToMapping(record.field_mapping_json, [])
    setMappingRows(rows)
    setErpFields(rows.map(r => r.erp_field))
    // 还原条件参数
    setConditionParams(jsonToConditionParams(record.condition_params_json))
    setModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      // 将映射表格序列化为 JSON
      values.field_mapping_json = mappingToJson(mappingRows)
      // 将条件参数序列化为 JSON
      values.condition_params_json = conditionParamsToJson(conditionParams)
      if (editingItem) {
        await api.put(`/basicdata/sync-sql/${editingItem.id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/basicdata/sync-sql', values)
        message.success('创建成功')
      }
      setModalOpen(false)
      fetchData()
    } catch (e: any) {
      // 错误已由全局拦截器提示
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/basicdata/sync-sql/${id}`)
      message.success('已删除')
      fetchData()
    } catch {
      // 错误已由全局拦截器提示
    }
  }

  const handleTest = async (id: number) => {
    setTestingId(id)
    setTestResult(null)
    try {
      const res: any = await api.post(`/basicdata/sync-sql/${id}/test`, {}, { timeout: 120000 })
      console.log('[SyncSqlConfig] test response:', res)
      const result = res.data?.total_rows !== undefined ? res.data : res
      setTestResult(result)
      setTestModalOpen(true)
      message.success(`查询成功，共 ${result?.total_rows ?? 0} 条`)
    } catch (e: any) {
      // 错误已由全局拦截器提示
    } finally {
      setTestingId(null)
    }
  }

  const handleTestInModal = async () => {
    const sqlText = form.getFieldValue('sql_text')
    if (!sqlText?.trim()) {
      message.warning('请先输入 SQL 语句')
      return
    }
    setTestingInModal(true)
    setTestResult(null)
    try {
      const res: any = await api.post('/basicdata/sync-sql/test-sql', { sql_text: sqlText }, { timeout: 120000 })
      const result = res.data?.total_rows !== undefined ? res.data : res
      setTestResult(result)
      setTestModalOpen(true)
      message.success(`查询成功，共 ${result?.total_rows ?? 0} 条`)
    } catch (e: any) {
      // 错误已由全局拦截器提示
    } finally {
      setTestingInModal(false)
    }
  }

  /* ================================================================ */
  /* sync_type 切换时自动加载 SPC 字段                                    */
  /* ================================================================ */

  const handleSyncTypeChange = (val: string) => {
    form.setFieldValue('sync_type', val)
    loadSpcFields(val)
  }

  /* ================================================================ */
  /* Table columns                                                     */
  /* ================================================================ */

  const columns = [
    {
      title: '同步类型', dataIndex: 'sync_type', key: 'sync_type', width: 120, sorter: true,
      filters: Object.entries(syncTypeLabels).map(([k, v]) => ({ text: v, value: k })),
      render: (v: string) => <Tag color="blue">{syncTypeLabels[v] || v}</Tag>,
    },
    { title: '说明', dataIndex: 'description', key: 'description', ellipsis: true, width: 150, sorter: true },
    {
      title: '同步间隔', dataIndex: 'sync_interval', key: 'sync_interval', width: 80, sorter: true,
      render: (v: string) => {
        const option = SYNC_INTERVAL_OPTIONS.find(o => o.value === v)
        return option ? <Tag color="purple">{option.label}</Tag> : <Tag>{v}</Tag>
      },
    },
    {
      title: '同步策略', dataIndex: 'sync_strategy', key: 'sync_strategy', width: 90, sorter: true,
      filters: SYNC_STRATEGY_OPTIONS.map(o => ({ text: o.label, value: o.value })),
      render: (v: string) => {
        const option = SYNC_STRATEGY_OPTIONS.find(o => o.value === v)
        return option ? <Tag color="orange">{option.label}</Tag> : <Tag>{v}</Tag>
      },
    },
    {
      title: '时间窗口', dataIndex: 'sync_time_window', key: 'sync_time_window', width: 100,
      render: (v: string | null) => v ? <Tag color="cyan">{v}</Tag> : <Tag color="default">不限</Tag>,
    },
    {
      title: '优先级', dataIndex: 'sync_priority', key: 'sync_priority', width: 60, sorter: true,
      render: (v: number) => <Tag color={v <= 3 ? 'red' : v <= 6 ? 'orange' : 'default'}>{v}</Tag>,
    },
    {
      title: '同步状态', dataIndex: 'last_sync_status', key: 'last_sync_status', width: 90, sorter: true,
      filters: [{ text: '成功', value: 'success' }, { text: '失败', value: 'failed' }, { text: '运行中', value: 'running' }, { text: '未运行', value: '' }],
      render: (v: string | null, record: SyncSqlItem) => {
        if (!v) return <Tag color="default">未运行</Tag>
        if (v === 'success') return <Tag color="green" icon={<PlayCircleOutlined />}>成功</Tag>
        if (v === 'failed') return <Tag color="red" icon={<DeleteOutlined />}>失败</Tag>
        if (v === 'running') return <Tag color="blue" icon={<ThunderboltOutlined />}>运行中</Tag>
        return <Tag>{v}</Tag>
      },
    },
    {
      title: '下次同步', dataIndex: 'next_sync_time', key: 'next_sync_time', width: 140, sorter: true,
      render: (v: string | null) => v ? <span style={{ fontSize: 11 }}>{new Date(v).toLocaleString('zh-CN')}</span> : <span style={{ color: '#94a3b8', fontSize: 11 }}>-</span>,
    },
    {
      title: '启用', dataIndex: 'sync_enabled', key: 'sync_enabled', width: 60, sorter: true,
      filters: [{ text: '是', value: 'true' }, { text: '否', value: 'false' }],
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '是' : '否'}</Tag>,
    },
    {
      title: '操作', key: 'action', width: 180, fixed: 'right' as const,
      render: (_: any, record: SyncSqlItem) => (
        <Space size="small">
          <Button size="small" icon={<PlayCircleOutlined />} loading={testingId === record.id} onClick={() => handleTest(record.id)}>测试</Button>
          <PermButton permResource="settings" permAction="update" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</PermButton>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)} disabled={!canDelete}>
            <PermButton permResource="settings" permAction="delete" size="small" icon={<DeleteOutlined />} danger />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  /* ================================================================ */
  /* 已使用的 SPC 字段集合（用于下拉选项标记）                              */
  /* ================================================================ */

  const usedSpcFields = new Set(mappingRows.map(r => r.spc_field).filter(Boolean))

  /* ================================================================ */
  /* Render                                                            */
  /* ================================================================ */

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
              <PermButton permResource="settings" permAction="create" type="primary" icon={<PlusOutlined />} onClick={openAdd}>添加配置</PermButton>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table columns={columns} dataSource={data} rowKey="id" loading={loading} size="small" scroll={{ x: 1400 }} onChange={handleTableChange} pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`, pageSizeOptions: ['20', '50', '100'] }} />
      </div>

      {/* 测试结果弹窗 */}
      <Modal
        title="SQL 测试结果"
        open={testModalOpen}
        onCancel={() => setTestModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setTestModalOpen(false)}>
            关闭
          </Button>,
        ]}
        width={1100}
        styles={{ body: { maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' } }}
      >
        {testResult && (
          <div>
            <div style={{ marginBottom: 16 }}>
              <Alert
                type="success"
                showIcon
                message={`查询成功：共 ${testResult.total_rows} 条记录${testResult.elapsed_seconds != null ? `，耗时 ${testResult.elapsed_seconds}s` : ''}`}
                description={`返回字段(${testResult.columns?.length || 0})：${testResult.columns?.join(', ')}`}
              />
            </div>
            <div style={{ marginBottom: 8 }}>
              <strong>数据预览（前 {testResult.preview?.length || 0} 条）：</strong>
            </div>
            <Table
              dataSource={testResult.preview?.map((row: any, idx: number) => ({ ...row, _rowKey: idx }))}
              rowKey="_rowKey"
              size="small"
              scroll={{ x: 'max-content', y: 400 }}
              pagination={false}
              bordered
              columns={testResult.columns?.map((col: string) => ({
                title: col,
                dataIndex: col,
                key: col,
                width: 160,
                ellipsis: { showTitle: false },
                render: (val: any) => (
                  <Tooltip placement="topLeft" title={val != null ? String(val) : ''}>
                    <span style={{ fontSize: 12 }}>{val != null ? String(val) : <span style={{ color: '#ccc' }}>NULL</span>}</span>
                  </Tooltip>
                ),
              })) || []}
            />
          </div>
        )}
      </Modal>

      {/* ============ 编辑弹窗 ============ */}
      <Modal
        title={editingItem ? '编辑同步 SQL' : '新增同步 SQL'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        width={860}
        styles={{ body: { maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' } }}
      >
        <Form form={form} layout="vertical">
          {/* ---- 基本信息 ---- */}
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item name="sync_type" label="同步类型" rules={[{ required: true, message: '选择或输入同步类型' }]} style={{ flex: 1 }}>
              <AutoComplete
                placeholder="选择或输入同步类型"
                disabled={!!editingItem}
                onChange={handleSyncTypeChange}
                filterOption={(input, option) =>
                  (option?.value ?? '').toLowerCase().includes(input.toLowerCase())
                }
                options={
                  availableTypes.length > 0
                    ? availableTypes.map(t => ({ value: t.value, label: t.label }))
                    : Object.entries(SYNC_TYPE_LABELS).map(([k, v]) => ({ value: k, label: v }))
                }
              />
            </Form.Item>
            <Form.Item name="description" label="说明" style={{ flex: 2 }}>
              <Input placeholder="SQL 用途说明" />
            </Form.Item>
          </div>

          {/* ---- 同步配置 ---- */}
          <Divider style={{ margin: '8px 0 16px' }}>
            <ThunderboltOutlined /> 同步配置
          </Divider>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item 
              name="sync_interval" 
              label="同步间隔" 
              initialValue="1h"
              rules={[{ required: true, message: '选择同步间隔' }]}
              style={{ flex: 1 }}
              extra="多久执行一次同步"
            >
              <Select options={SYNC_INTERVAL_OPTIONS} />
            </Form.Item>
            <Form.Item 
              name="sync_strategy" 
              label="同步策略" 
              initialValue="incremental"
              rules={[{ required: true, message: '选择同步策略' }]}
              style={{ flex: 1 }}
              extra="增量/全量/混合同步"
            >
              <Select options={SYNC_STRATEGY_OPTIONS} />
            </Form.Item>
            <Form.Item 
              name="sync_time_window" 
              label="时间窗口" 
              style={{ flex: 1 }}
              extra="如: 02:00-04:00，留空表示不限"
            >
              <Input placeholder="HH:MM-HH:MM" />
            </Form.Item>
          </div>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item 
              name="sync_priority" 
              label="优先级" 
              initialValue={5}
              rules={[{ required: true, message: '输入优先级' }]}
              style={{ flex: 1 }}
              extra="1-10，数字越小优先级越高"
            >
              <Input type="number" min={1} max={10} />
            </Form.Item>
            <Form.Item 
              name="sync_enabled" 
              label="启用同步" 
              initialValue={true}
              valuePropName="checked"
              style={{ flex: 0, minWidth: 120 }}
            >
              <Switch />
            </Form.Item>
          </div>

          {/* ---- SQL 语句 ---- */}
          <Form.Item
            name="sql_text"
            label="SQL 语句"
            rules={[{ required: true, message: '输入 SQL' }]}
            extra="使用 :since 作为增量时间参数，SELECT 的列名将作为 ERP 字段名用于映射"
          >
            <TextArea
              rows={8}
              placeholder="SELECT FBillNo AS order_no, ... FROM ... WHERE update_time >= :since"
              style={{ fontFamily: 'monospace', fontSize: 12 }}
            />
          </Form.Item>

          <Space style={{ marginTop: -12, marginBottom: 16 }}>
            <Button
              icon={<SearchOutlined />}
              loading={erpFieldsLoading}
              onClick={handleParseErpFields}
            >
              分析 SQL 字段
            </Button>
            <Button
              icon={<PlayCircleOutlined />}
              loading={testingInModal}
              onClick={handleTestInModal}
            >
              测试
            </Button>
          </Space>

          {/* ---- 字段映射面板 ---- */}
          <Divider style={{ margin: '8px 0 16px' }}>
            <SwapOutlined /> 字段映射
          </Divider>

          {mappingRows.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="点击「分析 SQL 字段」提取 ERP 字段，或编辑已有配置时自动加载"
              style={{ margin: '8px 0 16px' }}
            />
          ) : (
            <>
              <div className="flex justify-between items-center" style={{ marginBottom: 8 }}>
                <span style={{ fontSize: 12, color: '#64748b' }}>
                  共 {mappingRows.length} 个 ERP 字段，已映射 {mappingRows.filter(r => r.spc_field).length} 个
                </span>
                <Tooltip title="使用 AI 分析 SQL 语义，自动匹配 ERP 字段到 SPC 字段并生成备注">
                  <Button
                    size="small"
                    icon={<ThunderboltOutlined />}
                    onClick={handleAutoMatch}
                    loading={aiMatching}
                  >
                    {aiMatching ? 'AI 分析中...' : '自动匹配'}
                  </Button>
                </Tooltip>
              </div>

              <div
                style={{
                  border: '1px solid #f0f0f0',
                  borderRadius: 8,
                  maxHeight: 320,
                  overflowY: 'auto',
                }}
              >
                {/* 表头 */}
                <div
                  style={{
                    display: 'flex', alignItems: 'center', padding: '8px 12px',
                    background: '#fafafa', fontWeight: 600, fontSize: 12,
                    borderBottom: '1px solid #f0f0f0', position: 'sticky', top: 0, zIndex: 1,
                  }}
                >
                  <span style={{ flex: 1 }}>ERP 字段</span>
                  <span style={{ width: 40, textAlign: 'center' }}>→</span>
                  <span style={{ flex: 1 }}>SPC 字段</span>
                  <span style={{ flex: 1 }}>备注</span>
                  <span style={{ width: 40 }} />
                </div>

                {/* 映射行 */}
                {mappingRows.map((row, idx) => (
                  <div
                    key={row.erp_field}
                    style={{
                      display: 'flex', alignItems: 'center', padding: '6px 12px',
                      borderBottom: idx < mappingRows.length - 1 ? '1px solid #f5f5f5' : undefined,
                      background: row.spc_field ? '#f0fdf4' : undefined,
                    }}
                  >
                    <code style={{ flex: 1, fontSize: 12, color: '#334155' }}>
                      {row.erp_field}
                    </code>
                    <span style={{ width: 40, textAlign: 'center', color: '#94a3b8' }}>→</span>
                    <div style={{ flex: 1 }}>
                      <Select
                        size="small"
                        allowClear
                        showSearch
                        placeholder="选择 SPC 字段"
                        value={row.spc_field}
                        onChange={(val) => updateMappingSpc(idx, val || null)}
                        loading={spcFieldsLoading}
                        style={{ width: '100%' }}
                        optionFilterProp="label"
                        options={spcFields.map(f => ({
                          value: f.name,
                          label: f.name,
                          disabled: usedSpcFields.has(f.name) && f.name !== row.spc_field,
                        }))}
                        optionRender={(option) => (
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
                            <span>{option.label}</span>
                            <span style={{ color: '#94a3b8', fontSize: 11 }}>
                              {spcFields.find(f => f.name === option.value)?.type}
                            </span>
                          </div>
                        )}
                      />
                    </div>
                    <div style={{ flex: 1, paddingLeft: 8 }}>
                      <Input
                        size="small"
                        placeholder="字段备注"
                        value={row.remark}
                        onChange={(e) => updateMappingRemark(idx, e.target.value)}
                        style={{ width: '100%' }}
                      />
                    </div>
                    <Tooltip title="移除此映射行">
                      <Button
                        type="text"
                        size="small"
                        icon={<MinusCircleOutlined />}
                        onClick={() => removeMappingRow(idx)}
                        style={{ width: 40, color: '#94a3b8' }}
                      />
                    </Tooltip>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* 隐藏字段，保持表单完整性 */}
          <Form.Item name="field_mapping_json" hidden>
            <Input />
          </Form.Item>

          {/* ---- 条件参数面板 ---- */}
          <Divider style={{ margin: '16px 0' }}>
            <SwapOutlined /> 条件参数配置
          </Divider>
          <Alert
            message="条件参数说明"
            description="在SQL中使用 :parameter_name 作为参数占位符，同步时可根据需要传入参数值"
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
          />
          <div className="flex justify-between items-center" style={{ marginBottom: 8 }}>
            <span style={{ fontSize: 12, color: '#64748b' }}>
              共 {conditionParams.length} 个条件参数
            </span>
            <Button size="small" icon={<PlusOutlined />} onClick={addConditionParam}>
              添加条件参数
            </Button>
          </div>

          {conditionParams.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无条件参数，点击「添加条件参数」添加"
              style={{ margin: '8px 0 16px' }}
            />
          ) : (
            <div
              style={{
                border: '1px solid #f0f0f0',
                borderRadius: 8,
                maxHeight: 400,
                overflowY: 'auto',
              }}
            >
              {conditionParams.map((param, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: 12,
                    borderBottom: idx < conditionParams.length - 1 ? '1px solid #f5f5f5' : undefined,
                    background: '#fafafa',
                  }}
                >
                  <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                    <Form.Item
                      label="参数名"
                      style={{ flex: 1, marginBottom: 0 }}
                      required
                    >
                      <Input
                        size="small"
                        placeholder="如: customer_code"
                        value={param.parameter_name}
                        onChange={(e) => updateConditionParam(idx, 'parameter_name', e.target.value)}
                      />
                    </Form.Item>
                    <Form.Item
                      label="参数类型"
                      style={{ width: 120, marginBottom: 0 }}
                      required
                    >
                      <Select
                        size="small"
                        value={param.parameter_type}
                        onChange={(val) => updateConditionParam(idx, 'parameter_type', val)}
                        options={[
                          { value: 'string', label: '字符串' },
                          { value: 'number', label: '数字' },
                          { value: 'date', label: '日期' },
                          { value: 'list', label: '列表' },
                          { value: 'boolean', label: '布尔' },
                        ]}
                      />
                    </Form.Item>
                  </div>
                  <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                    <Form.Item
                      label="显示标签"
                      style={{ flex: 1, marginBottom: 0 }}
                      required
                    >
                      <Input
                        size="small"
                        placeholder="如: 客户代码"
                        value={param.label}
                        onChange={(e) => updateConditionParam(idx, 'label', e.target.value)}
                      />
                    </Form.Item>
                    <Form.Item
                      label="必填"
                      style={{ width: 80, marginBottom: 0 }}
                    >
                      <Switch
                        size="small"
                        checked={param.required}
                        onChange={(val) => updateConditionParam(idx, 'required', val)}
                      />
                    </Form.Item>
                  </div>
                  <div style={{ marginBottom: 8 }}>
                    <Form.Item label="默认值" style={{ marginBottom: 0 }}>
                      <Input
                        size="small"
                        placeholder="可选"
                        value={param.default_value}
                        onChange={(e) => updateConditionParam(idx, 'default_value', e.target.value)}
                      />
                    </Form.Item>
                  </div>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                    <Form.Item label="描述" style={{ flex: 1, marginBottom: 0 }}>
                      <Input.TextArea
                        size="small"
                        rows={2}
                        placeholder="参数说明"
                        value={param.description}
                        onChange={(e) => updateConditionParam(idx, 'description', e.target.value)}
                      />
                    </Form.Item>
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                      onClick={() => removeConditionParam(idx)}
                      style={{ marginTop: 24 }}
                    >
                      删除
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Form>
      </Modal>
    </div>
  )
}
