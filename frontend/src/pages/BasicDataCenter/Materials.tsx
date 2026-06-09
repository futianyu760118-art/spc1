import { useState, useCallback, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, Select, InputNumber, message,
  Space, Tag, Popconfirm, Row, Col, TreeSelect,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
  ApartmentOutlined, UnorderedListOutlined,
} from '@ant-design/icons'
import api from '../../services/api'

interface Material {
  id: number
  material_id: string
  parent_id?: string | null
  material_code: string
  material_name: string
  spec_model?: string
  material_type: string
  unit_of_measure: string
  brand?: string
  is_purchase: number
  is_produce: number
  status: number
  erp_sync_flag: number
  is_deleted: number
  children?: Material[]
}

interface TreeNode {
  id: string
  value: string
  title: string
  key: string
  children?: TreeNode[]
}

const buildTreeData = (items: Material[]): TreeNode[] => {
  const map: Record<string, TreeNode> = {}
  const roots: TreeNode[] = []
  for (const item of items) {
    map[item.material_id] = { id: item.material_id, value: item.material_id, title: `${item.material_code} - ${item.material_name}`, key: item.material_id, children: [] }
  }
  for (const item of items) {
    if (item.parent_id && map[item.parent_id]) {
      map[item.parent_id].children!.push(map[item.material_id])
    } else {
      roots.push(map[item.material_id])
    }
  }
  return roots
}

const flattenTree = (nodes: Material[]): Material[] => {
  const result: Material[] = []
  const walk = (list: Material[]) => {
    for (const node of list) {
      result.push(node)
      if (node.children?.length) walk(node.children)
    }
  }
  walk(nodes)
  return result
}

const filterSelfFromTree = (nodes: TreeNode[], excludeId: string): TreeNode[] => {
  return nodes
    .filter(n => n.id !== excludeId)
    .map(n => ({
      ...n,
      children: n.children ? filterSelfFromTree(n.children, excludeId) : [],
    }))
}

interface MaterialFormProps {
  form: any
  treeData: TreeNode[]
}

const MaterialForm = ({ form, treeData }: MaterialFormProps) => (
  <Form form={form} layout="vertical">
    <Form.Item name="material_id" label="物料ID" rules={[{ required: true }]}>
      <Input placeholder="请输入物料ID(外部系统)" />
    </Form.Item>
    <Form.Item name="parent_id" label="上级物料">
      <TreeSelect
        treeData={treeData}
        placeholder="无（根级物料）"
        allowClear
        treeDefaultExpandAll
      />
    </Form.Item>
    <Form.Item name="material_code" label="物料编码" rules={[{ required: true }]}>
      <Input placeholder="请输入物料编码" />
    </Form.Item>
    <Form.Item name="material_name" label="物料名称" rules={[{ required: true }]}>
      <Input placeholder="请输入物料名称" />
    </Form.Item>
    <Form.Item name="spec_model" label="规格型号">
      <Input placeholder="请输入规格型号" />
    </Form.Item>
    <Form.Item name="material_type" label="物料分类" rules={[{ required: true }]}>
      <Input placeholder="请输入物料分类" />
    </Form.Item>
    <Form.Item name="unit_of_measure" label="计量单位" rules={[{ required: true }]}>
      <Input placeholder="请输入计量单位" />
    </Form.Item>
    <Form.Item name="brand" label="品牌/厂商">
      <Input placeholder="请输入品牌/厂商" />
    </Form.Item>
    <Form.Item name="is_purchase" label="是否可采购" initialValue={0}>
      <Select>
        <Select.Option value={1}>是</Select.Option>
        <Select.Option value={0}>否</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="is_produce" label="是否可生产" initialValue={0}>
      <Select>
        <Select.Option value={1}>是</Select.Option>
        <Select.Option value={0}>否</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="status" label="状态" initialValue={1}>
      <Select>
        <Select.Option value={1}>启用</Select.Option>
        <Select.Option value={0}>禁用</Select.Option>
      </Select>
    </Form.Item>
    <Form.Item name="erp_sync_flag" label="ERP同步标识" initialValue={0}>
      <Select>
        <Select.Option value={1}>已同步</Select.Option>
        <Select.Option value={0}>未同步</Select.Option>
      </Select>
    </Form.Item>
  </Form>
)

