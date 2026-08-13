import { useEffect, useState } from 'react'
import { Table, Button, Modal, Form, Input, InputNumber, Select, Space, Tag, message, Popconfirm, Switch, Row, Col } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons'
import { nodeStandardApi } from '../../services/api'
import { formatDateTime } from '../../utils'

const sceneOptions = [
  { value: '内销', label: '内销' },
  { value: '外销', label: '外销' },
  { value: '标准品', label: '标准品' },
  { value: '新品', label: '新品' },
  { value: '通用', label: '通用' },
]
const unitOptions = [
  { value: '天', label: '天' },
  { value: '小时', label: '小时' },
]

const sceneColor: Record<string, string> = {
  '内销': 'blue', '外销': 'green', '标准品': 'orange', '新品': 'purple', '通用': 'default',
}

export default function NodeStandards() {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [form] = Form.useForm()
  const [filterScene, setFilterScene] = useState<string | undefined>()

  const fetchData = async () => {
    setLoading(true)
    try {
      const params: any = {}
      if (filterScene) params.applicable_scene = filterScene
      const res: any = await nodeStandardApi.list(params)
      setData(res.data || [])
    } catch {
      // 错误已由全局拦截器提示
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [filterScene])

  const openAdd = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ time_unit: '天', is_active: true })
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
        await nodeStandardApi.update(editing.id, values)
        message.success('更新成功')
      } else {
        await nodeStandardApi.create(values)
        message.success('创建成功')
      }
      setModalOpen(false)
      fetchData()
    } catch {
      // 错误已由全局拦截器提示
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await nodeStandardApi.delete(id)
      message.success('删除成功')
      fetchData()
    } catch {
      // 错误已由全局拦截器提示
    }
  }

  const columns = [
    { title: '节点编码', dataIndex: 'node_code', key: 'node_code', width: 140 },
    { title: '节点名称', dataIndex: 'node_name', key: 'node_name', ellipsis: true },
    {
      title: '标准值', key: 'time', width: 120,
      render: (_: any, r: any) => <span style={{ fontWeight: 600, color: '#6366f1' }}>{r.time_value} {r.time_unit}</span>,
    },
    {
      title: '适用场景', dataIndex: 'applicable_scene', key: 'applicable_scene', width: 110,
      render: (v: string) => <Tag color={sceneColor[v] || 'default'}>{v}</Tag>,
    },
    { title: '描述', dataIndex: 'description', key: 'description', ellipsis: true, render: (v: string) => v || '—' },
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
              placeholder="按场景筛选"
              allowClear
              style={{ width: 160 }}
              options={sceneOptions}
              onChange={(v) => setFilterScene(v)}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>新建标准</Button>
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
          scroll={{ x: 1000 }}
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条`, pageSizeOptions: ['20', '50', '100'] }}
        />
      </div>

      <Modal
        title={editing ? '编辑节点标准' : '新建节点标准'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        width={520}
      >
        <Form form={form} layout="vertical">
          {!editing && (
            <Form.Item name="node_code" label="节点编码" rules={[{ required: true, message: '请输入编码' }]}>
              <Input placeholder="如 PREP_CYCLE" />
            </Form.Item>
          )}
          <Form.Item name="node_name" label="节点名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如 备料周期" />
          </Form.Item>
          <Space size="middle" style={{ width: '100%' }}>
            <Form.Item name="time_value" label="标准值" rules={[{ required: true, message: '请输入' }]} style={{ flex: 1 }}>
              <InputNumber min={0} max={999} className="w-full" placeholder="如 3" style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="time_unit" label="单位" rules={[{ required: true }]} style={{ width: 120 }}>
              <Select options={unitOptions} />
            </Form.Item>
          </Space>
          <Form.Item name="applicable_scene" label="适用场景" rules={[{ required: true, message: '请选择' }]}>
            <Select options={sceneOptions} placeholder="选择场景" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="可选描述" />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
