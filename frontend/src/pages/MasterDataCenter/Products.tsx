import { useState, useCallback, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber, message,
  Space, Popconfirm, Row, Col,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import api from '../../services/api'

interface Product {
  id: number
  product_code: string
  product_line?: string
  tech_version?: string
  bom_version?: string
  default_warehouse?: string
  warranty_days?: number
  create_time: string
  update_time?: string
}

const ProductForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="product_code" label="产品编码" rules={[{ required: true }]}>
      <Input placeholder="请输入产品编码" />
    </Form.Item>
    <Form.Item name="product_line" label="产品线">
      <Input placeholder="请输入产品线" />
    </Form.Item>
    <Form.Item name="tech_version" label="技术版本">
      <Input placeholder="请输入技术版本" />
    </Form.Item>
    <Form.Item name="bom_version" label="BOM版本号">
      <Input placeholder="请输入BOM版本号" />
    </Form.Item>
    <Form.Item name="default_warehouse" label="默认仓库">
      <Input placeholder="请输入默认仓库" />
    </Form.Item>
    <Form.Item name="warranty_days" label="质保天数">
      <InputNumber style={{ width: '100%' }} placeholder="请输入质保天数" />
    </Form.Item>
  </Form>
)

export default function Products() {
  const [data, setData] = useState<Product[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<Product | null>(null)
  const [form] = Form.useForm()
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })

  const fetchData = useCallback(async (page = 1, pageSize = 20) => {
    setLoading(true)
    try {
      const res: any = await api.get('/masterdata/products', { params: { page, page_size: pageSize } })
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

  const handleEdit = (item: Product) => {
    setEditingItem(item)
    form.setFieldsValue(item)
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/masterdata/products/${id}`)
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
        await api.put(`/masterdata/products/${editingItem.id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/masterdata/products', values)
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
    { title: '产品编码', dataIndex: 'product_code', key: 'product_code' },
    { title: '产品线', dataIndex: 'product_line', key: 'product_line' },
    { title: '技术版本', dataIndex: 'tech_version', key: 'tech_version' },
    { title: 'BOM版本', dataIndex: 'bom_version', key: 'bom_version' },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: any, record: Product) => (
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
          scroll={{ x: 700 }}
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
        title={editingItem ? '编辑产品主数据' : '新增产品主数据'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
      >
        <ProductForm form={form} />
      </Modal>
    </div>
  )
}
