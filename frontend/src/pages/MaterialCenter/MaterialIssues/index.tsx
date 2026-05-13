import { useEffect, useState, useCallback } from 'react'
import {
  Table, Tag, Input, Select, Button, Space, message, Modal, Form,
  DatePicker, Upload, Row, Col, Popconfirm,
} from 'antd'
import {
  SearchOutlined, ReloadOutlined, UploadOutlined, PlusOutlined, EditOutlined, DeleteOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { materialApi } from '../../../services/api'

interface IssueRow {
  id: number
  year: number | null
  week_no: number | null
  department: string | null
  category: string | null
  issue_date: string | null
  reporter: string | null
  description: string | null
  deadline: string | null
  responsible_dept: string | null
  responsible_person: string | null
  audit_score: number | null
  is_project: boolean | null
  follow_up_record: string | null
  status: string
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  open: { label: '待处理', color: 'error' },
  in_progress: { label: '处理中', color: 'processing' },
  closed: { label: '已关闭', color: 'success' },
}

export default function MaterialIssues() {
  const [data, setData] = useState<IssueRow[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState({ keyword: '', department: '', status: '' })
  const [sortBy, setSortBy] = useState<string>('')
  const [sortOrder, setSortOrder] = useState<string>('')
  const [modalOpen, setModalOpen] = useState(false)
  const [editRecord, setEditRecord] = useState<IssueRow | null>(null)
  const [form] = Form.useForm()

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await materialApi.listIssues({
        page, page_size: pageSize,
        ...(filters.keyword ? { keyword: filters.keyword } : {}),
        ...(filters.department ? { department: filters.department } : {}),
        ...(filters.status ? { status: filters.status } : {}),
        ...(sortBy ? { sort_by: sortBy, sort_order: sortOrder || 'asc' } : {}),
      })
      setData(res.data.items)
      setTotal(res.data.total)
    } catch (e: any) {
      message.error(e.message)
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, filters, sortBy, sortOrder])

  useEffect(() => { load() }, [load])

  const openCreate = () => {
    setEditRecord(null)
    form.resetFields()
    setModalOpen(true)
  }

  const openEdit = (row: IssueRow) => {
    setEditRecord(row)
    form.setFieldsValue({
      ...row,
      issue_date: row.issue_date ? dayjs(row.issue_date) : null,
      deadline: row.deadline ? dayjs(row.deadline) : null,
    })
    setModalOpen(true)
  }

  const handleSubmit = async (values: any) => {
    const payload = {
      ...values,
      issue_date: values.issue_date ? dayjs(values.issue_date).format('YYYY-MM-DD') : null,
      deadline: values.deadline ? dayjs(values.deadline).format('YYYY-MM-DD') : null,
    }
    try {
      if (editRecord) {
        await materialApi.updateIssue(editRecord.id, payload)
        message.success('更新成功')
      } else {
        await materialApi.createIssue(payload)
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
      await materialApi.deleteIssue(id)
      message.success('删除成功')
      load()
    } catch (e: any) {
      message.error(e.message)
    }
  }

  const handleImport = async (file: File) => {
    try {
      const res: any = await materialApi.importIssues(file)
      message.success(`导入完成：新增 ${res.data.created}，更新 ${res.data.updated}，跳过 ${res.data.skipped}`)
      load()
    } catch (e: any) {
      message.error(`导入失败：${e.message}`)
    }
    return false
  }

  const columns = [
    { title: '年份', dataIndex: 'year', width: 65, sorter: true },
    { title: '周序', dataIndex: 'week_no', width: 55, sorter: true },
    { title: '部门', dataIndex: 'department', width: 70, sorter: true },
    { title: '类别', dataIndex: 'category', width: 70, sorter: true },
    { title: '日期', dataIndex: 'issue_date', width: 90, sorter: true },
    { title: '提出人', dataIndex: 'reporter', width: 80, sorter: true },
    {
      title: '问题描述', dataIndex: 'description', ellipsis: true, width: 280,
      render: (v: string | null) => (
        <span title={v || ''}>{v || '-'}</span>
      ),
    },
    { title: '节点', dataIndex: 'deadline', width: 90, sorter: true },
    { title: '责任部门', dataIndex: 'responsible_dept', width: 80, sorter: true },
    { title: '责任人', dataIndex: 'responsible_person', width: 70, sorter: true },
    { title: '评分', dataIndex: 'audit_score', width: 60, sorter: true, render: (v: number | null) => v ?? '-' },
    { title: '立项', dataIndex: 'is_project', width: 60, render: (v: boolean | null) => v ? '是' : '-' },
    {
      title: '跟进记录', dataIndex: 'follow_up_record', ellipsis: true, width: 180,
      render: (v: string | null) => <span title={v || ''}>{v || '-'}</span>,
    },
    {
      title: '状态', dataIndex: 'status', width: 85, sorter: true,
      render: (v: string) => {
        const s = STATUS_MAP[v] || { label: v, color: 'default' }
        return <Tag color={s.color}>{s.label}</Tag>
      },
    },
    {
      title: '操作', width: 90, fixed: 'right' as const,
      render: (_: any, row: IssueRow) => (
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
          <Col>
            <Input
              prefix={<SearchOutlined />}
              placeholder="搜索问题描述/责任人"
              value={filters.keyword}
              onChange={e => { setFilters(f => ({ ...f, keyword: e.target.value })); setPage(1) }}
              style={{ width: 220 }}
              allowClear
            />
          </Col>
          <Col>
            <Select
              placeholder="部门"
              value={filters.department || undefined}
              onChange={v => { setFilters(f => ({ ...f, department: v || '' })); setPage(1) }}
              allowClear
              style={{ width: 100 }}
            >
              {['计划', '采购', '品质', '仓库', '生产', '销售'].map(d => (
                <Select.Option key={d} value={d}>{d}</Select.Option>
              ))}
            </Select>
          </Col>
          <Col>
            <Select
              placeholder="状态"
              value={filters.status || undefined}
              onChange={v => { setFilters(f => ({ ...f, status: v || '' })); setPage(1) }}
              allowClear
              style={{ width: 110 }}
            >
              <Select.Option value="open">待处理</Select.Option>
              <Select.Option value="in_progress">处理中</Select.Option>
              <Select.Option value="closed">已关闭</Select.Option>
            </Select>
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
              <Upload beforeUpload={(f) => { handleImport(f); return false }} showUploadList={false} accept=".csv">
                <Button icon={<UploadOutlined />}>导入CSV</Button>
              </Upload>
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新增问题</Button>
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
          scroll={{ x: 1400 }}
          size="small"
          pagination={{
            total, current: page, pageSize,
            showSizeChanger: true, showTotal: t => `共 ${t} 条`,
          }}
          onChange={(pagination, _tableFilters, sorter: any) => {
            setPage(pagination.current || 1)
            setPageSize(pagination.pageSize || 20)
            const sortField = sorter.field as string | undefined
            const sortDir = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : ''
            setSortBy(sortField || '')
            setSortOrder(sortDir)
          }}
        />
      </div>

      <Modal
        title={editRecord ? '编辑问题物料' : '新增问题物料'}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        width={700}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit} initialValues={{ status: 'open' }}>
          <Row gutter={16}>
            <Col span={6}><Form.Item name="year" label="年份"><Input type="number" /></Form.Item></Col>
            <Col span={6}><Form.Item name="week_no" label="周序"><Input type="number" /></Form.Item></Col>
            <Col span={6}>
              <Form.Item name="department" label="部门">
                <Select allowClear>
                  {['计划', '采购', '品质', '仓库', '生产', '销售'].map(d => (
                    <Select.Option key={d} value={d}>{d}</Select.Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="category" label="类别">
                <Select allowClear>
                  <Select.Option value="问题">问题</Select.Option>
                  <Select.Option value="改善">改善</Select.Option>
                </Select>
              </Form.Item>
            </Col>
            <Col span={8}><Form.Item name="issue_date" label="日期"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={8}><Form.Item name="reporter" label="提出人"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="deadline" label="节点"><DatePicker style={{ width: '100%' }} /></Form.Item></Col>
            <Col span={24}>
              <Form.Item name="description" label="问题描述" rules={[{ required: true }]}>
                <Input.TextArea rows={3} />
              </Form.Item>
            </Col>
            <Col span={8}><Form.Item name="responsible_dept" label="责任部门"><Input /></Form.Item></Col>
            <Col span={8}><Form.Item name="responsible_person" label="责任人"><Input /></Form.Item></Col>
            <Col span={4}>
              <Form.Item name="audit_score" label="评分">
                <Input type="number" />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item name="is_project" label="立项" valuePropName="checked">
                <input type="checkbox" />
              </Form.Item>
            </Col>
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
              <Form.Item name="follow_up_record" label="稽核证据和跟进记录">
                <Input.TextArea rows={3} />
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Modal>
    </div>
  )
}
