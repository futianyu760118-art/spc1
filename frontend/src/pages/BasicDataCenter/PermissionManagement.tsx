import { useState, useCallback, useEffect } from 'react'
import {
  Table, Button, Modal, Form, Input, InputNumber, Select, TreeSelect,
  message, Space, Tag, Popconfirm, Switch, Tooltip,
} from 'antd'
import {
  PlusOutlined, EditOutlined, DeleteOutlined, ReloadOutlined,
} from '@ant-design/icons'
import { permissionApi } from '../../services/api'
import PermButton from '../../components/PermButton'
import { useAuthStore } from '../../store/auth'

interface PermNode {
  code: string
  name: string
  module: string
  parent_code: string | null
  actions: string[]
  route_path: string | null
  sort_order: number
  is_active?: boolean
  children: PermNode[]
}

const PROTECTED_CODES = ['permissions', 'roles', 'users']
const STANDARD_ACTIONS = ['create', 'read', 'update', 'delete', 'import', 'reset_password']

function flatten(nodes: PermNode[], acc: PermNode[] = []): PermNode[] {
  for (const n of nodes) {
    acc.push(n)
    if (n.children?.length) flatten(n.children, acc)
  }
  return acc
}

function buildTreeSelectData(nodes: PermNode[]): any[] {
  return nodes.map(n => ({
    value: n.code,
    title: `${n.name} (${n.code})`,
    children: n.children?.length ? buildTreeSelectData(n.children) : undefined,
  }))
}

