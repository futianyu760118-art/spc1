import { useCallback, useEffect, useState } from 'react'
import {
  Alert, Button, Card, Col, DatePicker, Drawer, Empty, Form, Input, InputNumber, Row, Select, Space, Switch,
  Table, Tabs, Tag, Typography, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { ReactNode } from 'react'
import { EditOutlined, PlusOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import api from '@/services/api'
import { useAuthStore } from '@/store/auth'

interface PageData<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

interface ParameterRow {
  id: number
  material_id: number
  material_code: string | null
  material_name: string | null
  purchase_lead_time_days: number | null
  purchase_variable_lead_time_days: number | null
  purchase_variable_lead_time_batch: number | null
  inspection_lead_time_days: number | null
  produce_lead_time_days: number | null
  subcontract_lead_time_days: number | null
  safety_stock: number
  max_stock: number | null
  moq: number | null
  batch_policy: string
  batch_qty: number | null
  default_supplier_id: number | null
  data_source: string
  remark: string | null
}

interface ParameterFormValues {
  material_id?: number | null
  material_code?: string | null
  purchase_lead_time_days?: number | null
  purchase_variable_lead_time_days?: number | null
  purchase_variable_lead_time_batch?: number | null
  inspection_lead_time_days?: number | null
  produce_lead_time_days?: number | null
  subcontract_lead_time_days?: number | null
  safety_stock: number
  max_stock?: number | null
  moq?: number | null
  batch_policy: string
  batch_qty?: number | null
  default_supplier_id?: number | null
  remark?: string | null
}

interface SchemeRow {
  id: number
  scheme_code: string
  scheme_name: string
  horizon_days: number
  consider_inventory: boolean
  consider_po: boolean
  consider_task: boolean
  consider_subcontract: boolean
  consider_transfer: boolean
  consider_requisition: boolean
  consider_safety_stock: boolean
  supply_priority: string
  exception_enabled: boolean
  exception_grace_days: number
  compare_window_days: number
  compare_qty_threshold_pct: number
  is_default: boolean
  is_active: boolean
  remark: string | null
}

type SchemeSwitchField =
  | 'consider_inventory'
  | 'consider_po'
  | 'consider_task'
  | 'consider_subcontract'
  | 'consider_transfer'
  | 'consider_requisition'
  | 'consider_safety_stock'

interface SchemeFormValues {
  scheme_name: string
  horizon_days: number
  consider_inventory: boolean
  consider_po: boolean
  consider_task: boolean
  consider_subcontract: boolean
  consider_transfer: boolean
  consider_requisition: boolean
  consider_safety_stock: boolean
  supply_priority: 'by_date' | 'by_type'
  exception_grace_days: number
  compare_window_days: number
  compare_qty_threshold_pct: number
  remark?: string | null
}

interface SubstituteRow {
  id: number
  main_material_id: number
  substitute_material_id: number
  main_material_code: string | null
  main_material_name: string | null
  substitute_material_code: string | null
  substitute_material_name: string | null
  priority: number
  policy: string
  ratio: number | null
  substitute_mode: string
  valid_from: string | null
  valid_to: string | null
  enabled: boolean
  remark: string | null
}

interface SubstituteFormValues {
  main_material_code?: string | null
  substitute_material_code?: string | null
  priority: number
  policy: 'priority' | 'ratio'
  ratio?: number | null
  substitute_mode: 'offset' | 'replace'
  valid_from?: Dayjs | null
  valid_to?: Dayjs | null
  enabled: boolean
  remark?: string | null
}

const BATCH_POLICY_MAP: Record<string, { label: string; cls: string }> = {
  lot_for_lot: { label: '按需', cls: 'sc-tag-wait' },
  multiple: { label: '倍数', cls: 'sc-tag-prod' },
  fixed: { label: '固定', cls: 'sc-tag-purple' },
}

const DATA_SOURCE_MAP: Record<string, { label: string; color: string }> = {
  manual: { label: '手工', color: 'green' },
  excel: { label: 'Excel', color: 'cyan' },
  erp: { label: 'ERP', color: 'geekblue' },
}

const SUBSTITUTE_POLICY_MAP: Record<string, { label: string; cls: string }> = {
  priority: { label: '按优先级', cls: 'sc-tag-kit' },
  ratio: { label: '按比例', cls: 'sc-tag-purple' },
}

const SUBSTITUTE_MODE_MAP: Record<string, { label: string; cls: string }> = {
  offset: { label: '抵扣', cls: 'sc-tag-kit' },
  replace: { label: '替换', cls: 'sc-tag-purple' },
}

const SCHEME_SWITCH_FIELDS: Array<{ name: SchemeSwitchField; label: string; tooltip?: string }> = [
  { name: 'consider_inventory', label: '库存参与供给' },
  { name: 'consider_po', label: '采购订单参与供给' },
  { name: 'consider_task', label: '生产任务单参与供给' },
  { name: 'consider_subcontract', label: '委外订单参与供给' },
  { name: 'consider_transfer', label: '调拨在途参与供给' },
  { name: 'consider_requisition', label: '采购申请参与供给（P2 生效）' },
  { name: 'consider_safety_stock', label: '安全库存参与净算', tooltip: '关闭后仅为订单需求净算，不生成安全库存补货建议。' },
]

function fmtQty(v: number | null | undefined): string {
  if (v == null) return '-'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

function renderLeadTime(v: number | null): ReactNode {
  return v != null
    ? fmtQty(v)
    : <span style={{ color: '#cbd5e1' }} title="未单独配置：按默认 7 天提前期参与运算">默认</span>
}

function renderOptionalNumber(v: number | null): ReactNode {
  return v != null ? fmtQty(v) : <span style={{ color: '#cbd5e1' }}>-</span>
}

function fmtMaterialLabel(code: string | null, name: string | null, id: number): string {
  return code || name ? `${name || ''}（${code || ''}）` : `物料 ID ${id}`
}

function fmtValidity(row: SubstituteRow): ReactNode {
  const { valid_from: from, valid_to: to } = row
  if (!from && !to) return <span className="sc-tag sc-tag-wait">长期</span>
  if (from && to) return <span className="sc-mono">{from} ~ {to}</span>
  if (from) return <span className="sc-mono">{from} 起</span>
  return <span className="sc-mono">至 {to}</span>
}

function MaterialParameterPane({ canParam }: { canParam: boolean }) {
  const [data, setData] = useState<ParameterRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingMaterialId, setEditingMaterialId] = useState<number | null>(null)
  const [editingMaterialLabel, setEditingMaterialLabel] = useState('')
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<ParameterFormValues>()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = (await api.get('/mrp/parameters', {
        params: { keyword, page, page_size: pageSize },
      })) as unknown as ApiResponse<PageData<ParameterRow>>
      setData(res.data.items || [])
      setTotal(res.data.total || 0)
    } catch {
      // 全局拦截器已提示
    } finally {
      setLoading(false)
    }
  }, [keyword, page, pageSize])

  useEffect(() => { load() }, [load])

  const openCreate = () => {
    setEditingMaterialId(null)
    setEditingMaterialLabel('')
    form.resetFields()
    form.setFieldsValue({ batch_policy: 'lot_for_lot', safety_stock: 0 })
    setDrawerOpen(true)
  }

  const openEdit = (row: ParameterRow) => {
    setEditingMaterialId(row.material_id)
    setEditingMaterialLabel(
      row.material_code || row.material_name
        ? `${row.material_name || ''}（${row.material_code || ''}）`
        : `物料 ID ${row.material_id}`,
    )
    form.setFieldsValue(row)
    setDrawerOpen(true)
  }

  const submit = async () => {
    const values = await form.validateFields()
    const payload: Record<string, unknown> = { ...values }
    if (editingMaterialId == null) {
      delete payload.material_id
    } else {
      payload.material_id = editingMaterialId
      delete payload.material_code
    }
    setSaving(true)
    try {
      await api.put('/mrp/parameters', payload)
      message.success('物料参数已保存')
      setDrawerOpen(false)
      await load()
    } catch {
      // 全局拦截器已提示
    } finally {
      setSaving(false)
    }
  }

  const columns: ColumnsType<ParameterRow> = [
    {
      title: '物料 ID', dataIndex: 'material_id', width: 100, fixed: 'left',
      render: (v: number) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    {
      title: '物料编码', dataIndex: 'material_code', width: 160, ellipsis: true,
      render: (v: string | null, row) => v || (
        <span style={{ color: '#cbd5e1', fontFamily: 'monospace', fontSize: 12 }}>#{row.material_id}</span>
      ),
    },
    {
      title: '物料名称', dataIndex: 'material_name', width: 180, ellipsis: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>—</span>,
    },
    { title: '外购提前期(天)', dataIndex: 'purchase_lead_time_days', width: 120, align: 'right', render: renderLeadTime },
    { title: '变动提前期(天)', dataIndex: 'purchase_variable_lead_time_days', width: 120, align: 'right', render: renderOptionalNumber },
    { title: '变动批量', dataIndex: 'purchase_variable_lead_time_batch', width: 100, align: 'right', render: renderOptionalNumber },
    { title: '检验提前期(天)', dataIndex: 'inspection_lead_time_days', width: 120, align: 'right', render: renderOptionalNumber },
    { title: '自制提前期(天)', dataIndex: 'produce_lead_time_days', width: 120, align: 'right', render: renderLeadTime },
    { title: '委外提前期(天)', dataIndex: 'subcontract_lead_time_days', width: 120, align: 'right', render: renderLeadTime },
    {
      title: '安全库存', dataIndex: 'safety_stock', width: 100, align: 'right',
      render: (v: number) => (v === 0 ? <span style={{ color: '#cbd5e1' }}>0</span> : fmtQty(v)),
    },
    { title: '最高存量', dataIndex: 'max_stock', width: 100, align: 'right', render: renderOptionalNumber },
    { title: 'MOQ', dataIndex: 'moq', width: 90, align: 'right', render: renderOptionalNumber },
    {
      title: '批量策略', dataIndex: 'batch_policy', width: 100,
      render: (v: string) => {
        const m = BATCH_POLICY_MAP[v] || { label: v, cls: 'sc-tag-plain' }
        return <span className={`sc-tag ${m.cls}`}>{m.label}</span>
      },
    },
    { title: '批量值', dataIndex: 'batch_qty', width: 100, align: 'right', render: renderOptionalNumber },
    { title: '默认供应商', dataIndex: 'default_supplier_id', width: 100, align: 'right', render: renderOptionalNumber },
    {
      title: '数据来源', dataIndex: 'data_source', width: 90,
      render: (v: string) => {
        const m = DATA_SOURCE_MAP[v] || { label: v, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '备注', dataIndex: 'remark', width: 160, ellipsis: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    ...(canParam ? [{
      title: '操作', width: 80, fixed: 'right' as const,
      render: (_: unknown, row: ParameterRow) => (
        <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(row)}>编辑</Button>
      ),
    }] : []),
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input.Search
              placeholder="物料编码/名称关键字"
              style={{ width: 240 }}
              allowClear
              onSearch={(v) => { setKeyword(v.trim()); setPage(1) }}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={() => load()} loading={loading}>刷新</Button>
              {canParam && <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增/编辑</Button>}
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table<ParameterRow>
          rowKey="id"
          dataSource={data}
          columns={columns}
          loading={loading}
          size="small"
          scroll={{ x: 1940 }}
          pagination={{
            total, current: page, pageSize,
            showSizeChanger: true, showTotal: (t) => `共 ${t} 条`,
          }}
          onChange={(pagination) => {
            setPage(pagination.current || 1)
            setPageSize(pagination.pageSize || 20)
          }}
        />
      </div>

      <Drawer
        title={editingMaterialId == null ? '新增物料参数' : `编辑物料参数（${editingMaterialLabel}）`}
        width={560}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
        footer={(
          <Space style={{ float: 'right' }}>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={submit}>保存</Button>
          </Space>
        )}
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              {editingMaterialId == null ? (
                <Form.Item
                  name="material_code"
                  label="物料编码"
                  tooltip="按编码精确匹配物料主数据，保存后自动关联 erp_material_id"
                  rules={[{ required: true, message: '请输入物料编码' }]}
                >
                  <Input placeholder="如 1.3.1.HJ-5110-03-001" allowClear />
                </Form.Item>
              ) : (
                <Form.Item label="物料" tooltip="编辑时不可更换物料">
                  <Input disabled value={editingMaterialLabel} />
                </Form.Item>
              )}
            </Col>
            <Col span={12}>
              <Form.Item name="safety_stock" label="安全库存" rules={[{ required: true, message: '请输入安全库存' }]}>
                <InputNumber style={{ width: '100%' }} min={0} precision={4} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="purchase_lead_time_days" label="外购固定提前期(天)">
                <InputNumber style={{ width: '100%' }} min={0} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="purchase_variable_lead_time_days" label="外购变动提前期(天)">
                <InputNumber style={{ width: '100%' }} min={0} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="purchase_variable_lead_time_batch" label="变动提前期批量">
                <InputNumber style={{ width: '100%' }} min={0} precision={4} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="inspection_lead_time_days" label="检验提前期(天)">
                <InputNumber style={{ width: '100%' }} min={0} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="produce_lead_time_days" label="自制提前期(天)">
                <InputNumber style={{ width: '100%' }} min={0} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="subcontract_lead_time_days" label="委外提前期(天)">
                <InputNumber style={{ width: '100%' }} min={0} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="max_stock" label="最高存量">
                <InputNumber style={{ width: '100%' }} min={0} precision={4} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="moq" label="最小起订量 MOQ">
                <InputNumber style={{ width: '100%' }} min={0} precision={4} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="batch_policy" label="批量策略" rules={[{ required: true }]}>
                <Select
                  options={[
                    { value: 'lot_for_lot', label: '按需（lot_for_lot）' },
                    { value: 'multiple', label: '固定倍数（multiple）' },
                    { value: 'fixed', label: '固定批量（fixed）' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="batch_qty" label="批量值（multiple/fixed 生效）">
                <InputNumber style={{ width: '100%' }} min={0} precision={4} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="default_supplier_id" label="默认供应商 ID" tooltip="引用 scm_supplier.id">
                <InputNumber style={{ width: '100%' }} min={1} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="remark" label="备注">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Drawer>
    </div>
  )
}

function SchemePane({ canParam }: { canParam: boolean }) {
  const [scheme, setScheme] = useState<SchemeRow | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<SchemeFormValues>()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = (await api.get('/mrp/schemes')) as unknown as ApiResponse<SchemeRow[]>
      const rows = res.data || []
      const current = rows.find((r) => r.is_default) || rows[0] || null
      setScheme(current)
      if (current) {
        form.setFieldsValue({
          scheme_name: current.scheme_name,
          horizon_days: current.horizon_days,
          consider_inventory: current.consider_inventory,
          consider_po: current.consider_po,
          consider_task: current.consider_task,
          consider_subcontract: current.consider_subcontract,
          consider_transfer: current.consider_transfer,
          consider_requisition: current.consider_requisition,
          consider_safety_stock: current.consider_safety_stock,
          supply_priority: current.supply_priority === 'by_type' ? 'by_type' : 'by_date',
          exception_grace_days: current.exception_grace_days,
          compare_window_days: current.compare_window_days,
          compare_qty_threshold_pct: current.compare_qty_threshold_pct,
          remark: current.remark,
        })
      }
    } catch {
      // 全局拦截器已提示
    } finally {
      setLoading(false)
    }
  }, [form])

  useEffect(() => { load() }, [load])

  const submit = async () => {
    if (!scheme) return
    const values = await form.validateFields()
    setSaving(true)
    try {
      await api.put(`/mrp/schemes/${scheme.id}`, values)
      message.success('计划方案已保存')
      await load()
    } catch {
      // 全局拦截器已提示
    } finally {
      setSaving(false)
    }
  }

  if (!loading && !scheme) {
    return (
      <Card className="card-modern">
        <Empty description="计划方案不存在" />
      </Card>
    )
  }

  return (
    <Card
      className="card-modern"
      title={scheme ? `${scheme.scheme_name}（${scheme.scheme_code}）` : '计划方案'}
      extra={(
        <Space>
          <span className="sc-note">变更下次运算生效；每次运行会保存参数快照。</span>
          {!canParam && <Typography.Text type="secondary">无参数维护权限，只读</Typography.Text>}
          <Button icon={<ReloadOutlined />} onClick={() => load()} loading={loading}>刷新</Button>
          <Button type="primary" icon={<SaveOutlined />} loading={saving} disabled={!canParam || !scheme} onClick={submit}>
            保存
          </Button>
        </Space>
      )}
    >
      <Form form={form} layout="vertical" disabled={!canParam}>
        <Row gutter={16}>
          <Col span={8}>
            <Form.Item name="scheme_name" label="方案名称" rules={[{ required: true, message: '请输入方案名称' }]}>
              <Input />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item
              name="horizon_days"
              label="计划展望期(天)"
              tooltip="只净算展望期内的需求；期外订单留待后续批次。"
              rules={[{ required: true, message: '请输入展望期' }]}
            >
              <InputNumber style={{ width: '100%' }} min={1} max={365} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item
              name="supply_priority"
              label="供给优先顺序"
              tooltip="「按日期」＝可用日早的先抵扣；「按单据类型」＝库存 → 在途 → 任务。"
              rules={[{ required: true }]}
            >
              <Select
                options={[
                  { value: 'by_date', label: '按日期（by_date）' },
                  { value: 'by_type', label: '按类型（by_type）' },
                ]}
              />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          {SCHEME_SWITCH_FIELDS.map((field) => (
            <Col span={8} key={field.name}>
              <Form.Item name={field.name} label={field.label} tooltip={field.tooltip} valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
          ))}
        </Row>
        <div className="sc-note" style={{ marginBottom: 16 }}>关闭的来源不参与净算（如关闭「调拨」＝调拨单不充抵缺口）。</div>
        <Row gutter={16}>
          <Col span={8}>
            <Form.Item name="exception_grace_days" label="例外宽限期(天)" tooltip="拖期在宽限期内不生成例外提醒（0 = 不提醒，P2 生效）">
              <InputNumber style={{ width: '100%' }} min={0} max={90} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="compare_window_days" label="K3 对比日期窗口(天)" tooltip="与 K3 对比时，需求日 ±N 天视为同一项。">
              <InputNumber style={{ width: '100%' }} min={0} max={30} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item name="compare_qty_threshold_pct" label="K3 对比量差阈值(%)" tooltip="数量差 ≤N% 记为 match（批次与对比同口径）。">
              <InputNumber style={{ width: '100%' }} min={0} max={100} precision={2} />
            </Form.Item>
          </Col>
          <Col span={24}>
            <Form.Item name="remark" label="备注">
              <Input.TextArea rows={2} />
            </Form.Item>
          </Col>
        </Row>
      </Form>
    </Card>
  )
}

function SubstitutePane({ canParam }: { canParam: boolean }) {
  const [data, setData] = useState<SubstituteRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editingRow, setEditingRow] = useState<SubstituteRow | null>(null)
  const [saving, setSaving] = useState(false)
  const [form] = Form.useForm<SubstituteFormValues>()
  const policy = Form.useWatch('policy', form)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = (await api.get('/mrp/substitutes', {
        params: { keyword, page, page_size: pageSize },
      })) as unknown as ApiResponse<PageData<SubstituteRow>>
      setData(res.data.items || [])
      setTotal(res.data.total || 0)
    } catch {
      // 全局拦截器已提示
    } finally {
      setLoading(false)
    }
  }, [keyword, page, pageSize])

  useEffect(() => { load() }, [load])

  const openCreate = () => {
    setEditingRow(null)
    form.resetFields()
    form.setFieldsValue({ priority: 1, policy: 'priority', substitute_mode: 'offset', enabled: true })
    setDrawerOpen(true)
  }

  const openEdit = (row: SubstituteRow) => {
    setEditingRow(row)
    form.setFieldsValue({
      priority: row.priority,
      policy: row.policy === 'ratio' ? 'ratio' : 'priority',
      ratio: row.ratio,
      substitute_mode: row.substitute_mode === 'replace' ? 'replace' : 'offset',
      valid_from: row.valid_from ? dayjs(row.valid_from) : null,
      valid_to: row.valid_to ? dayjs(row.valid_to) : null,
      enabled: row.enabled,
      remark: row.remark,
    })
    setDrawerOpen(true)
  }

  const submit = async () => {
    const values = await form.validateFields()
    const payload: Record<string, unknown> = {
      priority: values.priority,
      policy: values.policy,
      ratio: values.policy === 'ratio' ? values.ratio : null,
      substitute_mode: values.substitute_mode,
      valid_from: values.valid_from ? dayjs(values.valid_from).format('YYYY-MM-DD') : null,
      valid_to: values.valid_to ? dayjs(values.valid_to).format('YYYY-MM-DD') : null,
      enabled: values.enabled,
      remark: values.remark || null,
    }
    if (editingRow == null) {
      payload.main_material_code = (values.main_material_code || '').trim()
      payload.substitute_material_code = (values.substitute_material_code || '').trim()
    } else {
      payload.main_material_id = editingRow.main_material_id
      payload.substitute_material_id = editingRow.substitute_material_id
    }
    setSaving(true)
    try {
      await api.put('/mrp/substitutes', payload, { skipErrorToast: true })
      message.success('替代规则已保存')
      setDrawerOpen(false)
      await load()
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
        || (error as Error)?.message
        || '保存失败'
      message.error(detail)
    } finally {
      setSaving(false)
    }
  }

  const columns: ColumnsType<SubstituteRow> = [
    {
      title: '主料编码', dataIndex: 'main_material_code', width: 180, ellipsis: true,
      render: (v: string | null, row) => v || (
        <span style={{ color: '#cbd5e1', fontFamily: 'monospace', fontSize: 12 }}>#{row.main_material_id}</span>
      ),
    },
    {
      title: '主料名称', dataIndex: 'main_material_name', width: 160, ellipsis: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>—</span>,
    },
    {
      title: '替代料编码', dataIndex: 'substitute_material_code', width: 180, ellipsis: true,
      render: (v: string | null, row) => v || (
        <span style={{ color: '#cbd5e1', fontFamily: 'monospace', fontSize: 12 }}>#{row.substitute_material_id}</span>
      ),
    },
    {
      title: '替代料名称', dataIndex: 'substitute_material_name', width: 160, ellipsis: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>—</span>,
    },
    { title: '优先级', dataIndex: 'priority', width: 80, align: 'right' },
    {
      title: '策略', dataIndex: 'policy', width: 96,
      render: (v: string) => {
        const m = SUBSTITUTE_POLICY_MAP[v] || { label: v, cls: 'sc-tag-plain' }
        return (
          <div>
            <span className={`sc-tag ${m.cls}`}>{v}</span>
            <div className="sc-sub">{m.label}</div>
          </div>
        )
      },
    },
    {
      title: '比例', dataIndex: 'ratio', width: 90, align: 'right',
      render: (v: number | null, row) => (row.policy === 'ratio' && v != null ? `${fmtQty(v)}%` : '-'),
    },
    {
      title: '模式', dataIndex: 'substitute_mode', width: 96,
      render: (v: string) => {
        const m = SUBSTITUTE_MODE_MAP[v] || { label: v, cls: 'sc-tag-plain' }
        return (
          <div>
            <span className={`sc-tag ${m.cls}`}>{m.label}</span>
            <div className="sc-sub">{v}</div>
          </div>
        )
      },
    },
    { title: '生效期', width: 200, render: (_: unknown, row) => fmtValidity(row) },
    {
      title: '启用', dataIndex: 'enabled', width: 70,
      render: (v: boolean) => <span className={`sc-tag ${v ? 'sc-tag-done' : 'sc-tag-wait'}`}>{v ? '启用' : '停用'}</span>,
    },
    {
      title: '备注', dataIndex: 'remark', width: 160, ellipsis: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    ...(canParam ? [{
      title: '操作', width: 80, fixed: 'right' as const,
      render: (_: unknown, row: SubstituteRow) => (
        <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(row)}>编辑</Button>
      ),
    }] : []),
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input.Search
              placeholder="主料/替代料编码或名称关键字"
              style={{ width: 260 }}
              allowClear
              onSearch={(v) => { setKeyword(v.trim()); setPage(1) }}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={() => load()} loading={loading}>刷新</Button>
              {canParam && <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增</Button>}
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table<SubstituteRow>
          rowKey="id"
          dataSource={data}
          columns={columns}
          loading={loading}
          size="small"
          scroll={{ x: 1440 }}
          pagination={{
            total, current: page, pageSize,
            showSizeChanger: true, showTotal: (t) => `共 ${t} 条`,
          }}
          onChange={(pagination) => {
            setPage(pagination.current || 1)
            setPageSize(pagination.pageSize || 20)
          }}
        />
      </div>

      <div className="sc-note" style={{ marginTop: 12, padding: '9px 13px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: 9, lineHeight: 1.75 }}>
        注：替代抵扣后，替代料自身后续需求由常规净算补货（已声明简化）；<code>replace</code> 模式仅对外购替代料生效。
      </div>

      <Drawer
        title={editingRow == null
          ? '新增替代规则'
          : `编辑替代规则（${editingRow.main_material_code || editingRow.main_material_id} → ${editingRow.substitute_material_code || editingRow.substitute_material_id}）`}
        width={560}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
        footer={(
          <Space style={{ float: 'right' }}>
            <Button onClick={() => setDrawerOpen(false)}>取消</Button>
            <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={submit}>保存</Button>
          </Space>
        )}
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              {editingRow == null ? (
                <Form.Item
                  name="main_material_code"
                  label="主料编码"
                  tooltip="按编码精确匹配物料主数据，保存后自动关联 erp_material_id"
                  rules={[{ required: true, message: '请输入主料编码' }]}
                >
                  <Input placeholder="如 1.3.1.HJ-5110-03-001" allowClear />
                </Form.Item>
              ) : (
                <Form.Item label="主料" tooltip="编辑时不可更换主料/替代料">
                  <Input
                    disabled
                    value={fmtMaterialLabel(
                      editingRow.main_material_code,
                      editingRow.main_material_name,
                      editingRow.main_material_id,
                    )}
                  />
                </Form.Item>
              )}
            </Col>
            <Col span={12}>
              {editingRow == null ? (
                <Form.Item
                  name="substitute_material_code"
                  label="替代料编码"
                  tooltip="按编码精确匹配物料主数据，保存后自动关联 erp_material_id"
                  rules={[{ required: true, message: '请输入替代料编码' }]}
                >
                  <Input placeholder="如 1.3.1.HJ-5110-03-001" allowClear />
                </Form.Item>
              ) : (
                <Form.Item label="替代料" tooltip="编辑时不可更换主料/替代料">
                  <Input
                    disabled
                    value={fmtMaterialLabel(
                      editingRow.substitute_material_code,
                      editingRow.substitute_material_name,
                      editingRow.substitute_material_id,
                    )}
                  />
                </Form.Item>
              )}
            </Col>
            <Col span={12}>
              <Form.Item name="priority" label="优先级" tooltip="数值小者优先" rules={[{ required: true, message: '请输入优先级' }]}>
                <InputNumber style={{ width: '100%' }} min={1} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="policy" label="策略" rules={[{ required: true }]}>
                <Select
                  options={[
                    { value: 'priority', label: '按优先级（priority）' },
                    { value: 'ratio', label: '按比例（ratio）' },
                  ]}
                />
              </Form.Item>
            </Col>
            {policy === 'ratio' && (
              <Col span={12}>
                <Form.Item name="ratio" label="比例(%)" tooltip="同主料下合计 100" rules={[{ required: true, message: '请输入比例' }]}>
                  <InputNumber style={{ width: '100%' }} min={0.0001} max={100} precision={4} />
                </Form.Item>
              </Col>
            )}
            <Col span={12}>
              <Form.Item name="substitute_mode" label="模式" rules={[{ required: true }]}>
                <Select
                  options={[
                    { value: 'offset', label: '抵扣余额（offset）' },
                    { value: 'replace', label: '缺口改落替代料（replace）' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="valid_from" label="生效日期">
                <DatePicker style={{ width: '100%' }} placeholder="不填则立即生效" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="valid_to" label="失效日期">
                <DatePicker style={{ width: '100%' }} placeholder="不填则长期有效" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="enabled" label="启用" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="remark" label="备注">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Drawer>
    </div>
  )
}

export default function ParametersTab() {
  const hasPermission = useAuthStore((s) => s.hasPermission) as (resource: string, action: string) => boolean
  const canParam = hasPermission('materials.mrp', 'param')

  return (
    <div>
      <Alert
        type="info"
        showIcon
        message={<><b>怎么看：</b>给引擎喂参数：提前期、安全库存、起订量、批量策略（未配置按默认 7 天）。替代规则＝主料缺口时先消耗替代料余额。</>}
        style={{ marginBottom: 16 }}
      />
      <Tabs
        items={[
          { key: 'parameters', label: '物料参数', children: <MaterialParameterPane canParam={canParam} /> },
          { key: 'scheme', label: '计划方案', children: <SchemePane canParam={canParam} /> },
          { key: 'substitutes', label: '替代规则', children: <SubstitutePane canParam={canParam} /> },
        ]}
      />
    </div>
  )
}
