import { useState, useCallback, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, InputNumber, message,
  Space, Tag, Popconfirm, Row, Col,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import api from '../../services/api'

interface Process {
  id: number
  process_code: string
  process_name: string
  process_group?: string
  standard_hour?: number
  work_center?: string
  is_qc_point: number
  description?: string
}

const ProcessForm = ({ form }: { form: any }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="process_code" label="工序编码" rules={[{ required: true }]}>
      <Input placeholder="请输入工序编码" />
    </Form.Item>
    <Form.Item name="process_name" label="工序名称" rules={[{ required: true }]}>
      <Input placeholder="请输入工序名称" />
    </Form.Item>
    <Form.Item name="process_group" label="工序分组">
      <Input placeholder="请输入工序分组" />
    </Form.Item>
    <Form.Item name="standard_hour" label="标准工时">
      <InputNumber style={{ width: '100%' }} placeholder="请输入标准工时" />
    </Form.Item>
    <Form.Item name="work_center" label="工作中心">
      <Input placeholder="请输入工作中心" />
    </Form.Item>
    <Form.Item name="is_qc_point" label="是否为质检点" initialValue={0}>
      <Select>
        <Select.Option value={1}>是</Select.Option>
        <Select.Option value={0}>否</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="description" label="描述">
      <Input.TextArea placeholder="请输入描述" rows={3} />
    </Form.Item>
  </Form>
)

export default function Processes() {
  const [data, setData] = useState<Process[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<Process | null>(null)
  const [form] = Form.useForm()
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })

  const fetchData = useCallback(async (page = 1, pageSize = 20) => {
    setLoading(true)
    try {
      const res: any = await api.get('/masterdata/processes', { params: { page, page_size: pageSize } })
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

  const handleEdit = (item: Process) => {
    setEditingItem(item)
    form.setFieldsValue(item)
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/masterdata/processes/${id}`)
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
        await api.put(`/masterdata/processes/${editingItem.id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/masterdata/processes', values)
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
    { title: '工序编码', dataIndex: 'process_code', key: 'process_code' },
    { title: '工序名称', dataIndex: 'process_name', key: 'process_name' },
    { title: '工序分组', dataIndex: 'process_group', key: 'process_group' },
    { title: '工作中心', dataIndex: 'work_center', key: 'work_center' },
    {
      title: '质检点',
      dataIndex: 'is_qc_point',
      key: 'is_qc_point',
      render: (qc: number) => <Tag color={qc === 1 ? 'blue' : 'default'}>{qc === 1 ? '是' : '否'}</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: any, record: Process) => (
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
        title={editingItem ? '编辑工序主数据' : '新增工序主数据'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
      >
        <ProcessForm form={form} />
      </Modal>
    </div>
  )
}
