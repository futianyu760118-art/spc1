import { useCallback, useEffect, useState } from 'react'
import { Button, Col, DatePicker, Form, Input, InputNumber, Modal, Popconfirm, Row, Select, Space, Table, Tabs, Tag, Tooltip, message } from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined, SearchOutlined, ThunderboltOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { productionApi, orderApi } from '../../../services/api'
import { formatDate } from '../../../utils'

const DEPARTMENTS = ['计划', '采购', '生产', '品质', '仓储']

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  planned: { label: '已计划', color: 'blue' },
  in_progress: { label: '执行中', color: 'processing' },
  completed: { label: '已完成', color: 'success' },
  delayed: { label: '延期', color: 'warning' },
  cancelled: { label: '已取消', color: 'default' },
}

const PRIORITY_MAP: Record<string, { label: string; color: string }> = {
  low: { label: '低', color: 'default' },
  normal: { label: '普通', color: 'blue' },
  high: { label: '高', color: 'orange' },
  urgent: { label: '紧急', color: 'red' },
}

const RISK_MAP: Record<string, { label: string; color: string }> = {
  red: { label: '红色', color: 'red' },
  yellow: { label: '黄色', color: 'gold' },
  blue: { label: '蓝色', color: 'blue' },
  green: { label: '绿色', color: 'green' },
}

