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

interface Location {
  id: number
  location_id: string
  location_group_id?: string
  location_code?: string
  location_name?: string
  location_full_name?: string
  depth?: number
  detail_flag?: number
  parent_id?: string
  is_deleted?: number
  system_type?: number
  data_source?: string
  created_at: string
  updated_at: string
}

const LocationForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="location_id" label="库位ID" rules={[{ required: true }]}>
      <Input placeholder="请输入库位ID" />
    </Form.Item>
    <Form.Item name="location_code" label="库位编码">
      <Input placeholder="请输入库位编码" />
    </Form.Item>
    <Form.Item name="location_name" label="库位名称">
      <Input placeholder="请输入库位名称" />
    </Form.Item>
    <Form.Item name="location_full_name" label="库位全称">
      <Input placeholder="请输入库位全称" />
    </Form.Item>
    <Form.Item name="location_group_id" label="库位分组ID">
      <Input placeholder="请输入库位分组ID" />
    </Form.Item>
    <Form.Item name="parent_id" label="父库位ID">
      <Input placeholder="请输入父库位ID" />
    </Form.Item>
    <Form.Item name="depth" label="层级深度" initialValue={0}>
      <InputNumber style={{ width: '100%' }} placeholder="请输入层级深度" />
    </Form.Item>
    <Form.Item name="detail_flag" label="明细标识" initialValue={0}>
      <Select>
        <Select.Option value={1}>是</Select.Option>
        <Select.Option value={0}>否</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="system_type" label="系统类型" initialValue={0}>
      <InputNumber style={{ width: '100%' }} placeholder="请输入系统类型" />
    </Form.Item>
    <Form.Item name="is_deleted" label="是否删除" initialValue={0}>
      <Select>
        <Select.Option value={1}>是</Select.Option>
        <Select.Option value={0}>否</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

export default function Locations() {
  const [data, setData] = useState<Location[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<Location | null>(null)
  const [form] = Form.useForm()
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const hasPermission = useAuthStore(s => s.hasPermission)
  const canCreate = hasPermission('basicdata.data.locations', 'create')
  const canUpdate = hasPermission('basicdata.data.locations', 'update')
  const canDelete = hasPermission('basicdata.data.locations', 'delete')

  const fetchData = useCallback(async (page = 1, pageSize = 20) => {
    setLoading(true)
    try {
      const res: any = await api.get('/basicdata/locations', { params: { page, page_size: pageSize } })
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

  const handleEdit = (item: Location) => {
    setEditingItem(item)
    form.setFieldsValue(item)
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/basicdata/locations/${id}`)
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
        await api.put(`/basicdata/locations/${editingItem.id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/basicdata/locations', values)
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
    { title: '库位ID', dataIndex: 'location_id', key: 'location_id' },
    { title: '库位编码', dataIndex: 'location_code', key: 'location_code' },
    { title: '库位名称', dataIndex: 'location_name', key: 'location_name' },
    { title: '库位全称', dataIndex: 'location_full_name', key: 'location_full_name' },
    { title: '层级', dataIndex: 'depth', key: 'depth' },
    {
      title: '明细',
      dataIndex: 'detail_flag',
      key: 'detail_flag',
      render: (flag: number) => (
        <Tag color={flag === 1 ? 'blue' : 'default'}>{flag === 1 ? '是' : '否'}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: any, record: Location) => (
        <Space size="small">
          <PermButton permResource="basicdata.data.locations" permAction="update" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)} okText="确认" cancelText="取消" disabled={!canDelete}>
            <PermButton permResource="basicdata.data.locations" permAction="delete" size="small" danger icon={<DeleteOutlined />} />
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
              <PermButton permResource="basicdata.data.locations" permAction="create" type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增</PermButton>
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
          scroll={{ x: 900 }}
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
        title={editingItem ? '编辑库位' : '新增库位'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
      >
        <LocationForm form={form} />
      </Modal>
    </div>
  )
}