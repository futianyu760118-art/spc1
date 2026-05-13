import { useState, useCallback, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, InputNumber, message,
  Space, Tag, Popconfirm, Row, Col,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import api from '../../services/api'

interface Organization {
  id: number
  org_code: string
  org_name: string
  org_type: string
  parent_id?: number
  leader_id?: number
  status: number
}

const OrganizationForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="org_code" label="组织编码" rules={[{ required: true }]}>
      <Input placeholder="请输入组织编码" />
    </Form.Item>
    <Form.Item name="org_name" label="组织名称" rules={[{ required: true }]}>
      <Input placeholder="请输入组织名称" />
    </Form.Item>
    <Form.Item name="org_type" label="组织类型" rules={[{ required: true }]}>
      <Select placeholder="请选择组织类型">
        <Select.Option value="部门">部门</Select.Option>
        <Select.Option value="车间">车间</Select.Option>
        <Select.Option value="班组">班组</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="parent_id" label="父级组织ID">
      <InputNumber style={{ width: '100%' }} placeholder="请输入父级组织ID" />
    </Form.Item>
    <Form.Item name="leader_id" label="负责人ID">
      <InputNumber style={{ width: '100%' }} placeholder="请输入负责人ID" />
    </Form.Item>
    <Form.Item name="status" label="状态" initialValue={1}>
      <Select>
        <Select.Option value={1}>启用</Select.Option>
        <Select.Option value={0}>禁用</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

export default function Organizations() {
  const [data, setData] = useState<Organization[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<Organization | null>(null)
  const [form] = Form.useForm()
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })

  const fetchData = useCallback(async (page = 1, pageSize = 20) => {
    setLoading(true)
    try {
      const res: any = await api.get('/masterdata/organizations', { params: { page, page_size: pageSize } })
      setData(res.data?.items || [])
      setPagination({ current: res.data?.page || 1, pageSize: res.data?.page_size || 20, total: res.data?.total || 0 })
    } catch (error) {
      message.error('加载数据失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
  }, [fetchData])

  const handleAdd = () => {
    setEditingItem(null)
    form.resetFields()
    setModalVisible(true)
  }

  const handleEdit = (item: Organization) => {
    setEditingItem(item)
    form.setFieldsValue(item)
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/masterdata/organizations/${id}`)
      message.success('删除成功')
      fetchData(pagination.current, pagination.pageSize)
    } catch (error) {
      message.error('删除失败')
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editingItem) {
        await api.put(`/masterdata/organizations/${editingItem.id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/masterdata/organizations', values)
        message.success('创建成功')
      }
      setModalVisible(false)
      form.resetFields()
      fetchData(pagination.current, pagination.pageSize)
    } catch (error) {
      message.error('操作失败')
    }
  }

  const columns = [
    { title: '组织编码', dataIndex: 'org_code', key: 'org_code' },
    { title: '组织名称', dataIndex: 'org_name', key: 'org_name' },
    { title: '组织类型', dataIndex: 'org_type', key: 'org_type' },
    { title: '父级ID', dataIndex: 'parent_id', key: 'parent_id' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: any, record: Organization) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)} okText="确认" cancelText="取消">
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
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={() => fetchData()}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增</Button>
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
          scroll={{ x: 800 }}
          size="small"
          pagination={{
            ...pagination,
            showSizeChanger: true,
            showTotal: (total: number) => `共 ${total} 条`,
            onChange: (page, pageSize) => fetchData(page, pageSize),
            pageSizeOptions: ['20', '50', '100'],
          }}
        />
      </div>
      <Modal
        title={editingItem ? '编辑组织主数据' : '新增组织主数据'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
      >
        <OrganizationForm form={form} />
      </Modal>
    </div>
  )
}
