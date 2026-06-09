import { useState, useEffect } from 'react'
import { Table, Tag, Button, Modal, Form, Input, Select, Space, message, Popconfirm, Switch, Row, Col, Tabs, Checkbox, Tree, Radio, Divider, Alert } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, KeyOutlined, ReloadOutlined, SafetyOutlined, UserOutlined, ThunderboltOutlined, ExportOutlined } from '@ant-design/icons'
import { userApi } from '../../services/api'
import ExportColumnSelector, { type ExportColumnOption } from '../../components/ExportColumnSelector'
import { useExport } from '../../hooks/useExport'
import { formatDateTime } from '../../utils'

const roleColorMap: Record<string, string> = {
  admin: 'purple',
  planner: 'blue',
  purchaser: 'orange',
  manager: 'cyan',
  purchase_manager: 'gold',
}

interface PermTreeNode {
  key: string
  label: string
  children?: PermTreeNode[]
}

const PERMISSION_TREE: PermTreeNode[] = [
  { key: 'dashboard', label: '供应链驾驶舱' },
  {
    key: 'orders', label: '订单交付中心',
    children: [
      { key: 'orders.list', label: '订单总控台' },
      { key: 'orders.run_orders', label: '跑单管理' },
      { key: 'orders.risk_pool', label: '订单风险池' },
    ],
  },
  {
    key: 'materials', label: '物料齐套中心',
    children: [
      { key: 'materials.purchase_plan', label: '采购到料计划' },
      { key: 'materials.issues', label: '问题物料池' },
      { key: 'materials.long_lead', label: '长交期物料池' },
      { key: 'materials.kit_analysis', label: '齐套分析' },
      { key: 'materials.supplier_risk', label: '供应商风险分析' },
      { key: 'materials.supplier_payment', label: '供应商付款排程' },
    ],
  },
  {
    key: 'production', label: '生产协同中心',
    children: [
      { key: 'production.overview', label: '生产总览' },
      { key: 'production.schedule_plans', label: '计划排产' },
      { key: 'production.front_process', label: '前道管理' },
      { key: 'production.smt', label: '贴片管理' },
      { key: 'production.lean', label: '精益管理' },
      { key: 'production.assembly', label: '组装管理' },
      { key: 'production.packaging', label: '包装管理' },
      { key: 'production.exceptions', label: '工序异常池' },
    ],
  },
  {
    key: 'exceptions', label: '异常与质量中心',
    children: [
      { key: 'exceptions.pool', label: '异常总池' },
      { key: 'exceptions.issue_log', label: '问题日志' },
      { key: 'exceptions.change_log', label: '变更日志' },
      { key: 'exceptions.quality', label: '品质异常' },
      { key: 'exceptions.product_samples', label: '产品封样' },
      { key: 'exceptions.closure', label: '闭环跟踪' },
    ],
  },
  { key: 'meetings', label: '会议与任务中心' },
  { key: 'npi', label: '新品/NPI项目中心' },
  {
    key: 'rules', label: '规则配置中心',
    children: [
      { key: 'rules.risk_rules', label: '预警规则' },
      { key: 'rules.inspection', label: '点检规则' },
      { key: 'rules.node_standards', label: '节点标准' },
      { key: 'rules.order_standards', label: '订单标准' },
      { key: 'rules.work_instructions', label: '作业指导书' },
      { key: 'rules.responsibility', label: '责任归属' },
      { key: 'rules.status_dict', label: '状态字典' },
    ],
  },
  {
    key: 'basicdata', label: '基础数据与集成中心',
    children: [
      { key: 'basicdata.import', label: '数据集成' },
      { key: 'basicdata.data', label: '基础数据管理' },
      { key: 'basicdata.feedback', label: '问题反馈' },
      { key: 'basicdata.files', label: '文件管理' },
      { key: 'announcements', label: '公告管理' },
      { key: 'users', label: '用户管理' },
      { key: 'audit', label: '审计日志' },
      { key: 'settings', label: '同步SQL配置' },
    ],
  },
]