export default function Materials() {
  const [data, setData] = useState<Material[]>([])
  const [treeData, setTreeData] = useState<Material[]>([])
  const [parentTreeData, setParentTreeData] = useState<TreeNode[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingItem, setEditingItem] = useState<Material | null>(null)
  const [form] = Form.useForm()
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20, total: 0 })
  const [viewMode, setViewMode] = useState<'tree' | 'list'>('tree')

  const fetchTreeData = useCallback(async () => {
    try {
      const res: any = await api.get('/basicdata/materials/tree')
      setTreeData(res.data || [])
      setParentTreeData(buildTreeData(flattenTree(res.data || [])))
    } catch {
      // ignore
    }
  }, [])

  const fetchData = useCallback(async (page = 1, pageSize = 20) => {
    setLoading(true)
    try {
      const res: any = await api.get('/basicdata/materials', { params: { page, page_size: pageSize } })
      setData(res.data?.items || [])
      setPagination({ current: res.data?.page || 1, pageSize: res.data?.page_size || 20, total: res.data?.total || 0 })
    } catch (error) {
      message.error('加载数据失败')
    } finally {
      setLoading(false)
    }
  }, [])

  const refreshAll = useCallback(async () => {
    if (viewMode === 'tree') {
      await fetchTreeData()
    } else {
      await fetchData(pagination.current, pagination.pageSize)
    }
    await fetchTreeData()
  }, [viewMode, fetchTreeData, fetchData, pagination])

  useEffect(() => {
    if (viewMode === 'tree') {
      fetchTreeData()
    } else {
      fetchData()
    }
  }, [viewMode, fetchTreeData, fetchData])

  useEffect(() => {
    fetchTreeData()
  }, [fetchTreeData])

  const handleAdd = () => {
    setEditingItem(null)
    form.resetFields()
    setModalVisible(true)
  }

  const handleEdit = (item: Material) => {
    setEditingItem(item)
    form.setFieldsValue(item)
    setModalVisible(true)
  }

  const handleDelete = async (materialId: string) => {
    try {
      await api.delete(`/basicdata/materials/${materialId}`)
      message.success('删除成功')
      refreshAll()
    } catch (error) {
      message.error('删除失败')
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editingItem) {
        if (values.parent_id === editingItem.material_id) {
          message.error('上级物料不能选择自身')
          return
        }
        await api.put(`/basicdata/materials/${editingItem.material_id}`, values)
        message.success('更新成功')
      } else {
        await api.post('/basicdata/materials', values)
        message.success('创建成功')
      }
      setModalVisible(false)
      form.resetFields()
      refreshAll()
    } catch (error) {
      message.error('操作失败')
    }
  }

  const columns = [
    { title: '物料ID', dataIndex: 'material_id', key: 'material_id', width: 120 },
    { title: '物料编码', dataIndex: 'material_code', key: 'material_code', width: 160 },
    { title: '物料名称', dataIndex: 'material_name', key: 'material_name', width: 180 },
    { title: '规格型号', dataIndex: 'spec_model', key: 'spec_model', width: 140 },
    { title: '物料分类', dataIndex: 'material_type', key: 'material_type', width: 100 },
    { title: '计量单位', dataIndex: 'unit_of_measure', key: 'unit_of_measure', width: 80 },
    { title: '品牌/厂商', dataIndex: 'brand', key: 'brand', width: 100 },
    {
      title: '可采购', dataIndex: 'is_purchase', key: 'is_purchase', width: 70,
      render: (v: number) => <Tag color={v ? 'blue' : 'default'}>{v ? '是' : '否'}</Tag>,
    },
    {
      title: '可生产', dataIndex: 'is_produce', key: 'is_produce', width: 70,
      render: (v: number) => <Tag color={v ? 'blue' : 'default'}>{v ? '是' : '否'}</Tag>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 70,
      render: (status: number) => (
        <Tag color={status === 1 ? 'green' : 'red'}>{status === 1 ? '启用' : '禁用'}</Tag>
      ),
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      fixed: 'right' as const,
      render: (_: any, record: Material) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.material_id)} okText="确认" cancelText="取消">
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
            <Space>
              <Button
                type={viewMode === 'tree' ? 'primary' : 'default'}
                icon={<ApartmentOutlined />}
                onClick={() => setViewMode('tree')}
              >树形</Button>
              <Button
                type={viewMode === 'list' ? 'primary' : 'default'}
                icon={<UnorderedListOutlined />}
                onClick={() => setViewMode('list')}
              >列表</Button>
            </Space>
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<ReloadOutlined />} onClick={refreshAll}>刷新</Button>
              <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>新增</Button>
            </Space>
          </Col>
        </Row>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        {viewMode === 'tree' ? (
          <Table
            rowKey="id"
            columns={columns}
            dataSource={treeData}
            loading={loading}
            scroll={{ x: 1100 }}
            size="small"
            pagination={false}
            expandable={{ defaultExpandAllRows: true }}
          />
        ) : (
          <Table
            rowKey="id"
            columns={columns}
            dataSource={data}
            loading={loading}
            scroll={{ x: 1100 }}
            size="small"
            pagination={{
              ...pagination,
              showSizeChanger: true,
              showTotal: (total: number) => `共 ${total} 条`,
              onChange: (page, pageSize) => fetchData(page, pageSize),
              pageSizeOptions: ['20', '50', '100'],
            }}
          />
        )}
      </div>
      <Modal
        title={editingItem ? '编辑物料' : '新增物料'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
      >
        <MaterialForm form={form} treeData={editingItem ? filterSelfFromTree(parentTreeData, editingItem.material_id) : parentTreeData} />
      </Modal>
    </div>
  )
}