export default function SchedulePlans() {
  const [activeTab, setActiveTab] = useState('orders')
  const [department, setDepartment] = useState(DEPARTMENTS[0])
  const [data, setData] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState<string | undefined>()
  const [dateRange, setDateRange] = useState<[string, string] | null>(null)
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [scheduleModalOpen, setScheduleModalOpen] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [selectedOrder, setSelectedOrder] = useState<any>(null)
  const [form] = Form.useForm()
  const [scheduleForm] = Form.useForm()
  const [year, setYear] = useState(dayjs().year())
  const [month, setMonth] = useState(dayjs().month() + 1)
  const [riskLevel, setRiskLevel] = useState<string | undefined>()
  const [onlyUnscheduled, setOnlyUnscheduled] = useState(false)
  const [orderData, setOrderData] = useState<any[]>([])
  const [orderTotal, setOrderTotal] = useState(0)
  const [orderPage, setOrderPage] = useState(1)
  const [workHours, setWorkHours] = useState(8)

  const loadPlans = useCallback(async () => {
    if (!['active_plans', 'reschedule_needed', 'history_plans'].includes(activeTab)) return
    setLoading(true)
    try {
      const params: Record<string, any> = { page, page_size: pageSize, department }
      if (keyword.trim()) params.keyword = keyword.trim()
      if (status) params.status = status
      if (dateRange) {
        params.date_start = dateRange[0]
        params.date_end = dateRange[1]
      }
      
      if (activeTab === 'active_plans') {
        params.is_active = true
        params.needs_reschedule = false
      } else if (activeTab === 'reschedule_needed') {
        params.is_active = true
        params.needs_reschedule = true
      } else if (activeTab === 'history_plans') {
        params.is_active = false
      }

      const res: any = await productionApi.listSchedulePlans(params)
      setData(res.data.items || [])
      setTotal(res.data.total || 0)
    } catch (e: any) {
      message.error(e.message || '获取计划排产失败')
    } finally {
      setLoading(false)
    }
  }, [activeTab, dateRange, department, keyword, page, pageSize, status])

  const loadOrders = useCallback(async () => {
    if (activeTab !== 'orders') return
    setLoading(true)
    try {
      const params: Record<string, any> = {
        page: orderPage,
        page_size: pageSize,
        year,
        month,
        only_unscheduled: onlyUnscheduled,
      }
      if (keyword.trim()) params.keyword = keyword.trim()
      if (riskLevel) params.risk_level = riskLevel
      const res: any = await productionApi.getOrdersForScheduling(params)
      setOrderData(res.data.items || [])
      setOrderTotal(res.data.total || 0)
    } catch (e: any) {
      message.error(e.message || '获取订单列表失败')
    } finally {
      setLoading(false)
    }
  }, [activeTab, keyword, month, onlyUnscheduled, orderPage, pageSize, riskLevel, year])

  const loadWorkHours = useCallback(async () => {
    try {
      const res: any = await productionApi.getWorkHoursConfig()
      setWorkHours(res.data?.daily_work_hours || 8)
    } catch (e: any) {
      console.error('获取工作时间配置失败', e)
    }
  }, [])

  useEffect(() => {
    if (activeTab === 'orders') loadOrders()
    else loadPlans()
  }, [activeTab, loadOrders, loadPlans])

  useEffect(() => { loadWorkHours() }, [loadWorkHours])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ department, plan_date: dayjs(), priority: 'normal', status: 'planned', daily_work_hours: workHours })
    setModalOpen(true)
  }

  const openEdit = (row: any) => {
    setEditing(row)
    form.setFieldsValue({
      ...row,
      plan_date: row.plan_date ? dayjs(row.plan_date) : null,
      start_date: row.start_date ? dayjs(row.start_date) : null,
      end_date: row.end_date ? dayjs(row.end_date) : null,
    })
    setModalOpen(true)
  }

  const openSchedule = (row: any) => {
    setSelectedOrder(row)
    scheduleForm.resetFields()
    const upph = row.upph > 0 ? row.upph : undefined
    scheduleForm.setFieldsValue({
      order_no: row.order_no,
      line_no: row.line_no,
      product_code: row.product_code,
      model_code: row.product_model,
      quantity: row.order_qty,
      promised_date: row.promised_date ? dayjs(row.promised_date) : null,
      department: '生产',
      plan_date: dayjs(),
      upph,
      daily_work_hours: workHours,
    })
    setScheduleModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      const payload = {
        ...values,
        plan_date: values.plan_date ? values.plan_date.format('YYYY-MM-DD') : null,
        start_date: values.start_date ? values.start_date.format('YYYY-MM-DD') : null,
        end_date: values.end_date ? values.end_date.format('YYYY-MM-DD') : null,
      }
      if (editing) {
        await productionApi.updateSchedulePlan(editing.id, payload)
        message.success('更新成功')
      } else {
        await productionApi.createSchedulePlan(payload)
        message.success('创建成功')
      }
      setModalOpen(false)
      loadPlans()
    } catch (e: any) {
      if (!e?.errorFields) message.error(e.message || '保存失败')
    }
  }

  const handleAutoSchedule = async () => {
    try {
      const values = await scheduleForm.validateFields()
      const payload = {
        order_no: values.order_no,
        line_no: values.line_no,
        department: values.department,
        plan_date: values.plan_date ? values.plan_date.format('YYYY-MM-DD') : null,
        upph: values.upph,
        daily_work_hours: values.daily_work_hours,
        owner: values.owner,
      }
      const res: any = await productionApi.autoSchedule(payload)
      if (res.data?.success) {
        const result = res.data.calculation_result || {}
        message.success(res.data.message || '排产成功')
        if (result.total_hours) {
          message.info(`总工时: ${result.total_hours}小时, 需要: ${result.days_needed}天`)
        }
      }
      setScheduleModalOpen(false)
      loadOrders()
      if (['active_plans', 'reschedule_needed', 'history_plans'].includes(activeTab)) loadPlans()
    } catch (e: any) {
      message.error(e.message || '排产失败')
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await productionApi.deleteSchedulePlan(id)
      message.success('删除成功')
      loadPlans()
    } catch (e: any) {
      message.error(e.message || '删除失败')
    }
  }

  const handleDetectChanges = async () => {
    setLoading(true)
    try {
      const res: any = await productionApi.detectScheduleChanges()
      if (res.data && res.data.length > 0) {
        message.info(`检测到 ${res.data.length} 条订单行变更，已标记待重排。`)
      } else {
        message.info('未检测到订单行变更。')
      }
      loadPlans()
    } catch (e: any) {
      message.error(e.message || '检测变更失败')
    } finally {
      setLoading(false)
    }
  }

  const handleReschedule = async (id: number) => {
    setLoading(true)
    try {
      await productionApi.reschedulePlan(id)
      message.success('重排成功！')
      loadPlans()
    } catch (e: any) {
      message.error(e.message || '重排失败')
    } finally {
      setLoading(false)
    }
  }

  const planColumns = [
    { title: '订单号', dataIndex: 'order_no', width: 140, render: (v: string) => v || '-' },
    { title: '行号', dataIndex: 'line_no', width: 80, render: (v: string) => v || '-' },
    { title: '产品编码', dataIndex: 'product_code', width: 200, render: (v: string) => v || '-' },
    { title: '型号', dataIndex: 'model_code', width: 250, render: (v: string) => v || '-' },
    { title: '数量', dataIndex: 'quantity', width: 90, render: (v: number) => <span style={{ fontWeight: 'bold' }}>{v ?? '-'}</span> },
    { title: '计划开始', dataIndex: 'start_date', width: 110, render: (v: string) => <Tag color="blue">{formatDate(v)}</Tag> },
    { title: '计划结束', dataIndex: 'end_date', width: 110, render: (v: string, row: any) => {
        const isDelayed = row.remark && row.remark.includes('延期预警');
        return <Tag color={isDelayed ? 'red' : 'green'}>{formatDate(v)}</Tag>;
    }},
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (v: string) => <Tag color={STATUS_MAP[v]?.color || 'default'}>{STATUS_MAP[v]?.label || v}</Tag>,
    },
    {
      title: '优先级', dataIndex: 'priority', width: 90,
      render: (v: string) => <Tag color={PRIORITY_MAP[v]?.color || 'default'}>{PRIORITY_MAP[v]?.label || v}</Tag>,
    },
    { title: '负责人', dataIndex: 'owner', width: 100, render: (v: string) => v || '-' },
    {
      title: '需重排', dataIndex: 'needs_reschedule', width: 80,
      render: (v: boolean) => v ? <Tag color="red">是</Tag> : <Tag color="green">否</Tag>,
    },
    { title: '重排原因', dataIndex: 'reschedule_reason', width: 150, ellipsis: true, render: (v: string) => v || '-' },
    { title: '备注', dataIndex: 'remark', width: 200, ellipsis: true, render: (v: string) => {
        if (v && v.includes('延期预警')) {
            return <span style={{ color: 'red', fontWeight: 'bold' }}>{v}</span>;
        }
        return v || '-';
    }},
    {
      title: '操作', width: 100, fixed: 'right' as const,
      render: (_: any, row: any) => (
        <Space size={4}>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(row.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
          {row.needs_reschedule && (
            <Popconfirm title="确认重排？" onConfirm={() => handleReschedule(row.id)}>
              <Button size="small" icon={<ThunderboltOutlined />} type="primary">重排</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const orderColumns = [
    { title: '订单号', dataIndex: 'order_no', width: 140, fixed: 'left' as const },
    { title: '行号', dataIndex: 'line_no', width: 80 },
    { title: '客户', dataIndex: 'customer', width: 140, ellipsis: true },
    { title: '产品编码', dataIndex: 'product_code', width: 200, render: (v: string) => v || '-' },
    { title: '型号', dataIndex: 'product_model', width: 250, render: (v: string) => v || '-' },
    { title: '数量', dataIndex: 'order_qty', width: 100, render: (v: number) => v ?? '-' },
    { title: '交期', dataIndex: 'promised_date', width: 110, render: (v: string) => formatDate(v) },
    {
      title: '风险等级', dataIndex: 'risk_level', width: 100,
      render: (v: string) => <Tag color={RISK_MAP[v]?.color || 'default'}>{RISK_MAP[v]?.label || v}</Tag>,
    },
    { title: 'UPPH', dataIndex: 'upph', width: 90, render: (v: number) => v > 0 ? v : <span style={{ color: '#999' }}>未设置</span> },
    {
      title: '排产状态', dataIndex: 'has_schedule', width: 100,
      render: (v: boolean) => v ? <Tag color="green">已排产</Tag> : <Tag color="orange">待排产</Tag>,
    },
    {
      title: '操作', width: 120, fixed: 'right' as const,
      render: (_: any, row: any) => (
        <Tooltip title={row.upph <= 0 ? '请先设置UPPH或手动输入' : '一键排产'}>
          <Button
            type={row.has_schedule ? 'default' : 'primary'}
            size="small"
            icon={<ThunderboltOutlined />}
            onClick={() => openSchedule(row)}
          >
            排产
          </Button>
        </Tooltip>
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '12px 20px', marginBottom: 16 }}>
        <Tabs
          activeKey={activeTab}
          onChange={(key) => { setActiveTab(key); setPage(1); setOrderPage(1) }}
          items={[
            { key: 'orders', label: '当月订单池' },
            { key: 'active_plans', label: '当前计划排产' },
            { key: 'reschedule_needed', label: '待重排' },
            { key: 'history_plans', label: '历史排产' },
          ]}
        />

        {['active_plans', 'reschedule_needed', 'history_plans'].includes(activeTab) && (
          <>
            <Tabs
              activeKey={department}
              onChange={(key) => { setDepartment(key); setPage(1) }}
              items={DEPARTMENTS.map(d => ({ key: d, label: d }))}
              style={{ marginBottom: 12 }}
            />
            <Row gutter={12} align="middle">
              <Col>
                <Input
                  prefix={<SearchOutlined />}
                  value={keyword}
                  onChange={e => { setKeyword(e.target.value); setPage(1) }}
                  placeholder="搜索订单/产品/型号/负责人"
                  allowClear
                  style={{ width: 260 }}
                />
              </Col>
              <Col>
                <Select
                  allowClear
                  placeholder="状态"
                  value={status}
                  onChange={v => { setStatus(v); setPage(1) }}
                  style={{ width: 140 }}
                  options={Object.entries(STATUS_MAP).map(([value, item]) => ({ value, label: item.label }))}
                />
              </Col>
              <Col>
                <DatePicker.RangePicker
                  onChange={dates => {
                    setDateRange(dates && dates[0] && dates[1] ? [dates[0].format('YYYY-MM-DD'), dates[1].format('YYYY-MM-DD')] : null)
                    setPage(1)
                  }}
                />
              </Col>
              <Col flex="auto" />
              <Col>
                <Space>
                  <Button icon={<ReloadOutlined />} onClick={loadPlans}>刷新</Button>
                  {activeTab === 'active_plans' && (
                    <Button type="primary" onClick={handleDetectChanges}>检测变更</Button>
                  )}
                  <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增计划</Button>
                </Space>
              </Col>
            </Row>
          </>
        )}

        {activeTab === 'orders' && (
          <Row gutter={12} align="middle">
            <Col>
              <Select value={year} onChange={v => { setYear(v); setOrderPage(1) }} style={{ width: 100 }} options={
                Array.from({ length: 10 }, (_, i) => ({ value: dayjs().year() - 5 + i, label: (dayjs().year() - 5 + i) + '年' }))
              } />
            </Col>
            <Col>
              <Select value={month} onChange={v => { setMonth(v); setOrderPage(1) }} style={{ width: 100 }} options={
                Array.from({ length: 12 }, (_, i) => ({ value: i + 1, label: (i + 1) + '月' }))
              } />
            </Col>
            <Col>
              <Input
                prefix={<SearchOutlined />}
                value={keyword}
                onChange={e => { setKeyword(e.target.value); setOrderPage(1) }}
                placeholder="搜索订单/客户/产品"
                allowClear
                style={{ width: 260 }}
              />
            </Col>
            <Col>
              <Select
                allowClear
                placeholder="风险等级"
                value={riskLevel}
                onChange={v => { setRiskLevel(v); setOrderPage(1) }}
                style={{ width: 120 }}
                options={Object.entries(RISK_MAP).map(([value, item]) => ({ value, label: item.label }))}
              />
            </Col>
            <Col>
              <Select
                allowClear
                placeholder="仅待排产"
                value={onlyUnscheduled}
                onChange={v => { setOnlyUnscheduled(v); setOrderPage(1) }}
                style={{ width: 120 }}
                options={[
                  { value: false, label: '全部' },
                  { value: true, label: '仅待排产' },
                ]}
              />
            </Col>
            <Col flex="auto" />
            <Col>
              <Button icon={<ReloadOutlined />} onClick={loadOrders}>刷新</Button>
            </Col>
          </Row>
        )}
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        {['active_plans', 'reschedule_needed', 'history_plans'].includes(activeTab) && (
          <Table
            rowKey="id"
            columns={planColumns}
            dataSource={data}
            loading={loading}
            size="small"
            scroll={{ x: 1600 }}
            pagination={{
              total,
              current: page,
              pageSize,
              showSizeChanger: true,
              onChange: (p, ps) => { setPage(p); setPageSize(ps) },
              showTotal: t => `共 ${t} 条`,
            }}
          />
        )}

        {activeTab === 'orders' && (
          <Table
            rowKey={(row: any) => `${row.order_no}-${row.line_no}`}
            columns={orderColumns}
            dataSource={orderData}
            loading={loading}
            size="small"
            scroll={{ x: 1400 }}
            pagination={{
              total: orderTotal,
              current: orderPage,
              pageSize,
              showSizeChanger: true,
              onChange: (p, ps) => { setOrderPage(p); setPageSize(ps) },
              showTotal: t => `共 ${t} 条`,
            }}
          />
        )}
      </div>

      <Modal
        title={editing ? '编辑计划排产' : '新增计划排产'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        width={800}
      >
        <Form form={form} layout="vertical">
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item name="department" label="部门" rules={[{ required: true }]}>
                <Select options={DEPARTMENTS.map(d => ({ value: d, label: d }))} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="plan_date" label="计划日期" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="status" label="状态">
                <Select options={Object.entries(STATUS_MAP).map(([value, item]) => ({ value, label: item.label }))} />
              </Form.Item>
            </Col>
            <Col span={8}><Form.Item name="order_no" label="订单号"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="product_code" label="产品编码"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="model_code" label="型号"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="quantity" label="数量"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="upph" label="UPPH"><InputNumber min={0} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="daily_work_hours" label="每日工作时长(h)"><InputNumber min={1} max={24} style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="owner" label="负责人"><Input /></Form.Item></Col>
            <Col span={8}>
              <Form.Item name="priority" label="优先级">
                <Select options={Object.entries(PRIORITY_MAP).map(([value, item]) => ({ value, label: item.label }))} />
              </Form.Item>
            </Col>
            <Col span={8}><Form.Item name="start_date" label="开始日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="end_date" label="结束日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={24}><Form.Item name="remark" label="备注"><Input.TextArea rows={3} /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>

      <Modal
        title="一键排产"
        open={scheduleModalOpen}
        onOk={handleAutoSchedule}
        onCancel={() => setScheduleModalOpen(false)}
        width={640}
      >
        <Form form={scheduleForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}><Form.Item name="order_no" label="订单号"><Input disabled /></Form.Item></Col>
            <Col span={12}><Form.Item name="line_no" label="行号"><Input disabled /></Form.Item></Col>
            <Col span={12}><Form.Item name="product_code" label="产品编码"><Input disabled /></Form.Item></Col>
            <Col span={12}><Form.Item name="model_code" label="型号"><Input disabled /></Form.Item></Col>
            <Col span={12}><Form.Item name="quantity" label="数量"><InputNumber disabled style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={12}><Form.Item name="promised_date" label="交期"><DatePicker disabled style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={12}>
              <Form.Item name="department" label="部门" rules={[{ required: true }]}>
                <Select options={DEPARTMENTS.map(d => ({ value: d, label: d }))} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="plan_date" label="计划日期" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="upph" label="UPPH (每小时产能)" rules={[{ required: true, type: 'number', min: 0.001 }]}>
                <InputNumber min={0.001} style={{ width: '100%' }} placeholder="请输入UPPH" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="daily_work_hours" label="每日工作时长(h)" rules={[{ required: true }]}>
                <InputNumber min={1} max={24} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={24}><Form.Item name="owner" label="负责人"><Input /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>
    </div>
  )
}
