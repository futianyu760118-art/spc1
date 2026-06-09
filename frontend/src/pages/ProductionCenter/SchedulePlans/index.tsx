import { useCallback, useEffect, useState } from 'react'
import { Button, Col, DatePicker, Form, Input, InputNumber, Modal, Popconfirm, Row, Select, Space, Table, Tabs, Tag, message } from 'antd'
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { productionApi } from '../../../services/api'
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

export default function SchedulePlans() {
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
  const [editing, setEditing] = useState<any>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, any> = { page, page_size: pageSize, department }
      if (keyword.trim()) params.keyword = keyword.trim()
      if (status) params.status = status
      if (dateRange) {
        params.date_start = dateRange[0]
        params.date_end = dateRange[1]
      }
      const res: any = await productionApi.listSchedulePlans(params)
      setData(res.data.items || [])
      setTotal(res.data.total || 0)
    } catch (e: any) {
      message.error(e.message || '获取计划排产失败')
    } finally {
      setLoading(false)
    }
  }, [dateRange, department, keyword, page, pageSize, status])

  useEffect(() => { load() }, [load])

  const openCreate = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ department, plan_date: dayjs(), priority: 'normal', status: 'planned' })
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
      load()
    } catch (e: any) {
      if (!e?.errorFields) message.error(e.message || '保存失败')
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await productionApi.deleteSchedulePlan(id)
      message.success('删除成功')
      load()
    } catch (e: any) {
      message.error(e.message || '删除失败')
    }
  }

  const columns = [
    { title: '计划日期', dataIndex: 'plan_date', width: 110, render: (v: string) => formatDate(v) },
    { title: '订单号', dataIndex: 'order_no', width: 120, ellipsis: true, render: (v: string) => v || '-' },
    { title: '产品编码', dataIndex: 'product_code', width: 120, ellipsis: true, render: (v: string) => v || '-' },
    { title: '型号', dataIndex: 'model_code', ellipsis: true, render: (v: string) => v || '-' },
    { title: '数量', dataIndex: 'quantity', width: 90, render: (v: number) => v ?? '-' },
    { title: '负责人', dataIndex: 'owner', width: 100, render: (v: string) => v || '-' },
    { title: '开始日期', dataIndex: 'start_date', width: 110, render: (v: string) => formatDate(v) },
    { title: '结束日期', dataIndex: 'end_date', width: 110, render: (v: string) => formatDate(v) },
    {
      title: '优先级', dataIndex: 'priority', width: 90,
      render: (v: string) => <Tag color={PRIORITY_MAP[v]?.color || 'default'}>{PRIORITY_MAP[v]?.label || v}</Tag>,
    },
    {
      title: '状态', dataIndex: 'status', width: 100,
      render: (v: string) => <Tag color={STATUS_MAP[v]?.color || 'default'}>{STATUS_MAP[v]?.label || v}</Tag>,
    },
    { title: '备注', dataIndex: 'remark', width: 160, ellipsis: true, render: (v: string) => v || '-' },
    {
      title: '操作', width: 100, fixed: 'right' as const,
      render: (_: any, row: any) => (
        <Space size={4}>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(row)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(row.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '12px 20px', marginBottom: 16 }}>
        <Tabs
          activeKey={department}
          onChange={(key) => { setDepartment(key); setPage(1) }}
          items={DEPARTMENTS.map(d => ({ key: d, label: d }))}
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
              <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增计划</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          size="small"
          scroll={{ x: 1280 }}
          pagination={{
            total,
            current: page,
            pageSize,
            showSizeChanger: true,
            onChange: (p, ps) => { setPage(p); setPageSize(ps) },
            showTotal: t => `共 ${t} 条`,
          }}
        />
      </div>

      <Modal
        title={editing ? '编辑计划排产' : '新增计划排产'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        width={720}
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
    </div>
  )
}