// Flatten tree to get all leaf keys (for column-level toggleAll)
function flattenLeaves(nodes: PermTreeNode[]): string[] {
  const result: string[] = []
  for (const n of nodes) {
    if (n.children && n.children.length > 0) {
      result.push(...flattenLeaves(n.children))
    } else {
      result.push(n.key)
    }
  }
  return result
}
// Also collect all keys (parent + leaf) for allKeys usage
function flattenAll(nodes: PermTreeNode[]): string[] {
  const result: string[] = []
  for (const n of nodes) {
    result.push(n.key)
    if (n.children) result.push(...flattenAll(n.children))
  }
  return result
}
const ALL_PERM_KEYS = flattenAll(PERMISSION_TREE)
const ALL_LEAF_KEYS = flattenLeaves(PERMISSION_TREE)

// 转换为 antd Tree 数据格式
function buildTreeData(nodes: PermTreeNode[]): any[] {
  return nodes.map(n => ({
    title: n.label,
    key: n.key,
    children: n.children && n.children.length > 0 ? buildTreeData(n.children) : undefined,
  }))
}
const PERM_TREE_DATA = buildTreeData(PERMISSION_TREE)

const PERMISSION_ACTIONS = [
  { key: 'create', label: '新增' },
  { key: 'read', label: '查看' },
  { key: 'update', label: '编辑' },
  { key: 'delete', label: '删除' },
  { key: 'import', label: '导入' },
]

interface UserItem {
  id: number
  username: string
  display_name: string | null
  role_id: number
  role_code: string
  role_name: string
  is_active: boolean
  last_login_time: string | null
  created_at: string | null
  updated_at: string | null
}

interface RoleItem {
  id: number
  role_code: string
  role_name: string
  permissions: Record<string, string[]>
}

const USER_EXPORT_COLUMNS: ExportColumnOption[] = [
  { field: 'username', label: '用户名' },
  { field: 'display_name', label: '显示名称' },
  { field: 'role_code', label: '角色编码' },
  { field: 'role_name', label: '角色名称' },
  { field: 'is_active', label: '状态' },
  { field: 'last_login_time', label: '最后登录' },
  { field: 'created_at', label: '创建时间' },
  { field: 'updated_at', label: '更新时间' },
]

