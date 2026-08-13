import { useState, useEffect, useCallback } from 'react'
import { Table, Button, Space, Tag, Modal, Form, Input, Select, message, Popconfirm, Card, Typography } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, SendOutlined } from '@ant-design/icons'
import { announcementApi } from '../../../services/api'
import { useAuthStore } from '../../../store/auth'

const { TextArea } = Input
const { Text } = Typography

const typeOptions = [
  { label: '通知', value: 'notice' },
  { label: '系统更新', value: 'system_update' },
  { label: '维护公告', value: 'maintenance' },
]

const priorityOptions = [
  { label: '普通', value: 'normal' },
  { label: '重要', value: 'important' },
  { label: '紧急', value: 'urgent' },
]

const typeColorMap: Record<string, string> = {
  notice: 'blue',
  system_update: 'green',
  maintenance: 'orange',
}

const priorityColorMap: Record<string, string> = {
  normal: 'default',
  important: 'gold',
  urgent: 'red',
}

const typeLabelMap: Record<string, string> = {
  notice: '通知',
  system_update: '系统更新',
  maintenance: '维护公告',
}

const priorityLabelMap: Record<string, string> = {
  normal: '普通',
  important: '重要',
  urgent: '紧急',
}

export default function AnnouncementManagement() {
  const hasPermission = useAuthStore((s: any) => s.hasPermission)
  const canCreate = hasPermission('announcements', 'create')
  const canUpdate = hasPermission('announcements', 'update')
  const canDelete = hasPermission('announcements', 'delete')

  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [modalOpen, setModalOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [form] = Form.useForm()
  const [sortInfo, setSortInfo] = useState<{ sort_by?: string; sort_order?: string }>({})
  const [filters, setFilters] = useState<Record<string, string[]>>({})

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const params: any = { page, page_size: pageSize }
      if (sortInfo.sort_by) params.sort_by = sortInfo.sort_by
      if (sortInfo.sort_order) params.sort_order = sortInfo.sort_order
      if (filters.type?.length) params.type = filters.type.join(',')
      if (filters.priority?.length) params.priority = filters.priority.join(',')
      if (filters.is_published?.length) params.is_published = filters.is_published[0] === 'true'
      if (filters.created_by?.length) params.created_by = filters.created_by.join(',')
      const res: any = await announcementApi.list(params)
      setData(res.data?.items || [])
      setTotal(res.data?.total || 0)
    } catch {
      // handled by interceptor
    } finally {
      setLoading(false)
    }
  }, [page, pageSize, sortInfo, filters])

  useEffect(() => { fetchData() }, [fetchData])

  const handleTableChange = (_pag: any, tableFilters: any, sorter: any) => {
    const sortField = sorter.field
    const sortOrder = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : undefined
    setSortInfo({ sort_by: sortField, sort_order: sortOrder })
    const newFilters: Record<string, string[]> = {}
    if (tableFilters.type?.length) newFilters.type = tableFilters.type
    if (tableFilters.priority?.length) newFilters.priority = tableFilters.priority
    if (tableFilters.is_published?.length) newFilters.is_published = tableFilters.is_published
    if (tableFilters.created_by?.length) newFilters.created_by = tableFilters.created_by
    setFilters(newFilters)
    setPage(1)
  }

  const openCreate = () => {
    setEditingId(null)
    form.resetFields()
    form.setFieldsValue({ type: 'notice', priority: 'normal' })
    setModalOpen(true)
  }

  const openEdit = (record: any) => {
    setEditingId(record.id)
    form.setFieldsValue({
      title: record.title,
      content: record.content,
      type: record.type,
      priority: record.priority,
    })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      if (editingId) {
        await announcementApi.update(editingId, values)
        message.success('公告已更新')
      } else {
        await announcementApi.create(values)
        message.success('公告已创建')
      }
      setModalOpen(false)
      fetchData()
    } catch (e: any) {
      if (e?.errorFields) return
      // 错误已由全局拦截器提示
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await announcementApi.remove(id)
      message.success('公告已删除')
      fetchData()
    } catch (e: any) {
      // 错误已由全局拦截器提示
    }
  }

  const handlePublish = async (id: number) => {
    try {
      const res: any = await announcementApi.publish(id)
      const count = res.data?.notified_users || 0
      message.success(`公告已发布，已通知 ${count} 位用户`)
      fetchData()
    } catch (e: any) {
      // 错误已由全局拦截器提示
    }
  }

  const uniqueValues = (key: string) => Array.from(new Set(data.map((r: any) => r[key]).filter(Boolean))).map(v => ({ text: String(v), value: v }))

  const columns = [
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      width: 260,
      ellipsis: true,
      sorter: true,
    },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 110,
      sorter: true,
      filters: typeOptions.map(o => ({ text: o.label, value: o.value })),
      render: (v: string) => <Tag color={typeColorMap[v]}>{typeLabelMap[v] || v}</Tag>,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 90,
      sorter: true,
      filters: priorityOptions.map(o => ({ text: o.label, value: o.value })),
      render: (v: string) => <Tag color={priorityColorMap[v]}>{priorityLabelMap[v] || v}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'is_published',
      key: 'is_published',
      width: 90,
      sorter: true,
      filters: [{ text: '已发布', value: 'true' }, { text: '草稿', value: 'false' }],
      render: (v: boolean) => v
        ? <Tag color="success">已发布</Tag>
        : <Tag>草稿</Tag>,
    },
    {
      title: '创建人',
      dataIndex: 'created_by',
      key: 'created_by',
      width: 100,
      sorter: true,
      filters: uniqueValues('created_by'),
      filterSearch: true,
    },
    {
      title: '发布时间',
      dataIndex: 'published_at',
      key: 'published_at',
      width: 150,
      sorter: true,
      render: (v: string) => v || '-',
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 150,
      sorter: true,
    },
    {
      title: '操作',
      key: 'actions',
      width: 220,
      render: (_: any, record: any) => (
        <Space size="small">
          {canUpdate && !record.is_published && (
            <Button type="link" size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
              编辑
            </Button>
          )}
          {canUpdate && !record.is_published && (
            <Popconfirm title="确认发布？发布后将通知所有用户。" onConfirm={() => handlePublish(record.id)}>
              <Button type="link" size="small" icon={<SendOutlined />} style={{ color: '#52c41a' }}>
                发布
              </Button>
            </Popconfirm>
          )}
          {canDelete && (
            <Popconfirm title="确认删除该公告？" onConfirm={() => handleDelete(record.id)}>
              <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Card
      title="公告管理"
      extra={
        canCreate && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            新建公告
          </Button>
        )
      }
    >
      <Table
        rowKey="id"
        loading={loading}
        columns={columns}
        dataSource={data}
        onChange={handleTableChange}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps) },
        }}
        expandable={{
          expandedRowRender: (record: any) => (
            <div style={{ padding: '8px 0' }}>
              <Text type="secondary" style={{ whiteSpace: 'pre-wrap' }}>
                {record.content || '（无正文内容）'}
              </Text>
            </div>
          ),
        }}
        size="middle"
        scroll={{ x: 1100 }}
      />

      <Modal
        title={editingId ? '编辑公告' : '新建公告'}
        open={modalOpen}
        onOk={handleSubmit}
        onCancel={() => setModalOpen(false)}
        confirmLoading={submitting}
        width={640}
        okText={editingId ? '保存' : '创建'}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="title" label="标题" rules={[{ required: true, message: '请输入公告标题' }]}>
            <Input placeholder="请输入公告标题" maxLength={200} />
          </Form.Item>
          <Form.Item name="content" label="正文">
            <TextArea rows={6} placeholder="请输入公告正文" maxLength={5000} showCount />
          </Form.Item>
          <Space size="large">
            <Form.Item name="type" label="类型" rules={[{ required: true }]}>
              <Select options={typeOptions} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="priority" label="优先级" rules={[{ required: true }]}>
              <Select options={priorityOptions} style={{ width: 160 }} />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </Card>
  )
}
