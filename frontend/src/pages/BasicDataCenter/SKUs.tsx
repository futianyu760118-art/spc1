import { useState, useCallback, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber, message,
  Space, Popconfirm, Row, Col,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import api from '../../services/api'
import PermButton from '../../components/PermButton'
import { useAuthStore } from '../../store/auth'

interface SKU {
  id: number
  sku_code: string
  material_id: number
  sku_name: string
  attr_json?: string
  barcode?: string
  gross_weight?: number
  net_weight?: number
  volume?: number
  create_time: string
}

const SKUForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="sku_code" label="SKU编码" rules={[{ required: true }]}>
      <Input placeholder="请输入SKU编码" />
    </Form.Item>
    <Form.Item name="material_id" label="关联物料ID" rules={[{ required: true }]}>
      <InputNumber style={{ width: '100%' }} placeholder="请输入关联物料ID" />
    </Form.Item>
    <Form.Item name="sku_name" label="SKU名称" rules={[{ required: true }]}>
      <Input placeholder="请输入SKU名称" />
    </Form.Item>
    <Form.Item name="attr_json" label="属性JSON">
      <Input.TextArea placeholder="请输入属性JSON" rows={3} />
    </Form.Item>
    <Form.Item name="barcode" label="条形码">
      <Input placeholder="请输入条形码" />
    </Form.Item>
    <Form.Item name="gross_weight" label="毛重(KG)">
      <InputNumber style={{ width: '100%' }} placeholder="请输入毛重" />
    </Form.Item>
    <Form.Item name="net_weight" label="净重(KG)">
      <InputNumber style={{ width: '100%' }} placeholder="请输入净重" />
    </Form.Item>
    <Form.Item name="volume" label="体积(CBM)">
      <InputNumber style={{ width: '100%' }} placeholder="请输入体积" />
    </Form.Item>
  </Form>
)

export default function SKUs() {
  const [data, setData] = useState<SKU[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<SKU | null>(null)
  const [form] = Form.useForm()
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const hasPermission = useAuthStore(s => s.hasPermission)
  const canCreate = hasPermission('basicdata.data.skus', 'create')
  const canUpdate = hasPermission('basicdata.data.skus', 'update')
  const canDelete = hasPermission('basicdata.data.skus', 'delete')

  const fetchData = useCallback(async (page = 1, pageSize = 20) => {
    setLoading(true)
    try {
      const res: any = await api.get('/basicdata/skus', { params: { page, page_size: pageSize } })
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

  const handleEdit = (item: SKU) => {
    setEditingItem(item)
    form.setFieldsValue(item)
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/basicdata/skus/${id}`)
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
        await api.put(`/basicdata/skus/${editingItem.id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/basicdata/skus', values)
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
    { title: 'SKU编码', dataIndex: 'sku_code', key: 'sku_code' },
    { title: 'SKU名称', dataIndex: 'sku_name', key: 'sku_name' },
    { title: '关联物料ID', dataIndex: 'material_id', key: 'material_id' },
    { title: '条形码', dataIndex: 'barcode', key: 'barcode' },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: any, record: SKU) => (
        <Space size="small">
          <PermButton permResource="basicdata.data.skus" permAction="update" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)} okText="确认" cancelText="取消" disabled={!canDelete}>
            <PermButton permResource="basicdata.data.skus" permAction="delete" size="small" danger icon={<DeleteOutlined />} />
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
              <PermButton permResource="basicdata.data.skus" permAction="create" type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增</PermButton>
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
        title={editingItem ? '编辑SKU' : '新增SKU'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
      >
        <SKUForm form={form} />
      </Modal>
    </div>
  )
}
