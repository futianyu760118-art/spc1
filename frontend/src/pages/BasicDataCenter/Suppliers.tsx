import { useState, useCallback, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, message,
  Space, Tag, Popconfirm, Row, Col,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import api from '../../services/api'

interface Supplier {
  id: number
  supplier_code: string
  supplier_name: string
  supplier_short?: string
  supplier_type?: string
  contact_person?: string
  contact_phone?: string
  payment_terms?: string
  status: number
  create_time: string
  update_time?: string
}

const SupplierForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="supplier_code" label="供应商编码" rules={[{ required: true }]}>
      <Input placeholder="请输入供应商编码" />
    </Form.Item>
    <Form.Item name="supplier_name" label="供应商名称" rules={[{ required: true }]}>
      <Input placeholder="请输入供应商名称" />
    </Form.Item>
    <Form.Item name="supplier_short" label="供应商简称">
      <Input placeholder="请输入供应商简称" />
    </Form.Item>
    <Form.Item name="supplier_type" label="供应商类型">
      <Input placeholder="请输入供应商类型" />
    </Form.Item>
    <Form.Item name="contact_person" label="联系人">
      <Input placeholder="请输入联系人" />
    </Form.Item>
    <Form.Item name="contact_phone" label="联系电话">
      <Input placeholder="请输入联系电话" />
    </Form.Item>
    <Form.Item name="payment_terms" label="付款条款">
      <Input placeholder="请输入付款条款" />
    </Form.Item>
    <Form.Item name="status" label="状态" initialValue={1}>
      <Select>
        <Select.Option value={1}>启用</Select.Option>
        <Select.Option value={0}>禁用</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

export default function Suppliers() {
  const [data, setData] = useState<Supplier[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<Supplier | null>(null)
  const [form] = Form.useForm()
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })

  const fetchData = useCallback(async (page = 1, pageSize = 20) => {
    setLoading(true)
    try {
      const res: any = await api.get('/basicdata/suppliers', { params: { page, page_size: pageSize } })
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

  const handleEdit = (item: Supplier) => {
    setEditingItem(item)
    form.setFieldsValue(item)
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/basicdata/suppliers/${id}`)
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
        await api.put(`/basicdata/suppliers/${editingItem.id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/basicdata/suppliers', values)
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
    { title: '供应商编码', dataIndex: 'supplier_code', key: 'supplier_code' },
    { title: '供应商名称', dataIndex: 'supplier_name', key: 'supplier_name' },
    { title: '供应商类型', dataIndex: 'supplier_type', key: 'supplier_type' },
    { title: '联系人', dataIndex: 'contact_person', key: 'contact_person' },
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
      render: (_: any, record: Supplier) => (
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
        title={editingItem ? '编辑供应商' : '新增供应商'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
      >
        <SupplierForm form={form} />
      </Modal>
    </div>
  )
}
