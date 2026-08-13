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

interface Warehouse {
  id: number
  wh_code: string
  wh_name: string
  wh_type: string
  address?: string
  manager_id?: number
  is_enabled: number
  create_time: string
}

const WarehouseForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="wh_code" label="仓库编码" rules={[{ required: true }]}>
      <Input placeholder="请输入仓库编码" />
    </Form.Item>
    <Form.Item name="wh_name" label="仓库名称" rules={[{ required: true }]}>
      <Input placeholder="请输入仓库名称" />
    </Form.Item>
    <Form.Item name="wh_type" label="仓库类型" rules={[{ required: true }]}>
      <Select placeholder="请选择仓库类型">
        <Select.Option value="原料仓">原料仓</Select.Option>
        <Select.Option value="成品仓">成品仓</Select.Option>
        <Select.Option value="包材仓">包材仓</Select.Option>
        <Select.Option value="线边仓">线边仓</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="address" label="仓库地址">
      <Input placeholder="请输入仓库地址" />
    </Form.Item>
    <Form.Item name="manager_id" label="仓库管理员ID">
      <InputNumber style={{ width: '100%' }} placeholder="请输入仓库管理员ID" />
    </Form.Item>
    <Form.Item name="is_enabled" label="是否启用" initialValue={1}>
      <Select>
        <Select.Option value={1}>启用</Select.Option>
        <Select.Option value={0}>禁用</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

export default function Warehouses() {
  const [data, setData] = useState<Warehouse[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<Warehouse | null>(null)
  const [form] = Form.useForm()
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const hasPermission = useAuthStore(s => s.hasPermission)
  const canCreate = hasPermission('basicdata.data.warehouses', 'create')
  const canUpdate = hasPermission('basicdata.data.warehouses', 'update')
  const canDelete = hasPermission('basicdata.data.warehouses', 'delete')

  const fetchData = useCallback(async (page = 1, pageSize = 20) => {
    setLoading(true)
    try {
      const res: any = await api.get('/basicdata/warehouses', { params: { page, page_size: pageSize } })
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

  const handleEdit = (item: Warehouse) => {
    setEditingItem(item)
    form.setFieldsValue(item)
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/basicdata/warehouses/${id}`)
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
        await api.put(`/basicdata/warehouses/${editingItem.id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/basicdata/warehouses', values)
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
    { title: '仓库编码', dataIndex: 'wh_code', key: 'wh_code' },
    { title: '仓库名称', dataIndex: 'wh_name', key: 'wh_name' },
    { title: '仓库类型', dataIndex: 'wh_type', key: 'wh_type' },
    {
      title: '状态',
      dataIndex: 'is_enabled',
      key: 'is_enabled',
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: any, record: Warehouse) => (
        <Space size="small">
          <PermButton permResource="basicdata.data.warehouses" permAction="update" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)} okText="确认" cancelText="取消" disabled={!canDelete}>
            <PermButton permResource="basicdata.data.warehouses" permAction="delete" size="small" danger icon={<DeleteOutlined />} />
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
              <PermButton permResource="basicdata.data.warehouses" permAction="create" type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增</PermButton>
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
        title={editingItem ? '编辑仓库' : '新增仓库'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
      >
        <WarehouseForm form={form} />
      </Modal>
    </div>
  )
}
