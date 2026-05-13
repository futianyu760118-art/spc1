import { useEffect, useState } from 'react'
import { Table, Button, Modal, Form, Input, InputNumber, Select, Space, Tag, message, Popconfirm, Switch, ColorPicker, Row, Col } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons'
import { statusDictApi } from '../../services/api'
import { formatDateTime } from '../../utils'

const statusTypeOptions = [
  { value: 'order_status', label: '订单状态' },
  { value: 'risk_level', label: '风险等级' },
  { value: 'po_status', label: '采购单状态' },
  { value: 'issue_status', label: '异常状态' },
  { value: 'production_status', label: '生产状态' },
]
const colorTagOptions = [
  { value: 'red', label: '红色' },
  { value: 'yellow', label: '黄色' },
  { value: 'green', label: '绿色' },
  { value: 'white', label: '白色' },
  { value: 'blue', label: '蓝色' },
  { value: 'orange', label: '橙色' },
  { value: 'gray', label: '灰色' },
]

const tagColorMap: Record<string, string> = {
  red: 'red', yellow: 'gold', green: 'green', white: 'default',
  blue: 'blue', orange: 'orange', gray: 'default',
}

export default function StatusDictionary() {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [form] = Form.useForm()
  const [filterType, setFilterType] = useState<string | undefined>()

  const fetchData = async () => {
    setLoading(true)
    try {
      const params: any = {}
      if (filterType) params.status_type = filterType
      const res: any = await statusDictApi.list(params)
      setData(res.data || [])
    } catch {
      message.error('获取状态字典失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [filterType])

  const openAdd = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ sort_order: 0, is_active: true, color_tag: 'green' })
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
        await statusDictApi.update(editing.id, values)
        message.success('更新成功')
      } else {
        await statusDictApi.create(values)
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
      await statusDictApi.delete(id)
      message.success('删除成功')
      fetchData()
    } catch {
      message.error('删除失败')
    }
  }

  const columns = [
    {
      title: '状态类型', dataIndex: 'status_type', key: 'status_type', width: 130,
      render: (v: string) => {
        const opt = statusTypeOptions.find(o => o.value === v)
        return <Tag color="blue">{opt?.label || v}</Tag>
      },
    },
    { title: '状态代码', dataIndex: 'code', key: 'code', width: 120 },
    { title: '状态名称', dataIndex: 'name', key: 'name', width: 120 },
    {
      title: '颜色标签', dataIndex: 'color_tag', key: 'color_tag', width: 100,
      render: (v: string) => <Tag color={tagColorMap[v] || 'default'}>{v}</Tag>,
    },
    {
      title: '显示颜色', dataIndex: 'display_color', key: 'display_color', width: 110,
      render: (v: string) => v ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 18, height: 18, borderRadius: 4, background: v, border: '1px solid #e2e8f0' }} />
          <span style={{ fontSize: 12, color: '#64748b' }}>{v}</span>
        </div>
      ) : '—',
    },
    { title: '排序', dataIndex: 'sort_order', key: 'sort_order', width: 70 },
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
              placeholder="按类型筛选"
              allowClear
              style={{ width: 160 }}
              options={statusTypeOptions}
              onChange={(v) => setFilterType(v)}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>新建状态</Button>
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
        title={editing ? '编辑状态字典' : '新建状态字典'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        width={520}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="status_type" label="状态类型" rules={[{ required: true, message: '请选择' }]}>
            <Select options={statusTypeOptions} placeholder="选择类型" />
          </Form.Item>
          <Form.Item name="code" label="状态代码" rules={[{ required: true, message: '请输入' }]}>
            <Input placeholder="如 on_time, delayed" />
          </Form.Item>
          <Form.Item name="name" label="状态名称" rules={[{ required: true, message: '请输入' }]}>
            <Input placeholder="如 正常、延迟" />
          </Form.Item>
          <Form.Item name="color_tag" label="颜色标签" rules={[{ required: true, message: '请选择' }]}>
            <Select options={colorTagOptions} placeholder="选择颜色" />
          </Form.Item>
          <Form.Item name="display_color" label="自定义颜色值">
            <Input placeholder="如 #FF0000（可选）" />
          </Form.Item>
          <Form.Item name="sort_order" label="排序号">
            <InputNumber min={0} max={999} className="w-full" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