export default function PermissionManagement() {
  const [tree, setTree] = useState<PermNode[]>([])
  const [loading, setLoading] = useState(false)
  const [modalVisible, setModalVisible] = useState(false)
  const [editingCode, setEditingCode] = useState<string | null>(null)
  const [form] = Form.useForm()
  const hasPermission = useAuthStore(s => s.hasPermission)
  const canCreate = hasPermission('permissions', 'create')
  const canUpdate = hasPermission('permissions', 'update')
  const canDelete = hasPermission('permissions', 'delete')

  const fetchTree = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await permissionApi.tree(true)
      setTree(res?.data || [])
    } catch {
      message.error('加载权限树失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchTree() }, [fetchTree])

  const flatList = flatten(tree)
  const treeSelectData = buildTreeSelectData(tree)

  const handleAdd = (parentCode?: string) => {
    setEditingCode(null)
    form.resetFields()
    form.setFieldsValue({
      actions: ['create', 'read', 'update', 'delete'],
      sort_order: 0,
      parent_code: parentCode || null,
      module: '',
    })
    setModalVisible(true)
  }

  const handleEdit = (node: PermNode) => {
    setEditingCode(node.code)
    form.setFieldsValue({
      code: node.code,
      name: node.name,
      module: node.module,
      parent_code: node.parent_code,
      actions: node.actions,
      route_path: node.route_path,
      sort_order: node.sort_order,
    })
    setModalVisible(true)
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (editingCode) {
        await permissionApi.update(editingCode, {
          name: values.name,
          module: values.module,
          parent_code: values.parent_code || null,
          actions: values.actions,
          route_path: values.route_path || null,
          sort_order: values.sort_order ?? 0,
        })
        message.success('更新成功')
      } else {
        await permissionApi.create({
          code: values.code,
          name: values.name,
          module: values.module || values.code.split('.')[0],
          parent_code: values.parent_code || null,
          actions: values.actions,
          route_path: values.route_path || null,
          sort_order: values.sort_order ?? 0,
        })
        message.success('创建成功')
      }
      setModalVisible(false)
      fetchTree()
    } catch (e: any) {
      if (e?.errorFields) return
      message.error(e?.response?.data?.detail || '操作失败')
    }
  }

  const handleDelete = async (code: string) => {
    try {
      await permissionApi.remove(code)
      message.success('删除成功')
      fetchTree()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '删除失败')
    }
  }

  const handleToggleActive = async (node: PermNode, active: boolean) => {
    try {
      await permissionApi.update(node.code, { is_active: active })
      message.success(active ? '已启用' : '已停用')
      fetchTree()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '操作失败')
    }
  }

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
      width: 200,
      render: (name: string, record: PermNode) => (
        <Space size={4}>
          <span>{name}</span>
          {PROTECTED_CODES.includes(record.code) && <Tag color="gold">系统</Tag>}
          {record.is_active === false && <Tag color="red">停用</Tag>}
        </Space>
      ),
    },
    { title: '编码', dataIndex: 'code', key: 'code', width: 220 },
    { title: '路由', dataIndex: 'route_path', key: 'route_path', width: 180, render: (v: string) => v || '-' },
    {
      title: '操作集',
      dataIndex: 'actions',
      key: 'actions',
      width: 220,
      render: (acts: string[]) => (
        <Space size={4} wrap>
          {(acts || []).map(a => <Tag key={a}>{a}</Tag>)}
        </Space>
      ),
    },
    { title: '排序', dataIndex: 'sort_order', key: 'sort_order', width: 70 },
    {
      title: '启用',
      key: 'is_active',
      width: 80,
      render: (_: any, record: PermNode) => {
        const protectedNode = PROTECTED_CODES.includes(record.code)
        const sw = (
          <Switch
            size="small"
            checked={record.is_active !== false}
            disabled={protectedNode || !canUpdate}
            onChange={(v) => handleToggleActive(record, v)}
          />
        )
        return protectedNode ? <Tooltip title="受保护权限不可停用">{sw}</Tooltip> : sw
      },
    },
    {
      title: '操作',
      key: 'action',
      width: 180,
      render: (_: any, record: PermNode) => (
        <Space size="small">
          <PermButton permResource="permissions" permAction="create" size="small" icon={<PlusOutlined />} onClick={() => handleAdd(record.code)}>子级</PermButton>
          <PermButton permResource="permissions" permAction="update" size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)} />
          <Popconfirm
            title="确认删除该权限？"
            description="将同时清除所有角色中对该权限的引用。"
            onConfirm={() => handleDelete(record.code)}
            okText="确认"
            cancelText="取消"
            disabled={!canDelete || PROTECTED_CODES.includes(record.code)}
          >
            <PermButton permResource="permissions" permAction="delete" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchTree}>刷新</Button>
          <PermButton permResource="permissions" permAction="create" type="primary" icon={<PlusOutlined />} onClick={() => handleAdd()}>新增顶级权限</PermButton>
        </Space>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table
          rowKey="code"
          columns={columns}
          dataSource={tree}
          loading={loading}
          pagination={false}
          scroll={{ x: 1100 }}
          size="small"
          expandable={{ defaultExpandAllRows: false, defaultExpandedRowKeys: flatList.filter(n => !n.parent_code).map(n => n.code) }}
        />
      </div>

      <Modal
        title={editingCode ? `编辑权限：${editingCode}` : '新增权限'}
        open={modalVisible}
        onOk={handleSubmit}
        onCancel={() => setModalVisible(false)}
        width={600}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="code" label="权限编码" rules={[{ required: true, message: '请输入权限编码' }]}>
            <Input placeholder="如 production.schedule_plans" disabled={!!editingCode} />
          </Form.Item>
          <Form.Item name="name" label="权限名称" rules={[{ required: true, message: '请输入权限名称' }]}>
            <Input placeholder="如 计划排产" />
          </Form.Item>
          <Form.Item name="parent_code" label="父级权限">
            <TreeSelect
              treeData={treeSelectData}
              placeholder="无（顶级权限）"
              allowClear
              treeDefaultExpandAll
            />
          </Form.Item>
          <Form.Item name="module" label="模块">
            <Input placeholder="如 production（默认取编码首段）" />
          </Form.Item>
          <Form.Item name="actions" label="操作集">
            <Select mode="tags" placeholder="选择或输入操作">
              {STANDARD_ACTIONS.map(a => <Select.Option key={a} value={a}>{a}</Select.Option>)}
            </Select>
          </Form.Item>
          <Form.Item name="route_path" label="前端路由">
            <Input placeholder="如 /schedule-plans（可选）" />
          </Form.Item>
          <Form.Item name="sort_order" label="排序">
            <InputNumber style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
