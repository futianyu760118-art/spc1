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
import { EMPLOYEE_STATUS_OPTIONS, getEmployeeStatusMeta } from '../../constants/employeeStatus'

interface Employee {
  id: number
  emp_code: string
  emp_name: string
  org_id: number
  position_id?: number
  position?: string
  position_name?: string
  oa_user_id?: string
  manager_oa_user_id?: string
  manager_name?: string
  phone?: string
  email?: string
  status: number
  create_time: string
}

interface Position {
  id: number
  position_code: string
  position_name: string
  status: number
}

const EmployeeForm = ({ form, positions, employees }: { form: any, positions: Position[], employees: Employee[] }) => (
  <Form form={form} layout="vertical">
    <Form.Item name="emp_code" label="员工工号" rules={[{ required: true }]}>
      <Input placeholder="请输入员工工号" />
    </Form.Item>
    <Form.Item name="emp_name" label="员工姓名" rules={[{ required: true }]}>
      <Input placeholder="请输入员工姓名" />
    </Form.Item>
    <Form.Item name="org_id" label="所属组织ID" rules={[{ required: true }]}>
      <InputNumber style={{ width: '100%' }} placeholder="请输入所属组织ID" />
    </Form.Item>
    <Form.Item name="position_id" label="岗位">
      <Select
        allowClear
        showSearch
        placeholder="请选择岗位"
        optionFilterProp="label"
        options={positions.map(position => ({
          value: position.id,
          label: `${position.position_name} (${position.position_code})`,
        }))}
      />
    </Form.Item>
    <Form.Item name="manager_oa_user_id" label="上级人员">
      <Select
        allowClear
        showSearch
        placeholder="请选择上级人员"
        optionFilterProp="label"
        options={employees
          .filter(emp => emp.emp_code)
          .map(emp => ({
            value: emp.oa_user_id || emp.emp_code,
            label: `${emp.emp_name} (${emp.emp_code})`,
          }))}
      />
    </Form.Item>
    <Form.Item name="phone" label="手机号">
      <Input placeholder="请输入手机号" />
    </Form.Item>
    <Form.Item name="email" label="邮箱">
      <Input placeholder="请输入邮箱" />
    </Form.Item>
    <Form.Item name="status" label="状态" initialValue={1}>
      <Select>
        {EMPLOYEE_STATUS_OPTIONS.map(option => (
          <Select.Option key={option.value} value={option.value}>{option.label}</Select.Option>
        ))}
      </Select>
    </Form.Item>
  </Form>
)

export default function Employees() {
  const [data, setData] = useState<Employee[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<Employee | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [form] = Form.useForm()
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const hasPermission = useAuthStore(s => s.hasPermission)
  const canCreate = hasPermission('basicdata.data.employees', 'create')
  const canUpdate = hasPermission('basicdata.data.employees', 'update')
  const canDelete = hasPermission('basicdata.data.employees', 'delete')

  const fetchData = useCallback(async (page = 1, pageSize = 20) => {
    setLoading(true)
    try {
      const res: any = await api.get('/basicdata/employees', { params: { page, page_size: pageSize } })
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

  useEffect(() => {
    const fetchPositions = async () => {
      try {
        const res: any = await api.get('/basicdata/positions', { params: { page: 1, page_size: 100, status: '1' } })
        setPositions(res.data?.items || [])
      } catch {
        message.error('加载岗位列表失败')
      }
    }
    fetchPositions()
  }, [])

  const handleAdd = () => {
    setEditingItem(null)
    form.resetFields()
    setModalVisible(true)
  }

  const handleEdit = (item: Employee) => {
    setEditingItem(item)
    form.setFieldsValue(item)
    setModalVisible(true)
  }

  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/basicdata/employees/${id}`)
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
        await api.put(`/basicdata/employees/${editingItem.id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/basicdata/employees', values)
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
    { title: '员工工号', dataIndex: 'emp_code', key: 'emp_code' },
    { title: '员工姓名', dataIndex: 'emp_name', key: 'emp_name' },
    { title: '所属组织ID', dataIndex: 'org_id', key: 'org_id' },
    {
      title: '岗位',
      dataIndex: 'position_name',
      key: 'position_name',
      render: (_: any, record: Employee) => record.position_name || record.position || '-',
    },
    {
      title: '上级',
      dataIndex: 'manager_name',
      key: 'manager_name',
      render: (text: string) => text || '-',
    },
    { title: '手机号', dataIndex: 'phone', key: 'phone' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: number) => {
        const meta = getEmployeeStatusMeta(status)
        return <Tag color={meta.color}>{meta.label}</Tag>
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_: any, record: Employee) => (
        <Space size="small">
          <PermButton permResource="basicdata.data.employees" permAction="update" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)} okText="确认" cancelText="取消" disabled={!canDelete}>
            <PermButton permResource="basicdata.data.employees" permAction="delete" size="small" danger icon={<DeleteOutlined />} />
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
              <PermButton permResource="basicdata.data.employees" permAction="create" type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增</PermButton>
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
          scroll={{ x: 1000 }}
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
        title={editingItem ? '编辑人员' : '新增人员'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
      >
        <EmployeeForm form={form} positions={positions} employees={data} />
      </Modal>
    </div>
  )
}
