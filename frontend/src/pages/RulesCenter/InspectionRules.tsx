import { useEffect, useState } from 'react'
import { Table, Button, Modal, Form, Input, Select, Space, Tag, message, Popconfirm, Switch, Row, Col } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined } from '@ant-design/icons'
import { inspectionRuleApi } from '../../services/api'
import { formatDateTime } from '../../utils'

const moduleOptions = [
  { value: 'order', label: '订单交付' },
  { value: 'material', label: '物料齐套' },
  { value: 'assembly', label: '组装生产' },
  { value: 'quality', label: '品质检验' },
  { value: 'packaging', label: '包装出货' },
]

const ruleTypeOptions = [
  { value: '预警规则', label: '预警规则' },
  { value: '责任规则', label: '责任规则' },
  { value: '节点标准', label: '节点标准' },
]

const moduleLabel: Record<string, string> = {
  order: '订单交付', material: '物料齐套', assembly: '组装生产',
  quality: '品质检验', packaging: '包装出货',
}
const moduleColor: Record<string, string> = {
  order: 'blue', material: 'green', assembly: 'orange',
  quality: 'purple', packaging: 'cyan',
}

export default function InspectionRules() {
  const [data, setData] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState<any>(null)
  const [form] = Form.useForm()
  const [filterModule, setFilterModule] = useState<string | undefined>()

  const fetchData = async () => {
    setLoading(true)
    try {
      const params: any = {}
      if (filterModule) params.module_code = filterModule
      const res: any = await inspectionRuleApi.list(params)
      setData(res.data || [])
    } catch {
      message.error('获取点检规则失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [filterModule])

  const openAdd = () => {
    setEditing(null)
    form.resetFields()
    form.setFieldsValue({ is_active: true, sort_order: 0 })
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
        await inspectionRuleApi.update(editing.id, values)
        message.success('更新成功')
      } else {
        await inspectionRuleApi.create(values)
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
      await inspectionRuleApi.delete(id)
      message.success('删除成功')
      fetchData()
    } catch {
      message.error('删除失败')
    }
  }

  const columns = [
    {
      title: '所属模块', dataIndex: 'module_code', key: 'module_code', width: 110,
      render: (v: string) => <Tag color={moduleColor[v] || 'default'}>{moduleLabel[v] || v}</Tag>,
    },
    {
      title: '规则类型', dataIndex: 'rule_type', key: 'rule_type', width: 100,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    { title: '点检项编码', dataIndex: 'item_code', key: 'item_code', width: 140 },
    { title: '点检项名称', dataIndex: 'item_name', key: 'item_name', ellipsis: true },
    { title: '父级编码', dataIndex: 'parent_code', key: 'parent_code', width: 140, render: (v: string) => v || '—' },
    { title: '标准说明', dataIndex: 'standard_desc', key: 'standard_desc', ellipsis: true, render: (v: string) => v || '—' },
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
          <Popconfirm title="确认删除此规则？" onConfirm={() => handleDelete(record.id)} okText="确认" cancelText="取消">
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
              placeholder="按模块筛选"
              allowClear
              style={{ width: 160 }}
              options={moduleOptions}
              onChange={(v) => setFilterModule(v)}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={fetchData}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>新建规则</Button>
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
          scroll={{ x: 1200 }}
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t) => `共 ${t} 条`, pageSizeOptions: ['20', '50', '100'] }}
        />
      </div>

      <Modal
        title={editing ? '编辑点检规则' : '新建点检规则'}
        open={modalOpen}
        onOk={handleSave}
        onCancel={() => setModalOpen(false)}
        width={560}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="module_code" label="所属模块" rules={[{ required: true, message: '请选择模块' }]}>
            <Select options={moduleOptions} placeholder="选择模块" />
          </Form.Item>
          <Form.Item name="rule_type" label="规则类型" rules={[{ required: true, message: '请选择类型' }]}>
            <Select options={ruleTypeOptions} placeholder="选择类型" />
          </Form.Item>
          {!editing && (
            <Form.Item name="item_code" label="点检项编码" rules={[{ required: true, message: '请输入编码' }]}>
              <Input placeholder="如 check_001" />
            </Form.Item>
          )}
          <Form.Item name="item_name" label="点检项名称" rules={[{ required: true, message: '请输入名称' }]}>
            <Input placeholder="如 采购物料齐套" />
          </Form.Item>
          <Form.Item name="parent_code" label="父级编码">
            <Input placeholder="可选，用于构建树状结构" />
          </Form.Item>
          <Form.Item name="standard_desc" label="标准说明">
            <Input.TextArea rows={3} placeholder="如：回货预计超过备料日期标红色" />
          </Form.Item>
          <Form.Item name="sort_order" label="排序号">
            <Input type="number" placeholder="0" />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
