import { useEffect, useState } from 'react'
import { Table, Button, Modal, Form, Input, InputNumber, Select, Space, Tag, message, Popconfirm, Switch, Row, Col } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons'
import { responsibilityApi, inspectionRuleApi } from '../../services/api'
import { formatDateTime } from '../../utils'

const escalationLabels: Record<number, string> = { 0: '不升级', 1: '主管', 2: '经理', 3: '总监' }
const escalationColors: Record<number, string> = { 0: 'default', 1: 'blue', 2: 'orange', 3: 'red' }

export default function ResponsibilityMap() {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [form] = Form.useForm()
  const [filterDept, setFilterDept] = useState<string | undefined>()
  const [ruleOptions, setRuleOptions] = useState<{ value: string; label: string }[]>([])

  const fetchData = async () => {
    setLoading(true)
    try {
      const params: any = {}
      if (filterDept) params.department = filterDept
      const res: any = await responsibilityApi.list(params)
      setData(res.data || [])
    } catch {
      message.error('获取责任归属失败')
    } finally {
      setLoading(false)
    }
  }

  const fetchRuleOptions = async () => {
    try {
      const res: any = await inspectionRuleApi.list({})
      const items = res.data || []
      setRuleOptions(items.map((r: any) => ({ value: r.item_code, label: `${r.item_code} - ${r.item_name}` })))
    } catch { /* ignore */ }
  }

  useEffect(() => { fetchData(); fetchRuleOptions() }, [filterDept])

  const departments = [...new Set(data.map((d: any) => d.department))].filter(Boolean)

  const openAdd = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ escalation_level: 0, is_active: true })
    setModalOpen(true)
  }

  const openEdit = (record: any) => {
    setEditing(record)
    form.setFieldsValue(record)
    setModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      if (editing) {
        await responsibilityApi.update(editing.id, values)
        message.success('更新成功')
      } else {
        await responsibilityApi.create(values)
        message.success('创建成功')
      }
      setModalOpen(false)
      fetchData()
    } catch {
      message.error('保存失败')
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await responsibilityApi.delete(id)
      message.success('删除成功')
      fetchData()
    } catch {
      message.error('删除失败')
    }
  }

  const columns = [
    { title: '关联点检项', dataIndex: 'rule_item_code', key: 'rule_item_code', width: 160 },
    { title: '责任部门', dataIndex: 'department', key: 'department', width: 120 },
    { title: '责任角色', dataIndex: 'role_name', key: 'role_name', width: 120 },
    { title: '指定人员', key: 'user', width: 140, render: (_: any, r: any) => r.user_name || r.user_id || '—' },
    {
      title: '升级层级', dataIndex: 'escalation_level', key: 'escalation_level', width: 100,
      render: (v: number) => <Tag color={escalationColors[v] || 'default'}>{escalationLabels[v] ?? `L${v}`}</Tag>,
    },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80,
      render: (v: boolean) => v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag>,
    },
    { title: '更新时间', dataIndex: 'updated_at', key: 'updated_at', width: 170,
      render: (v: string) => formatDateTime(v),
    },
    {
      title: '操作', key: 'action', width: 120, fixed: 'right' as const,
      render: (_: any, record: any) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} />
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
          <Col>
            <Select
              placeholder="按部门筛选"
              allowClear
              style={{ width: 160 }}
              options={departments.map(d => ({ value: d, label: d }))}
              onChange={(v) => setFilterDept(v)}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>新建归属</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          columns={columns}
          dataSource={data}
          rowKey="id"
          loading={loading}
          size="small"
          scroll={{ x: 1100 }}
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条`, pageSizeOptions: ['20', '50', '100'] }}
        />
      </div>

      <Modal
        title={editing ? '编辑责任归属' : '新建责任归属'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        width={520}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="rule_item_code" label="关联点检项" rules={[{ required: true, message: '请选择' }]}>
            <Select
              showSearch
              options={ruleOptions}
              placeholder="选择或搜索点检项编码"
              filterOption={(input, option) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
            />
          </Form.Item>
          <Form.Item name="department" label="责任部门" rules={[{ required: true, message: '请输入' }]}>
            <Input placeholder="如 采购部" />
          </Form.Item>
          <Form.Item name="role_name" label="责任角色" rules={[{ required: true, message: '请输入' }]}>
            <Input placeholder="如 采购员" />
          </Form.Item>
          <Form.Item name="user_name" label="指定人员（可选）">
            <Input placeholder="如 张三" />
          </Form.Item>
          <Form.Item name="user_id" label="用户ID（可选）">
            <Input placeholder="如 zhangsan" />
          </Form.Item>
          <Form.Item name="escalation_level" label="升级层级">
            <Select options={[
              { value: 0, label: '不升级' },
              { value: 1, label: '主管' },
              { value: 2, label: '经理' },
              { value: 3, label: '总监' },
            ]} />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