function PermissionMatrix({ value, onChange }: { value: Record<string, string[]>; onChange: (v: Record<string, string[]>) => void }) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {}
    PERMISSION_TREE.forEach(n => { if (n.children) init[n.key] = true })
    return init
  })

  const toggleExpand = (key: string) => setExpanded(prev => ({ ...prev, [key]: !prev[key] }))

  // Get effective actions for a key (for parent: derived from children)
  const getActions = (key: string, children?: PermTreeNode[]): string[] => {
    if (!children || children.length === 0) return value[key] || []
    // Parent: an action is "checked" if ALL children have it
    return PERMISSION_ACTIONS.filter(a => children.every(c => (value[c.key] || []).includes(a.key))).map(a => a.key)
  }
  const getIndeterminate = (action: string, children?: PermTreeNode[]): boolean => {
    if (!children || children.length === 0) return false
    const has = children.filter(c => (value[c.key] || []).includes(action)).length
    return has > 0 && has < children.length
  }

  // Toggle single action on a leaf
  const toggleLeaf = (key: string, action: string) => {
    const cur = value[key] || []
    const next = cur.includes(action) ? cur.filter(a => a !== action) : [...cur, action]
    onChange({ ...value, [key]: next })
  }

  // Toggle single action on a parent (cascade to all children)
  const toggleParent = (children: PermTreeNode[], action: string, checked: boolean) => {
    const next = { ...value }
    children.forEach(c => {
      next[c.key] = checked ? [...new Set([...(next[c.key] || []), action])] : (next[c.key] || []).filter(a => a !== action)
    })
    onChange(next)
  }

  // Toggle entire row (all actions)
  const toggleRow = (key: string, checked: boolean, children?: PermTreeNode[]) => {
    const next = { ...value }
    const allActs = PERMISSION_ACTIONS.map(a => a.key)
    if (children && children.length > 0) {
      children.forEach(c => { next[c.key] = checked ? [...allActs] : [] })
    } else {
      next[key] = checked ? [...allActs] : []
    }
    onChange(next)
  }

  // Column-level toggle (all leaves)
  const toggleCol = (action: string, checked: boolean) => {
    const next = { ...value }
    ALL_LEAF_KEYS.forEach(k => {
      next[k] = checked ? [...new Set([...(next[k] || []), action])] : (next[k] || []).filter(a => a !== action)
    })
    onChange(next)
  }

  const colAllChecked = (action: string) => ALL_LEAF_KEYS.every(k => (value[k] || []).includes(action))
  const colSomeChecked = (action: string) => ALL_LEAF_KEYS.some(k => (value[k] || []).includes(action))

  const renderRow = (node: PermTreeNode, depth: number) => {
    const hasChildren = node.children && node.children.length > 0
    const isExpanded = expanded[node.key]
    const actions = getActions(node.key, node.children)
    const allChecked = PERMISSION_ACTIONS.every(a => actions.includes(a.key))
    const rowIndeterminate = hasChildren
      ? PERMISSION_ACTIONS.some(a => getIndeterminate(a.key, node.children) || (node.children!.some(c => (value[c.key] || []).includes(a.key)) && !node.children!.every(c => (value[c.key] || []).includes(a.key)))) && !allChecked
      : (actions.length > 0 && !allChecked)

    const rows: React.ReactNode[] = []
    rows.push(
      <tr key={node.key} style={{ background: depth === 0 && hasChildren ? '#fafafa' : 'transparent' }}>
        <td style={{ padding: '6px 8px', paddingLeft: 8 + depth * 20, borderBottom: '1px solid #f0f0f0', whiteSpace: 'nowrap', fontWeight: hasChildren ? 500 : 400 }}>
          {hasChildren ? (
            <span onClick={() => toggleExpand(node.key)} style={{ cursor: 'pointer', marginRight: 4, display: 'inline-block', width: 14, textAlign: 'center', color: '#999', fontSize: 12, userSelect: 'none' }}>
              {isExpanded ? '▼' : '▶'}
            </span>
          ) : (
            <span style={{ display: 'inline-block', width: 14, marginRight: 4 }} />
          )}
          <Checkbox checked={allChecked} indeterminate={rowIndeterminate} onChange={e => toggleRow(node.key, e.target.checked, node.children)} />
          <span style={{ marginLeft: 6 }}>{node.label}</span>
        </td>
        {PERMISSION_ACTIONS.map(a => {
          const checked = actions.includes(a.key)
          const indeterminate = hasChildren ? getIndeterminate(a.key, node.children) : false
          return (
            <td key={a.key} style={{ textAlign: 'center', padding: '6px 4px', borderBottom: '1px solid #f0f0f0' }}>
              <Checkbox
                checked={checked}
                indeterminate={indeterminate}
                onChange={e => hasChildren ? toggleParent(node.children!, a.key, e.target.checked) : toggleLeaf(node.key, a.key)}
              />
            </td>
          )
        })}
      </tr>
    )
    if (hasChildren && isExpanded) {
      node.children!.forEach(child => {
        rows.push(...renderRow(child, depth + 1))
      })
    }
    return rows
  }

  return (
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
      <thead>
        <tr>
          <th style={{ textAlign: 'left', padding: '6px 8px', borderBottom: '2px solid #e5e7eb', minWidth: 200 }}>菜单 / 功能模块</th>
          {PERMISSION_ACTIONS.map(a => (
            <th key={a.key} style={{ textAlign: 'center', padding: '6px 4px', borderBottom: '2px solid #e5e7eb', width: 60 }}>
              <Checkbox checked={colAllChecked(a.key)} indeterminate={colSomeChecked(a.key) && !colAllChecked(a.key)} onChange={e => toggleCol(a.key, e.target.checked)} />
              {' '}{a.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {PERMISSION_TREE.map(node => renderRow(node, 0))}
      </tbody>
    </table>
  )
}

export default function UserManagement() {
  const { exporting, exportData } = useExport()
  const [activeTab, setActiveTab] = useState('users')
  const [users, setUsers] = useState<UserItem[]>([])
  const [roles, setRoles] = useState<RoleItem[]>([])
  const [loading, setLoading] = useState(false)
  const [roleLoading, setRoleLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [pwdModalOpen, setPwdModalOpen] = useState(false)
  const [roleModalOpen, setRoleModalOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<UserItem | null>(null)
  const [editingRole, setEditingRole] = useState<RoleItem | null>(null)
  const [pwdUser, setPwdUser] = useState<UserItem | null>(null)
  const [form] = Form.useForm()
  const [pwdForm] = Form.useForm()
  const [roleForm] = Form.useForm()
  const [rolePermissions, setRolePermissions] = useState<Record<string, string[]>>({})
  // 批量授权弹窗
  const [bgOpen, setBgOpen] = useState(false)
  const [bgKeys, setBgKeys] = useState<string[]>([])
  const [bgActions, setBgActions] = useState<string[]>(['read'])
  const [bgRoleIds, setBgRoleIds] = useState<number[]>([])
  const [bgMode, setBgMode] = useState<'grant' | 'revoke' | 'replace'>('grant')
  const [bgSubmitting, setBgSubmitting] = useState(false)
  const [exportColumnModalOpen, setExportColumnModalOpen] = useState(false)
  const [userQuery, setUserQuery] = useState<{ sortBy?: string; sortOrder?: string; filters?: Record<string, string[]> }>({})

  const fetchUsers = async (sortBy?: string, sortOrder?: string, tableFilters?: Record<string, string[]>) => {
    setUserQuery({ sortBy, sortOrder, filters: tableFilters })
    setLoading(true)
    try {
      const params: any = {}
      if (sortBy) params.sort_by = sortBy
      if (sortOrder) params.sort_order = sortOrder
      if (tableFilters?.role_code?.length) params.role_code = tableFilters.role_code.join(',')
      if (tableFilters?.is_active?.length) params.is_active = tableFilters.is_active[0] === 'true'
      const res: any = await userApi.list(params)
      setUsers(res.data || [])
    } catch {
      message.error('加载用户列表失败')
    } finally {
      setLoading(false)
    }
  }

  const fetchRoles = async () => {
    setRoleLoading(true)
    try {
      const res: any = await userApi.roles()
      setRoles(res.data || [])
    } catch {
      message.error('加载角色列表失败')
    } finally {
      setRoleLoading(false)
    }
  }

  useEffect(() => {
    fetchUsers()
    fetchRoles()
  }, [])

  const openAdd = () => {
    setEditingUser(null)
    form.resetFields()
    form.setFieldsValue({ is_active: true })
    setModalOpen(true)
  }

  const openEdit = (record: UserItem) => {
    setEditingUser(record)
    form.setFieldsValue({
      username: record.username,
      display_name: record.display_name,
      role_id: record.role_id,
      is_active: record.is_active,
    })
    setModalOpen(true)
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      if (editingUser) {
        await userApi.update(editingUser.id, {
          display_name: values.display_name,
          role_id: values.role_id,
          is_active: values.is_active,
        })
        message.success('更新成功')
      } else {
        await userApi.create(values)
        message.success('创建成功')
      }
      setModalOpen(false)
      fetchUsers()
    } catch (e: any) {
      if (e?.response?.data?.detail) message.error(e.response.data.detail)
    }
  }

  const handleDelete = async (id: number) => {
    try {
      await userApi.delete(id)
      message.success('已删除')
      fetchUsers()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '删除失败')
    }
  }

  const openResetPwd = (record: UserItem) => {
    setPwdUser(record)
    pwdForm.resetFields()
    setPwdModalOpen(true)
  }

  const handleResetPwd = async () => {
    try {
      const values = await pwdForm.validateFields()
      if (!pwdUser) return
      await userApi.resetPassword(pwdUser.id, values.new_password)
      message.success(`已重置 ${pwdUser.username} 的密码`)
      setPwdModalOpen(false)
    } catch (e: any) {
      if (e?.response?.data?.detail) message.error(e.response.data.detail)
    }
  }

  const handleToggleActive = async (record: UserItem) => {
    try {
      await userApi.update(record.id, { is_active: !record.is_active })
      message.success(record.is_active ? '已停用' : '已启用')
      fetchUsers(userQuery.sortBy, userQuery.sortOrder, userQuery.filters)
    } catch {
      message.error('操作失败')
    }
  }

  const handleExportUsers = (selectedColumns: string[]) => {
    const params: Record<string, any> = { format: 'xlsx', columns: selectedColumns.join(',') }
    if (userQuery.sortBy) params.sort_by = userQuery.sortBy
    if (userQuery.sortOrder) params.sort_order = userQuery.sortOrder
    if (userQuery.filters?.role_code?.length) params.role_code = userQuery.filters.role_code.join(',')
    if (userQuery.filters?.is_active?.length) params.is_active = userQuery.filters.is_active[0] === 'true'
    setExportColumnModalOpen(false)
    exportData('/api/v1/basicdata/users/export', params, '用户管理.xlsx')
  }

  // ── 角色操作 ──
  const openAddRole = () => {
    setEditingRole(null)
    roleForm.resetFields()
    setRolePermissions({})
    setRoleModalOpen(true)
  }

  const openEditRole = (record: RoleItem) => {
    setEditingRole(record)
    roleForm.setFieldsValue({ role_code: record.role_code, role_name: record.role_name })
    setRolePermissions(record.permissions || {})
    setRoleModalOpen(true)
  }

  const handleSaveRole = async () => {
    try {
      const values = await roleForm.validateFields()
      if (editingRole) {
        await userApi.updateRole(editingRole.id, { role_name: values.role_name, permissions: rolePermissions })
        message.success('角色更新成功')
      } else {
        await userApi.createRole({ role_code: values.role_code, role_name: values.role_name, permissions: rolePermissions })
        message.success('角色创建成功')
      }
      setRoleModalOpen(false)
      fetchRoles()
    } catch (e: any) {
      if (e?.response?.data?.detail) message.error(e.response.data.detail)
    }
  }

  const handleDeleteRole = async (id: number) => {
    try {
      await userApi.deleteRole(id)
      message.success('角色已删除')
      fetchRoles()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '删除失败')
    }
  }

  // ── 批量授权 ──
  const openBatchGrant = () => {
    setBgKeys([])
    setBgActions(['read'])
    setBgRoleIds([])
    setBgMode('grant')
    setBgOpen(true)
  }

  const handleBatchGrant = async () => {
    // 仅取叶子节点 key（避免父节点写入 perms）
    const leafSet = new Set(ALL_LEAF_KEYS)
    const targetKeys = bgKeys.filter(k => leafSet.has(k))
    if (targetKeys.length === 0) {
      message.warning('请选择至少一个权限项（具体子菜单）'); return
    }
    if (bgActions.length === 0) {
      message.warning('请选择至少一个操作'); return
    }
    if (bgRoleIds.length === 0) {
      message.warning('请选择至少一个目标角色'); return
    }
    const permissions: Record<string, string[]> = {}
    targetKeys.forEach(k => { permissions[k] = [...bgActions] })
    setBgSubmitting(true)
    try {
      const res: any = await userApi.batchGrant({ role_ids: bgRoleIds, permissions, mode: bgMode })
      const aff = res?.data?.affected ?? 0
      const skip = res?.data?.skipped_admin ?? 0
      message.success(`批量授权完成：影响 ${aff} 个角色${skip ? `，跳过 ${skip} 个 admin` : ''}`)
      setBgOpen(false)
      fetchRoles()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '批量授权失败')
    } finally {
      setBgSubmitting(false)
    }
  }

  const getPermSummary = (permissions: Record<string, string[]>) => {
    const entries = Object.entries(permissions).filter(([, v]) => v && v.length > 0)
    if (entries.length === 0) return <Tag>无权限</Tag>
    if (entries.length >= ALL_PERM_KEYS.length) return <Tag color="green">全部权限</Tag>
    return <Tag color="blue">{entries.length} 个模块</Tag>
  }

  const userColumns = [
    { title: '用户名', dataIndex: 'username', key: 'username', width: 120, sorter: true },
    { title: '显示名', dataIndex: 'display_name', key: 'display_name', width: 140, sorter: true },
    {
      title: '角色', dataIndex: 'role_code', key: 'role_code', width: 100, sorter: true,
      filters: roles.map(r => ({ text: r.role_name, value: r.role_code })),
      render: (code: string, record: UserItem) => (
        <Tag color={roleColorMap[code] || 'default'}>{record.role_name}</Tag>
      ),
    },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80, sorter: true,
      filters: [{ text: '启用', value: 'true' }, { text: '停用', value: 'false' }],
      render: (v: boolean, record: UserItem) => (
        <Switch size="small" checked={v} checkedChildren="启用" unCheckedChildren="停用" onChange={() => handleToggleActive(record)} />
      ),
    },
    { title: '最后登录', dataIndex: 'last_login_time', key: 'last_login_time', width: 150, sorter: true, render: (v: string) => formatDateTime(v) },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 150, sorter: true, render: (v: string) => formatDateTime(v) },
    {
      title: '操作', key: 'action', width: 160, fixed: 'right' as const,
      render: (_: any, record: UserItem) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          <Button size="small" icon={<KeyOutlined />} onClick={() => openResetPwd(record)} title="重置密码" />
          <Popconfirm title="确认删除该用户？" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" icon={<DeleteOutlined />} danger />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const roleColumns = [
    { title: '角色编码', dataIndex: 'role_code', key: 'role_code', width: 140,
      render: (code: string) => <Tag color={roleColorMap[code] || 'default'}>{code}</Tag>,
    },
    { title: '角色名称', dataIndex: 'role_name', key: 'role_name', width: 140 },
    {
      title: '权限概览', dataIndex: 'permissions', key: 'permissions', width: 120,
      render: (perms: Record<string, string[]>) => getPermSummary(perms),
    },
    {
      title: '操作', key: 'action', width: 140, fixed: 'right' as const,
      render: (_: any, record: RoleItem) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => openEditRole(record)}>权限</Button>
          {record.role_code !== 'admin' && (
            <Popconfirm title="确认删除该角色？" description="删除前请确保该角色下无用户" onConfirm={() => handleDeleteRole(record.id)}>
              <Button size="small" icon={<DeleteOutlined />} danger />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const tabItems = [
    {
      key: 'users',
      label: <span><UserOutlined /> 用户管理</span>,
      children: (
        <>
          <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
            <Row gutter={12} align="middle">
              <Col flex="auto" />
              <Col><Space>
                <Button icon={<ReloadOutlined />} onClick={() => fetchUsers()}>刷新</Button>
                <Button icon={<ExportOutlined />} loading={exporting} onClick={() => setExportColumnModalOpen(true)}>导出</Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={openAdd}>新增用户</Button>
              </Space></Col>
            </Row>
          </div>
          <div className="card-modern" style={{ padding: '0 0 4px', flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <Table columns={userColumns} dataSource={users} rowKey="id" loading={loading} size="small" scroll={{ x: 800, y: 'calc(100vh - 310px)' }}
              onChange={(_pag: any, tableFilters: any, sorter: any) => {
                const sortField = sorter.field
                const sortOrder = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : undefined
                const newFilters: Record<string, string[]> = {}
                if (tableFilters.role_code?.length) newFilters.role_code = tableFilters.role_code
                if (tableFilters.is_active?.length) newFilters.is_active = tableFilters.is_active
                fetchUsers(sortField, sortOrder, newFilters)
              }}
              pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`, pageSizeOptions: ['20', '50', '100'] }} />
          </div>
        </>
      ),
    },
    {
      key: 'roles',
      label: <span><SafetyOutlined /> 角色权限</span>,
      children: (
        <>
          <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
            <Row gutter={12} align="middle">
              <Col flex="auto" />
              <Col><Space>
                <Button icon={<ReloadOutlined />} onClick={fetchRoles}>刷新</Button>
                <Button icon={<ThunderboltOutlined />} onClick={openBatchGrant}>批量授权</Button>
                <Button type="primary" icon={<PlusOutlined />} onClick={openAddRole}>新增角色</Button>
              </Space></Col>
            </Row>
          </div>
          <div className="card-modern" style={{ padding: '0 0 4px', flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <Table columns={roleColumns} dataSource={roles} rowKey="id" loading={roleLoading} size="small" scroll={{ x: 900, y: 'calc(100vh - 310px)' }}
              pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`, pageSizeOptions: ['20', '50', '100'] }} />
          </div>
        </>
      ),
    },
  ]

  return (
    <div style={{ height: 'calc(100vh - 130px)', display: 'flex', flexDirection: 'column' }}>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabItems} style={{ marginBottom: 0, flex: '0 0 auto' }} />

      <ExportColumnSelector
        open={exportColumnModalOpen}
        columns={USER_EXPORT_COLUMNS}
        onConfirm={handleExportUsers}
        onCancel={() => setExportColumnModalOpen(false)}
      />

      {/* 新增/编辑用户 */}
      <Modal title={editingUser ? '编辑用户' : '新增用户'} open={modalOpen} onOk={handleSave} onCancel={() => setModalOpen(false)} width={480}>
        <Form form={form} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input placeholder="登录用户名" disabled={!!editingUser} />
          </Form.Item>
          <Form.Item name="display_name" label="显示名称">
            <Input placeholder="如：计划员 张三" />
          </Form.Item>
          {!editingUser && (
            <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }, { min: 6, message: '密码至少6位' }]}>
              <Input.Password placeholder="至少6位" />
            </Form.Item>
          )}
          <Form.Item name="role_id" label="角色" rules={[{ required: true, message: '请选择角色' }]}>
            <Select placeholder="选择角色" options={roles.map(r => ({ value: r.id, label: r.role_name }))} />
          </Form.Item>
          <Form.Item name="is_active" label="状态" valuePropName="checked">
            <Switch checkedChildren="启用" unCheckedChildren="停用" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 重置密码 */}
      <Modal title={`重置密码 — ${pwdUser?.username}`} open={pwdModalOpen} onOk={handleResetPwd} onCancel={() => setPwdModalOpen(false)} width={400}>
        <Form form={pwdForm} layout="vertical">
          <Form.Item name="new_password" label="新密码" rules={[{ required: true, message: '请输入新密码' }, { min: 6, message: '密码至少6位' }]}>
            <Input.Password placeholder="至少6位" />
          </Form.Item>
          <Form.Item name="confirm_password" label="确认密码" dependencies={['new_password']}
            rules={[
              { required: true, message: '请确认密码' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('new_password') === value) return Promise.resolve()
                  return Promise.reject(new Error('两次密码不一致'))
                },
              }),
            ]}>
            <Input.Password placeholder="再次输入新密码" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 新增/编辑角色 + 权限矩阵 */}
      <Modal
        title={editingRole ? `编辑角色权限 — ${editingRole.role_name}` : '新增角色'}
        open={roleModalOpen} onOk={handleSaveRole} onCancel={() => setRoleModalOpen(false)} width={780} destroyOnClose
      >
        <Form form={roleForm} layout="vertical">
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="role_code" label="角色编码" rules={[{ required: true, message: '请输入角色编码' }]}>
                <Input placeholder="如: planner" disabled={!!editingRole} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="role_name" label="角色名称" rules={[{ required: true, message: '请输入角色名称' }]}>
                <Input placeholder="如: 生产计划员" />
              </Form.Item>
            </Col>
          </Row>
        </Form>
        <div style={{ marginTop: 8, padding: '12px', border: '1px solid #f0f0f0', borderRadius: 6, background: '#fafafa' }}>
          <div style={{ fontWeight: 500, marginBottom: 8 }}>权限配置</div>
          <PermissionMatrix value={rolePermissions} onChange={setRolePermissions} />
        </div>
      </Modal>

      {/* 批量授权 */}
      <Modal
        title={<span><ThunderboltOutlined /> 批量授权 — 一次将权限分配给多个角色</span>}
        open={bgOpen}
        onOk={handleBatchGrant}
        onCancel={() => setBgOpen(false)}
        confirmLoading={bgSubmitting}
        width={880}
        destroyOnClose
        okText="确认应用"
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="操作说明"
          description={
            <div style={{ fontSize: 13 }}>
              选择要分配的「权限项」+「操作」，再勾选「目标角色」，点击应用即可一次完成多角色赋权。<br />
              <b>追加</b>：在角色已有权限上并集合并；<b>撤销</b>：从角色权限中移除指定操作；<b>覆盖</b>：以本次操作集合替换这些权限项。<br />
              admin 角色自动跳过（默认全权限）。
            </div>
          }
        />
        <Row gutter={16}>
          <Col span={12}>
            <div style={{ fontWeight: 500, marginBottom: 6 }}>① 权限项（菜单/子页面）</div>
            <div style={{ border: '1px solid #f0f0f0', borderRadius: 4, padding: 8, maxHeight: 360, overflow: 'auto' }}>
              <Tree
                checkable
                selectable={false}
                defaultExpandAll
                treeData={PERM_TREE_DATA}
                checkedKeys={bgKeys}
                onCheck={(checked: any) => {
                  const keys = Array.isArray(checked) ? checked : checked.checked
                  setBgKeys(keys.map((k: any) => String(k)))
                }}
              />
            </div>
            <Divider style={{ margin: '12px 0 8px' }} />
            <div style={{ fontWeight: 500, marginBottom: 6 }}>② 操作</div>
            <Checkbox.Group
              value={bgActions}
              onChange={(v) => setBgActions(v as string[])}
              options={PERMISSION_ACTIONS.map(a => ({ value: a.key, label: a.label }))}
            />
          </Col>
          <Col span={12}>
            <div style={{ fontWeight: 500, marginBottom: 6 }}>
              ③ 目标角色
              <Button
                size="small"
                type="link"
                onClick={() => {
                  const allIds = roles.filter(r => r.role_code !== 'admin').map(r => r.id)
                  setBgRoleIds(bgRoleIds.length === allIds.length ? [] : allIds)
                }}
              >
                全选 / 反选
              </Button>
            </div>
            <div style={{ border: '1px solid #f0f0f0', borderRadius: 4, padding: 8, maxHeight: 240, overflow: 'auto' }}>
              <Checkbox.Group
                value={bgRoleIds}
                onChange={(v) => setBgRoleIds(v as number[])}
                style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
              >
                {roles.map(r => (
                  <Checkbox key={r.id} value={r.id} disabled={r.role_code === 'admin'}>
                    <Tag color={roleColorMap[r.role_code] || 'default'} style={{ marginRight: 4 }}>{r.role_code}</Tag>
                    {r.role_name}
                    {r.role_code === 'admin' && <span style={{ color: '#999', marginLeft: 6, fontSize: 12 }}>（默认全权限，自动跳过）</span>}
                  </Checkbox>
                ))}
              </Checkbox.Group>
            </div>
            <Divider style={{ margin: '12px 0 8px' }} />
            <div style={{ fontWeight: 500, marginBottom: 6 }}>④ 应用模式</div>
            <Radio.Group value={bgMode} onChange={e => setBgMode(e.target.value)}>
              <Radio value="grant">追加（并集）</Radio>
              <Radio value="revoke">撤销</Radio>
              <Radio value="replace">覆盖</Radio>
            </Radio.Group>
          </Col>
        </Row>
      </Modal>
    </div>
  )
}
