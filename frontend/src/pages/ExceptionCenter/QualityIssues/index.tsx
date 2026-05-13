import { useEffect, useState, useCallback } from 'react'
import {
  Table, Tag, Input, Select, Button, Space, message, Modal, Form,
  DatePicker, InputNumber, Row, Col, Popconfirm,
} from 'antd'
import {
  ReloadOutlined, PlusOutlined, EditOutlined, DeleteOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { exceptionApi } from '../../../services/api'
import { formatDate } from '../../../utils'

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  open: { label: '待处理', color: 'error' },
  in_progress: { label: '处理中', color: 'processing' },
  closed: { label: '已关闭', color: 'success' },
}

const DEPT_OPTIONS = ['计划', '采购', '品质', '仓库', '生产', '销售', '工程', '研发']

export default function QualityIssues() {
  const [data, setData] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [modalOpen, setModalOpen] = useState(false)
  const [editRecord, setEditRecord] = useState<any>(null)
  const [keyword, setKeyword] = useState('')
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = { page, page_size: pageSize }
      if (keyword.trim()) params.keyword = keyword.trim()
      const res: any = await exceptionApi.listQuality(params)
      setData(res.data.items)
      setTotal(res.data.total)
    } catch (e: any) {
      message.error(e.message || '获取品质异常失败')
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, keyword])

  useEffect(() => { load() }, [load])

  const openCreate = () => {
    setEditRecord(null)
    form.resetFields()
    setModalOpen(true)
  }

  const openEdit = (row: any) => {
    setEditRecord(row)
    form.setFieldsValue({
      status: row.status,
    })
    setModalOpen(true)
  }

  const handleSubmit = async (values: any) => {
    const payload = editRecord
      ? { status: values.status }
      : {
          ...values,
          submit_date: values.submit_date ? dayjs(values.submit_date).format('YYYY-MM-DD') : null,
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
      message.error(e.message)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await exceptionApi.deleteQuality(id)
      message.success('删除成功')
      load()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const handleSearch = () => {
    if (page === 1) {
      load()
      return
    }
    setPage(1)
  }

  const textSorter = (field: string) => (a: any, b: any) => String(a[field] || '').localeCompare(String(b[field] || ''))
  const numberSorter = (field: string) => (a: any, b: any) => Number(a[field] || 0) - Number(b[field] || 0)
  const dateSorter = (field: string) => (a: any, b: any) => dayjs(a[field] || 0).valueOf() - dayjs(b[field] || 0).valueOf()
  const uniqueFilters = (field: string) => Array.from(new Set(data.map(item => item[field]).filter(Boolean))).map(value => ({ text: String(value), value: String(value) }))

  const columns = [
    { title: '编号', dataIndex: 'issue_no', width: 120, fixed: 'left' as const, sorter: textSorter('issue_no') },
    { title: '订单编号', dataIndex: 'order_no', width: 120, fixed: 'left' as const, sorter: textSorter('order_no'), filters: uniqueFilters('order_no'), onFilter: (value: any, record: any) => record.order_no === value },
    { title: '产品代码', dataIndex: 'product_code', width: 120, fixed: 'left' as const, sorter: textSorter('product_code'), filters: uniqueFilters('product_code'), onFilter: (value: any, record: any) => record.product_code === value },
    { title: '提出部门', dataIndex: 'submit_dept', width: 80, sorter: textSorter('submit_dept'), filters: uniqueFilters('submit_dept'), onFilter: (value: any, record: any) => record.submit_dept === value },
    { title: '提出日期', dataIndex: 'submit_date', width: 100, sorter: dateSorter('submit_date'), render: (v: string) => formatDate(v) },
    { title: '提出人', dataIndex: 'submitter', width: 75, sorter: textSorter('submitter'), filters: uniqueFilters('submitter'), onFilter: (value: any, record: any) => record.submitter === value },
    { title: '产品名称', dataIndex: 'product_name', width: 120, ellipsis: true, sorter: textSorter('product_name') },
    { title: '工序', dataIndex: 'process', width: 80, sorter: textSorter('process'), filters: uniqueFilters('process'), onFilter: (value: any, record: any) => record.process === value },
    { title: '缺陷类型', dataIndex: 'defect_type', width: 90, sorter: textSorter('defect_type'), filters: uniqueFilters('defect_type'), onFilter: (value: any, record: any) => record.defect_type === value },
    {
      title: '异常描述', dataIndex: 'description', ellipsis: true, width: 200,
      sorter: textSorter('description'),
      render: (v: string | null) => <span title={v || ''}>{v || '-'}</span>,
    },
    {
      title: '真实原因', dataIndex: 'root_cause', ellipsis: true, width: 180,
      sorter: textSorter('root_cause'),
      render: (v: string | null) => <span title={v || ''}>{v || '-'}</span>,
    },
    { title: '责任人', dataIndex: 'responsible_person', width: 75, sorter: textSorter('responsible_person'), filters: uniqueFilters('responsible_person'), onFilter: (value: any, record: any) => record.responsible_person === value },
    { title: '责任部门', dataIndex: 'responsible_dept', width: 80, sorter: textSorter('responsible_dept'), filters: uniqueFilters('responsible_dept'), onFilter: (value: any, record: any) => record.responsible_dept === value },
    { title: '批量数', dataIndex: 'batch_qty', width: 70, sorter: numberSorter('batch_qty'), render: (v: number | null) => v ?? '-' },
    { title: '抽样数量', dataIndex: 'sample_qty', width: 75, sorter: numberSorter('sample_qty'), render: (v: number | null) => v ?? '-' },
    { title: '不良数', dataIndex: 'defect_qty', width: 70, sorter: numberSorter('defect_qty'), render: (v: number | null) => v ?? '-' },
    {
      title: '不良率',
      width: 80,
      sorter: (a: any, b: any) => {
        const rateA = Number(a.sample_qty || 0) ? Number(a.defect_qty || 0) / Number(a.sample_qty || 0) : 0
        const rateB = Number(b.sample_qty || 0) ? Number(b.defect_qty || 0) / Number(b.sample_qty || 0) : 0
        return rateA - rateB
      },
      render: (_: any, row: any) => {
        const sampleQty = Number(row.sample_qty || 0)
        const defectQty = Number(row.defect_qty || 0)
        if (!sampleQty) return '-'
        return `${((defectQty / sampleQty) * 100).toFixed(2)}%`
      },
    },
    {
      title: '状态', dataIndex: 'status', width: 85, fixed: 'right' as const,
      sorter: textSorter('status'),
      filters: [
        { text: '待处理', value: 'open' },
        { text: '处理中', value: 'in_progress' },
        { text: '已关闭', value: 'closed' },
      ],
      onFilter: (value: any, record: any) => record.status === value,
      render: (v: string) => {
        const s = STATUS_MAP[v] || { label: v, color: 'default' }
        return <Tag color={s.color}>{s.label}</Tag>
      },
    },
    {
      title: '操作', width: 90, fixed: 'right' as const,
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
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col flex="auto">
            <Input.Search
              allowClear
              placeholder="模糊查询：订单编号、产品代码、提出部门、提出人、产品名称、工序、缺陷类型、异常描述、真实原因、责任人、责任部门"
              value={keyword}
              onChange={e => setKeyword(e.target.value)}
              onSearch={handleSearch}
              style={{ maxWidth: 720 }}
            />
          </Col>
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增品质异常</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="id"
          dataSource={data}
          columns={columns}
          loading={loading}
          scroll={{ x: 1900 }}
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
        width={editRecord ? 420 : 800}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit} initialValues={{ status: 'open' }}>
          {editRecord ? (
            <Form.Item name="status" label="状态">
              <Select>
                <Select.Option value="open">待处理</Select.Option>
                <Select.Option value="in_progress">处理中</Select.Option>
                <Select.Option value="closed">已关闭</Select.Option>
              </Select>
            </Form.Item>
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
              <Form.Item name="remark" label="备注">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Col>
          </Row>
          )}
        </Form>
      </Modal>
    </div>
  )
}
