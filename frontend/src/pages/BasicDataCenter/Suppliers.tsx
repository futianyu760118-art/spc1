import { useState, useCallback, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, InputNumber, message,
  Space, Tag, Popconfirm, Row, Col,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import api from '../../services/api'
import PermButton from '../../components/PermButton'
import { useAuthStore } from '../../store/auth'

interface Supplier {
  id: number
  supplier_code: string
  supplier_name: string
  supplier_short?: string
  supplier_type?: string
  contact_person?: string
  contact_phone?: string
  fax?: string
  address?: string
  erp_supply_id?: number
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
    <Form.Item name="fax" label="传真">
      <Input placeholder="请输入传真" />
    </Form.Item>
    <Form.Item name="address" label="地址">
      <Input placeholder="请输入地址" />
    </Form.Item>
    <Form.Item name="erp_supply_id" label="ERP供应商ID">
      <InputNumber style={{ width: '100%' }} placeholder="请输入ERP内部ID" />
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
  const hasPermission = useAuthStore(s => s.hasPermission)
  const canCreate = hasPermission('basicdata.data.suppliers', 'create')
  const canUpdate = hasPermission('basicdata.data.suppliers', 'update')
  const canDelete = hasPermission('basicdata.data.suppliers', 'delete')

  const fetchData = useCallback(async (page = 1, pageSize = 20) => {
    setLoading(true)
    try {
      const res: any = await api.get('/basicdata/suppliers', { params: { page, page_size: pageSize } })
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
      // 错误已由全局拦截器提示
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
      // 错误已由全局拦截器提示
    }
  }

  const columns = [
    { title: '供应商编码', dataIndex: 'supplier_code', key: 'supplier_code', width: 140 },
    { title: '供应商名称', dataIndex: 'supplier_name', key: 'supplier_name', width: 200, ellipsis: true },
    { title: '简称', dataIndex: 'supplier_short', key: 'supplier_short', width: 120, ellipsis: true },
    { title: '类型', dataIndex: 'supplier_type', key: 'supplier_type', width: 100 },
    { title: '联系人', dataIndex: 'contact_person', key: 'contact_person', width: 100 },
    { title: '电话', dataIndex: 'contact_phone', key: 'contact_phone', width: 130 },
    { title: '传真', dataIndex: 'fax', key: 'fax', width: 130 },
    { title: '地址', dataIndex: 'address', key: 'address', width: 200, ellipsis: true },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 80,
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      fixed: 'right' as const,
      render: (_: any, record: Supplier) => (
        <Space size="small">
          <PermButton permResource="basicdata.data.suppliers" permAction="update" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)} okText="确认" cancelText="取消" disabled={!canDelete}>
            <PermButton permResource="basicdata.data.suppliers" permAction="delete" size="small" danger icon={<DeleteOutlined />} />
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
              <PermButton permResource="basicdata.data.suppliers" permAction="create" type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增</PermButton>
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
          scroll={{ x: 1200 }}
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
        width={640}
      >
        <SupplierForm form={form} />
      </Modal>
    </div>
  )
}
