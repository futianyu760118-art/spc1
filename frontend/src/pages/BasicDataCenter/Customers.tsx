import { useState, useCallback, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, message,
  Space, Tag, Popconfirm, Row, Col,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import api from '../../services/api'
import PermButton from '../../components/PermButton'
import { useAuthStore } from '../../store/auth'

interface Customer {
  id: number
  customer_code: string
  customer_name: string
  customer_short?: string
  customer_level?: string
  industry_type?: string
  credit_code?: string
  status: number
  create_time: string
  update_time?: string
}

const CustomerForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="customer_code" label="客户编码" rules={[{ required: true }]}>
      <Input placeholder="请输入客户编码" />
    </Form.Item>
    <Form.Item name="customer_name" label="客户名称" rules={[{ required: true }]}>
      <Input placeholder="请输入客户名称" />
    </Form.Item>
    <Form.Item name="customer_short" label="客户简称">
      <Input placeholder="请输入客户简称" />
    </Form.Item>
    <Form.Item name="customer_level" label="客户等级">
      <Select placeholder="请选择客户等级">
        <Select.Option value="A">A类</Select.Option>
        <Select.Option value="B">B类</Select.Option>
        <Select.Option value="C">C类</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="industry_type" label="所属行业">
      <Input placeholder="请输入所属行业" />
    </Form.Item>
    <Form.Item name="credit_code" label="统一社会信用代码">
      <Input placeholder="请输入统一社会信用代码" />
    </Form.Item>
    <Form.Item name="status" label="状态" initialValue={1}>
      <Select>
        <Select.Option value={1}>启用</Select.Option>
        <Select.Option value={0}>禁用</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

export default function Customers() {
  const [data, setData] = useState<Customer[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<Customer | null>(null)
  const [form] = Form.useForm()
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const hasPermission = useAuthStore(s => s.hasPermission)
  const canCreate = hasPermission('basicdata.data.customers', 'create')
  const canUpdate = hasPermission('basicdata.data.customers', 'update')
  const canDelete = hasPermission('basicdata.data.customers', 'delete')

  const fetchData = useCallback(async (page = 1, pageSize = 20) => {
    setLoading(true)
    try {
      const res: any = await api.get('/basicdata/customers', { params: { page, page_size: pageSize } })
      setData(res.data?.items || [])
      setPagination({ current: res.data?.page || 1, pageSize: res.data?.page_size || 20, total: res.data?.total || 0 })
    } catch (error) {
      // 错误已由全局拦截器提示
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

  const handleEdit = (item: Customer) => {
    setEditingItem(item)
    form.setFieldsValue(item)
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/basicdata/customers/${id}`)
      message.success('删除成功')
      fetchData(pagination.current, pagination.pageSize)
    } catch (error) {
      // 错误已由全局拦截器提示
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editingItem) {
        await api.put(`/basicdata/customers/${editingItem.id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/basicdata/customers', values)
        message.success('创建成功')
      }
      setModalVisible(false)
      form.resetFields()
      fetchData(pagination.current, pagination.pageSize)
    } catch (error) {
      // 错误已由全局拦截器提示
    }
  }

  const columns = [
    { title: '客户编码', dataIndex: 'customer_code', key: 'customer_code' },
    { title: '客户名称', dataIndex: 'customer_name', key: 'customer_name' },
    { title: '客户简称', dataIndex: 'customer_short', key: 'customer_short' },
    { title: '客户等级', dataIndex: 'customer_level', key: 'customer_level' },
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
      render: (_: any, record: Customer) => (
        <Space size="small">
          <PermButton permResource="basicdata.data.customers" permAction="update" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)} okText="确认" cancelText="取消" disabled={!canDelete}>
            <PermButton permResource="basicdata.data.customers" permAction="delete" size="small" danger icon={<DeleteOutlined />} />
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
              <PermButton permResource="basicdata.data.customers" permAction="create" type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增</PermButton>
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
        title={editingItem ? '编辑客户' : '新增客户'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
      >
        <CustomerForm form={form} />
      </Modal>
    </div>
  )
}
