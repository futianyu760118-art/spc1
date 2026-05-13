import { useEffect, useState, useCallback } from 'react'
import { Table, Tag, Input, Button, Space, message, Modal, Form, Select, Row, Col, DatePicker, Popconfirm } from 'antd'
import { SearchOutlined, ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { productionApi } from '../../../services/api'

interface ExceptionRow {
  id: number
  exception_no: string
  process_type: string | null
  order_no: string | null
  model_code: string | null
  exception_type: string | null
  severity: string | null
  description: string | null
  responsible_dept: string | null
  responsible_person: string | null
  status: string
  resolved_at: string | null
  remark: string | null
}

const PROCESS_LABELS: Record<string, string> = {
  front_process: '前道', smt: '贴片', lean: '精益', assembly: '组装', packaging: '包装',
}

const EXCEPTION_TYPES = ['停线', '缺料', '返工', '未上线', '品质异常', '其他']

const SEVERITY_MAP: Record<string, { label: string; color: string }> = {
  high: { label: '高', color: 'error' },
  medium: { label: '中', color: 'warning' },
  low: { label: '低', color: 'default' },
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  open: { label: '待处理', color: 'error' },
  processing: { label: '处理中', color: 'processing' },
  resolved: { label: '已解决', color: 'success' },
  closed: { label: '已关闭', color: 'default' },
}

export default function ProcessExceptions() {
  const [data, setData] = useState<ExceptionRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState({ keyword: '', process_type: '', severity: '', status: '' })
  const [addModal, setAddModal] = useState(false)
  const [editModal, setEditModal] = useState(false)
  const [editRecord, setEditRecord] = useState<ExceptionRow | null>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await productionApi.listExceptions({
        page, page_size: pageSize,
        ...(filters.keyword ? { keyword: filters.keyword } : {}),
        ...(filters.process_type ? { process_type: filters.process_type } : {}),
        ...(filters.severity ? { severity: filters.severity } : {}),
        ...(filters.status ? { status: filters.status } : {}),
      })
      setData(res.data.items)
      setTotal(res.data.total)
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, filters])

  useEffect(() => { load() }, [load])

  const handleAdd = async (values: any) => {
    try {
      await productionApi.createException(values)
      message.success('新增异常成功')
      setAddModal(false)
      form.resetFields()
      load()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const handleEdit = async (values: any) => {
    if (!editRecord) return
    try {
      const payload: Record<string, any> = {
        ...values,
        resolved_at: values.resolved_at ? dayjs(values.resolved_at).format('YYYY-MM-DD') : null,
      }
      await productionApi.updateException(editRecord.id, payload)
      message.success('更新成功')
      setEditModal(false)
      form.resetFields()
      load()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await productionApi.deleteException(id)
      message.success('删除成功')
      load()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const columns = [
    { title: '异常编号', dataIndex: 'exception_no', width: 130, render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span> },
    { title: '工序', dataIndex: 'process_type', width: 70, render: (v: string | null) => v ? PROCESS_LABELS[v] || v : '-' },
    { title: '订单号', dataIndex: 'order_no', width: 90 },
    { title: '型号', dataIndex: 'model_code', width: 160, ellipsis: true },
    {
      title: '异常类型', dataIndex: 'exception_type', width: 90,
      render: (v: string | null) => v ? <Tag color="volcano">{v}</Tag> : '-',
    },
    {
      title: '严重程度', dataIndex: 'severity', width: 80,
      render: (v: string | null) => { if (!v) return '-'; const s = SEVERITY_MAP[v] || { label: v, color: 'default' }; return <Tag color={s.color}>{s.label}</Tag> },
    },
    { title: '描述', dataIndex: 'description', width: 200, ellipsis: true },
    { title: '责任部门', dataIndex: 'responsible_dept', width: 90 },
    { title: '责任人', dataIndex: 'responsible_person', width: 80 },
    {
      title: '状态', dataIndex: 'status', width: 80,
      render: (v: string) => { const s = STATUS_MAP[v] || { label: v, color: 'default' }; return <Tag color={s.color}>{s.label}</Tag> },
    },
    { title: '解决时间', dataIndex: 'resolved_at', width: 90 },
    { title: '备注', dataIndex: 'remark', width: 120, ellipsis: true },
    {
      title: '操作', width: 100, fixed: 'right' as const,
      render: (_: any, row: ExceptionRow) => (
        <Space size={4}>
          <Button size="small" icon={<EditOutlined />} onClick={() => {
            setEditRecord(row)
            form.setFieldsValue({
              process_type: row.process_type, order_no: row.order_no, model_code: row.model_code,
              exception_type: row.exception_type, severity: row.severity, description: row.description,
              responsible_dept: row.responsible_dept, responsible_person: row.responsible_person,
              status: row.status, resolved_at: row.resolved_at ? dayjs(row.resolved_at) : null,
              remark: row.remark,
            })
            setEditModal(true)
          }} />
          <Popconfirm title="确认删除?" onConfirm={() => handleDelete(row.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Input prefix={<SearchOutlined />} placeholder="搜索订单/型号/描述" value={filters.keyword}
              onChange={e => { setFilters(f => ({ ...f, keyword: e.target.value })); setPage(1) }}
              style={{ width: 200 }} allowClear />
          </Col>
          <Col>
            <Select placeholder="工序" value={filters.process_type || undefined}
              onChange={v => { setFilters(f => ({ ...f, process_type: v || '' })); setPage(1) }}
              allowClear style={{ width: 100 }}>
              {Object.entries(PROCESS_LABELS).map(([k, v]) => <Select.Option key={k} value={k}>{v}</Select.Option>)}
            </Select>
          </Col>
          <Col>
            <Select placeholder="严重程度" value={filters.severity || undefined}
              onChange={v => { setFilters(f => ({ ...f, severity: v || '' })); setPage(1) }}
              allowClear style={{ width: 100 }}>
              <Select.Option value="high">高</Select.Option>
              <Select.Option value="medium">中</Select.Option>
              <Select.Option value="low">低</Select.Option>
            </Select>
          </Col>
          <Col>
            <Select placeholder="状态" value={filters.status || undefined}
              onChange={v => { setFilters(f => ({ ...f, status: v || '' })); setPage(1) }}
              allowClear style={{ width: 100 }}>
              <Select.Option value="open">待处理</Select.Option>
              <Select.Option value="processing">处理中</Select.Option>
              <Select.Option value="resolved">已解决</Select.Option>
              <Select.Option value="closed">已关闭</Select.Option>
            </Select>
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setAddModal(true)}>新增异常</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table rowKey="id" dataSource={data} columns={columns} loading={loading}
          scroll={{ x: 1600 }} size="small"
          pagination={{ total, current: page, pageSize, onChange: (p, ps) => { setPage(p); setPageSize(ps) }, showSizeChanger: true, showTotal: t => `共 ${t} 条` }}
          rowClassName={(row) => row.severity === 'high' && row.status === 'open' ? 'ant-table-row-danger' : ''}
        />
      </div>

      <Modal title="新增工序异常" open={addModal} onCancel={() => { setAddModal(false); form.resetFields() }}
        onOk={() => form.submit()} width={600}>
        <Form form={form} layout="vertical" onFinish={handleAdd}>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="process_type" label="工序" rules={[{ required: true }]}>
              <Select>{Object.entries(PROCESS_LABELS).map(([k, v]) => <Select.Option key={k} value={k}>{v}</Select.Option>)}</Select>
            </Form.Item></Col>
            <Col span={12}><Form.Item name="exception_type" label="异常类型" rules={[{ required: true }]}>
              <Select>{EXCEPTION_TYPES.map(t => <Select.Option key={t} value={t}>{t}</Select.Option>)}</Select>
            </Form.Item></Col>
            <Col span={12}><Form.Item name="order_no" label="订单号"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="model_code" label="型号"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="severity" label="严重程度">
              <Select allowClear><Select.Option value="high">高</Select.Option><Select.Option value="medium">中</Select.Option><Select.Option value="low">低</Select.Option></Select>
            </Form.Item></Col>
            <Col span={24}><Form.Item name="description" label="异常描述" rules={[{ required: true }]}><Input.TextArea rows={3} /></Form.Item></Col>
            <Col span={12}><Form.Item name="responsible_dept" label="责任部门"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="responsible_person" label="责任人"><Input /></Form.Item></Col>
            <Col span={24}><Form.Item name="remark" label="备注"><Input /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>

      <Modal title="编辑工序异常" open={editModal} onCancel={() => { setEditModal(false); form.resetFields() }}
        onOk={() => form.submit()} width={600}>
        <Form form={form} layout="vertical" onFinish={handleEdit}>
          <Row gutter={16}>
            <Col span={12}><Form.Item name="process_type" label="工序">
              <Select>{Object.entries(PROCESS_LABELS).map(([k, v]) => <Select.Option key={k} value={k}>{v}</Select.Option>)}</Select>
            </Form.Item></Col>
            <Col span={12}><Form.Item name="exception_type" label="异常类型">
              <Select>{EXCEPTION_TYPES.map(t => <Select.Option key={t} value={t}>{t}</Select.Option>)}</Select>
            </Form.Item></Col>
            <Col span={12}><Form.Item name="order_no" label="订单号"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="model_code" label="型号"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="severity" label="严重程度">
              <Select allowClear><Select.Option value="high">高</Select.Option><Select.Option value="medium">中</Select.Option><Select.Option value="low">低</Select.Option></Select>
            </Form.Item></Col>
            <Col span={8}><Form.Item name="status" label="状态">
              <Select><Select.Option value="open">待处理</Select.Option><Select.Option value="processing">处理中</Select.Option><Select.Option value="resolved">已解决</Select.Option><Select.Option value="closed">已关闭</Select.Option></Select>
            </Form.Item></Col>
            <Col span={8}><Form.Item name="resolved_at" label="解决时间"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={24}><Form.Item name="description" label="异常描述"><Input.TextArea rows={3} /></Form.Item></Col>
            <Col span={12}><Form.Item name="responsible_dept" label="责任部门"><Input /></Form.Item></Col>
            <Col span={12}><Form.Item name="responsible_person" label="责任人"><Input /></Form.Item></Col>
            <Col span={24}><Form.Item name="remark" label="备注"><Input /></Form.Item></Col>
          </Row>
        </Form>
      </Modal>
    </div>
  )
}
