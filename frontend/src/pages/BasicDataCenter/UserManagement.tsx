import { useState, useEffect, useRef } from 'react'
import { Table, Tag, Button, Modal, Form, Input, Select, Space, message, Popconfirm, Switch, Row, Col } from 'antd'
import { PlusOutlined, EditOutlined, DeleteOutlined, KeyOutlined, ReloadOutlined, ExportOutlined, SyncOutlined, UserAddOutlined, SearchOutlined, TeamOutlined } from '@ant-design/icons'
import api, { userApi, wecomApi, type WecomUser } from '../../services/api'
import ExportColumnSelector, { type ExportColumnOption } from '../../components/ExportColumnSelector'
import { useExport } from '../../hooks/useExport'
import { formatDateTime } from '../../utils'
import { useAuthStore } from '../../store/auth'

const roleColorMap: Record<string, string> = {
  admin: 'purple',
  planner: 'blue',
  purchaser: 'orange',
  manager: 'cyan',
  purchase_manager: 'gold',
  supplier: 'green',
}

interface SupplierOption {
  supplier_code?: string
  supplier_name: string
  status: number
}

interface EmployeeOption {
  emp_code: string
  emp_name: string
  login_id?: string
  position_id?: number
  position_name?: string
  role_id?: number
  role_code?: string
  role_name?: string
  oa_user_id?: string
  manager_oa_user_id?: string
  status: number
}

const SUPPLIER_PAGE_SIZE = 100

interface RoleItem {
  id: number
  role_code: string
  role_name: string
  permissions: Record<string, string[]>
}

interface UserItem {
  id: number
  username: string
  display_name: string | null
  emp_code: string | null
  emp_name: string | null
  position_id: number | null
  position_name: string | null
  org_name: string | null
  manager_name: string | null
  role_id: number
  role_code: string
  role_name: string
  supplier_name: string | null
  wecom_user_id: string | null
  is_active: boolean
  is_default_password: boolean
  last_login_time: string | null
  created_at: string | null
  updated_at: string | null
}

const USER_EXPORT_COLUMNS: ExportColumnOption[] = [
  { field: 'username', label: '用户名' },
  { field: 'display_name', label: '显示名称' },
  { field: 'emp_code', label: '员工工号' },
  { field: 'emp_name', label: '员工姓名' },
  { field: 'position_name', label: '岗位' },
  { field: 'org_name', label: '所属组织' },
  { field: 'manager_name', label: '上级' },
  { field: 'role_code', label: '角色编码' },
  { field: 'role_name', label: '角色名称' },
  { field: 'supplier_name', label: '绑定供应商' },
  { field: 'is_active', label: '状态' },
  { field: 'is_default_password', label: '默认密码' },
  { field: 'last_login_time', label: '最后登录' },
  { field: 'created_at', label: '创建时间' },
  { field: 'updated_at', label: '更新时间' },
]

export default function UserManagement() {
  const { exporting, exportData } = useExport()
  const isAdmin = useAuthStore(s => s.isAdmin())
  const hasPermission = useAuthStore(s => s.hasPermission)
  const [users, setUsers] = useState<UserItem[]>([])
  const [roles, setRoles] = useState<RoleItem[]>([])
  const [suppliers, setSuppliers] = useState<SupplierOption[]>([])
  const [employeeOptions, setEmployeeOptions] = useState<EmployeeOption[]>([])
  const [employeeLoading, setEmployeeLoading] = useState(false)
  const [supplierLoading, setSupplierLoading] = useState(false)
  const [wecomUsers, setWecomUsers] = useState<WecomUser[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [pwdModalOpen, setPwdModalOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<UserItem | null>(null)
  const [pwdUser, setPwdUser] = useState<UserItem | null>(null)
  const [form] = Form.useForm()
  const [pwdForm] = Form.useForm()
  const [exportColumnModalOpen, setExportColumnModalOpen] = useState(false)
  const [syncingRoles, setSyncingRoles] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [userQuery, setUserQuery] = useState<{ sortBy?: string; sortOrder?: string; filters?: Record<string, string[]> }>({})
  const [userPage, setUserPage] = useState(1)
  const [userPageSize, setUserPageSize] = useState(20)
  const [userTotal, setUserTotal] = useState(0)
  const employeeSearchTimer = useRef<number | undefined>(undefined)
  const supplierSearchTimer = useRef<number | undefined>(undefined)
  const supplierRequestSeq = useRef(0)
  const selectedRoleId = Form.useWatch('role_id', form)
  const selectedEmpCode = Form.useWatch('emp_code', form)
  const selectedRole = roles.find(r => r.id === selectedRoleId)
  const isSupplierRole = selectedRole?.role_code === 'supplier'
  const selectedEmployee = employeeOptions.find(item => item.emp_code === selectedEmpCode)
  const hasPositionRole = !!selectedEmployee?.role_id

  // ======== 批量开通员工 ========
  const [unprovLoading, setUnprovLoading] = useState(false)
  const [unprovEmployees, setUnprovEmployees] = useState<any[]>([])
  const [unprovTotal, setUnprovTotal] = useState(0)
  const [unprovSelected, setUnprovSelected] = useState<string[]>([])
  const [unprovPage, setUnprovPage] = useState(1)
  const [unprovPageSize, setUnprovPageSize] = useState(100)
  const [unprovKeyword, setUnprovKeyword] = useState('')
  const [unprovOrgFilter, setUnprovOrgFilter] = useState<string | undefined>()
  const [unprovPosFilter, setUnprovPosFilter] = useState<string | undefined>()
  const [unprovOrgOptions, setUnprovOrgOptions] = useState<string[]>([])
  const [unprovPosOptions, setUnprovPosOptions] = useState<string[]>([])
  const [provisionModalOpen, setProvisionModalOpen] = useState(false)
  const [provisioning, setProvisioning] = useState(false)

  // ======== 批量操作 ========
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([])
  const [batchLoading, setBatchLoading] = useState(false)
  const [confirmModalOpen, setConfirmModalOpen] = useState(false)
  const [confirmAction, setConfirmAction] = useState<'reset_password' | 'delete' | null>(null)
  const [confirmInput, setConfirmInput] = useState('')
  const [isSelectAllFiltered, setIsSelectAllFiltered] = useState(false)
  const justHandledSelectAllRef = useRef(false)

  const buildFilter = () => {
    const f: Record<string, any> = {}
    if (userQuery.filters?.role_code?.length) f.role_code = userQuery.filters.role_code.join(',')
    if (userQuery.filters?.is_active?.length) f.is_active = userQuery.filters.is_active[0] === 'true'
    if (userQuery.filters?.position_name?.length) f.position_name = userQuery.filters.position_name.join(',')
    if (userQuery.filters?.org_name?.length) f.org_name = userQuery.filters.org_name.join(',')
    if (userQuery.filters?.supplier_name?.length) f.supplier_name = userQuery.filters.supplier_name.join(',')
    return f
  }

  const openConfirmModal = (action: 'reset_password' | 'delete') => {
    setConfirmAction(action)
    setConfirmInput('')
    setConfirmModalOpen(true)
  }

  const handleConfirmOk = () => {
    const expected = confirmAction === 'delete' ? '删除' : '重置'
    if (confirmInput !== expected) {
      message.warning(`请输入"${expected}"以确认操作`)
      return
    }
    setConfirmModalOpen(false)
    if (confirmAction === 'delete') {
      handleBatchDelete()
    } else {
      handleBatchResetPassword()
    }
  }

  const fetchUnprovisioned = async (opts?: { page?: number; pageSize?: number; keyword?: string; orgName?: string; positionName?: string }) => {
    setUnprovLoading(true)
    try {
      const p = opts?.page ?? unprovPage
      const ps = opts?.pageSize ?? unprovPageSize
      const kw = opts?.keyword !== undefined ? opts?.keyword : unprovKeyword
      const orgName = opts?.orgName !== undefined ? opts?.orgName : unprovOrgFilter
      const posName = opts?.positionName !== undefined ? opts?.positionName : unprovPosFilter
      const params: Record<string, any> = { page: p, page_size: ps }
      if (kw?.trim()) params.keyword = kw.trim()
      if (orgName) params.org_name = orgName
      if (posName) params.position_name = posName
      const res: any = await userApi.listUnprovisionedEmployees(params)
      const data = res?.data || {}
      setUnprovEmployees(data.items || [])
      setUnprovTotal(data.total || 0)
      setUnprovOrgOptions(data.org_options || [])
      setUnprovPosOptions(data.position_options || [])
    } catch {
      // message.error('加载待开通员工列表失败')
    } finally {
      setUnprovLoading(false)
    }
  }

  const handleOpenProvision = () => {
    setUnprovSelected([])
    setUnprovKeyword('')
    setUnprovOrgFilter(undefined)
    setUnprovPosFilter(undefined)
    setProvisionModalOpen(true)
    fetchUnprovisioned({ page: 1, pageSize: unprovPageSize, keyword: '', orgName: undefined, positionName: undefined })
  }

  const handleBatchProvision = async () => {
    if (unprovSelected.length === 0) {
      message.warning('请选择至少一名员工')
      return
    }
    setProvisioning(true)
    try {
      const res: any = await userApi.batchProvision({
        emp_codes: unprovSelected,
        // role_id 不传 — 后端自动按员工岗位 + 组织匹配
      })
      const data = res?.data || {}
      const created = data.created || 0
      const skipped = data.skipped || 0
      const errors = data.errors || []
      const defaultPwd = data.default_password || '默认密码'
      const parts = [`成功开通 ${created} 个用户`]
      if (skipped > 0) parts.push(`跳过 ${skipped} 个已存在用户`)
      parts.push(`默认密码：${defaultPwd}`)
      if (errors.length > 0) {
        parts.push(`${errors.length} 条异常（详情见日志）`)
        message.warning(parts.join('，'))
      } else {
        message.success(parts.join('，'))
      }
      setProvisionModalOpen(false)
      setUnprovSelected([])
      fetchUsers()
    } catch {
      // error handled by interceptor
    } finally {
      setProvisioning(false)
    }
  }

  const fetchUsers = async (opts?: { page?: number; pageSize?: number; sortBy?: string; sortOrder?: string; filters?: Record<string, string[]>; keyword?: string }) => {
    const p = opts?.page ?? userPage
    const ps = opts?.pageSize ?? userPageSize
    const sortBy = opts?.sortBy ?? userQuery.sortBy
    const sortOrder = opts?.sortOrder ?? userQuery.sortOrder
    const filters = opts?.filters ?? userQuery.filters
    const kw = opts?.keyword ?? keyword
    setUserQuery({ sortBy, sortOrder, filters })
    setLoading(true)
    try {
      const params: any = { page: p, page_size: ps }
      if (sortBy) params.sort_by = sortBy
      if (sortOrder) params.sort_order = sortOrder
      if (kw?.trim()) params.keyword = kw.trim()
      if (filters?.role_code?.length) params.role_code = filters.role_code.join(',')
      if (filters?.is_active?.length) params.is_active = filters.is_active[0] === 'true'
      if (filters?.position_name?.length) params.position_name = filters.position_name.join(',')
      if (filters?.org_name?.length) params.org_name = filters.org_name.join(',')
      if (filters?.supplier_name?.length) params.supplier_name = filters.supplier_name.join(',')
      const res: any = await userApi.list(params)
      const payload = res?.data
      if (Array.isArray(payload)) {
        setUsers(payload)
        setUserTotal(payload.length)
      } else {
        setUsers(payload?.items || [])
        setUserTotal(payload?.total ?? 0)
      }
    } catch {
      message.error('加载用户列表失败')
    } finally {
      setLoading(false)
    }
  }

  const fetchRoles = async () => {
    try {
      const res: any = await userApi.roles({ page_size: 500 })
      const payload = res?.data
      if (Array.isArray(payload)) {
        setRoles(payload)
      } else {
        setRoles(payload?.items || [])
      }
    } catch {
      message.error('加载角色列表失败')
    }
  }

  const fetchEmployeeOptions = async (keyword = '') => {
    setEmployeeLoading(true)
    try {
      const params: { keyword?: string } = {}
      if (keyword.trim()) params.keyword = keyword.trim()
      const res: any = await userApi.employeeOptions(params)
      setEmployeeOptions(res.data || [])
    } catch {
      message.error('加载员工列表失败')
    } finally {
      setEmployeeLoading(false)
    }
  }

  const fetchWecomUsers = async () => {
    try {
      const res: any = await wecomApi.listUsers()
      setWecomUsers(res.data || [])
    } catch {
      // 企业微信未配置或网络异常：静默，下拉为空，校验由后端兜底
    }
  }

  const mergeSuppliers = (list: SupplierOption[]) => {
    const map = new Map<string, SupplierOption>()
    list.forEach(item => {
      if (item.supplier_name) map.set(item.supplier_name, item)
    })
    return Array.from(map.values())
  }

  const fetchSuppliers = async (keyword = '') => {
    const requestSeq = ++supplierRequestSeq.current
    setSupplierLoading(true)
    try {
      const params: Record<string, any> = {
        page: 1,
        page_size: SUPPLIER_PAGE_SIZE,
        status: '1',
        sort_by: 'supplier_name',
        sort_order: 'asc',
      }
      if (keyword.trim()) params.keyword = keyword.trim()

      const firstRes: any = await api.get('/basicdata/suppliers', { params })
      const data = firstRes.data || {}
      let items: SupplierOption[] = data.items || []

      const total = data.total || items.length
      const totalPages = Math.ceil(total / SUPPLIER_PAGE_SIZE)
      for (let page = 2; page <= totalPages; page += 1) {
        const res: any = await api.get('/basicdata/suppliers', { params: { ...params, page } })
        items = [...items, ...(res.data?.items || [])]
      }

      if (requestSeq === supplierRequestSeq.current) {
        setSuppliers(prev => keyword.trim() ? mergeSuppliers([...prev, ...items]) : mergeSuppliers(items))
      }
    } catch {
      message.error('加载供应商列表失败')
    } finally {
      if (requestSeq === supplierRequestSeq.current) {
        setSupplierLoading(false)
      }
    }
  }

  const handleSupplierSearch = (keyword: string) => {
    if (supplierSearchTimer.current) window.clearTimeout(supplierSearchTimer.current)
    supplierSearchTimer.current = window.setTimeout(() => {
      fetchSuppliers(keyword)
    }, 300)
  }

  const handleEmployeeSearch = (keyword: string) => {
    if (employeeSearchTimer.current) window.clearTimeout(employeeSearchTimer.current)
    employeeSearchTimer.current = window.setTimeout(() => {
      fetchEmployeeOptions(keyword)
    }, 300)
  }

  useEffect(() => {
    fetchUsers()
    fetchRoles()
    fetchEmployeeOptions()
    fetchSuppliers()
    fetchWecomUsers()

    return () => {
      if (employeeSearchTimer.current) window.clearTimeout(employeeSearchTimer.current)
      if (supplierSearchTimer.current) window.clearTimeout(supplierSearchTimer.current)
    }
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
      emp_code: record.emp_code,
      role_id: record.role_id,
      supplier_name: record.supplier_name,
      wecom_user_id: record.wecom_user_id,
      is_active: record.is_active,
    })
    if (record.emp_code && !employeeOptions.some(item => item.emp_code === record.emp_code)) {
      setEmployeeOptions(prev => [
        ...prev,
        {
          emp_code: record.emp_code!,
          emp_name: record.emp_name || record.display_name || record.emp_code!,
          position_id: record.position_id || undefined,
          position_name: record.position_name || undefined,
          role_id: record.role_id,
          role_code: record.role_code,
          role_name: record.role_name,
          status: record.is_active ? 1 : 5,
        },
      ])
    }
    setModalOpen(true)
  }

  const handleEmployeeChange = (empCode?: string) => {
    if (!empCode) {
      form.setFieldsValue({ emp_code: undefined, role_id: undefined })
      return
    }
    const employee = employeeOptions.find(item => item.emp_code === empCode)
    if (!employee) {
      form.setFieldsValue({ emp_code: empCode })
      return
    }
    form.setFieldsValue({
      emp_code: employee.emp_code,
      display_name: employee.emp_name,
      role_id: employee.role_id || undefined,
    })
    if (!editingUser) {
      form.setFieldsValue({
        username: employee.login_id || employee.emp_code,
        password: employee.emp_code,
      })
    }
    if (!employee.role_id) {
      message.warning('该员工岗位暂未绑定角色，请手动选择角色')
    }
  }

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      if (editingUser) {
        await userApi.update(editingUser.id, {
          display_name: values.display_name,
          role_id: values.role_id,
          emp_code: values.emp_code,
          supplier_name: values.supplier_name,
          wecom_user_id: values.wecom_user_id,
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
      fetchUsers({ sortBy: userQuery.sortBy, sortOrder: userQuery.sortOrder, filters: userQuery.filters })
    } catch {
      message.error('操作失败')
    }
  }

  const handleExportUsers = (selectedColumns: string[]) => {
    const params: Record<string, any> = { format: 'xlsx', columns: selectedColumns.join(',') }
    if (keyword?.trim()) params.keyword = keyword.trim()
    if (userQuery.sortBy) params.sort_by = userQuery.sortBy
    if (userQuery.sortOrder) params.sort_order = userQuery.sortOrder
    if (userQuery.filters?.role_code?.length) params.role_code = userQuery.filters.role_code.join(',')
    if (userQuery.filters?.is_active?.length) params.is_active = userQuery.filters.is_active[0] === 'true'
    if (userQuery.filters?.position_name?.length) params.position_name = userQuery.filters.position_name.join(',')
    if (userQuery.filters?.org_name?.length) params.org_name = userQuery.filters.org_name.join(',')
    if (userQuery.filters?.supplier_name?.length) params.supplier_name = userQuery.filters.supplier_name.join(',')
    setExportColumnModalOpen(false)
    exportData('/api/v1/basicdata/users/export', params, '用户管理.xlsx')
  }

  const handleSyncRoles = async () => {
    setSyncingRoles(true)
    try {
      const res: any = await userApi.syncRoles()
      const data = res?.data
      const parts = [`共检查 ${data?.total ?? 0} 个用户，更新 ${data?.updated ?? 0} 个用户角色`]
      if (data?.created) parts.push(`新建 ${data.created} 个角色`)
      message.success(`同步完成：${parts.join('，')}`)
      fetchUsers()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '同步角色失败')
    } finally {
      setSyncingRoles(false)
    }
  }

  // ======== 批量操作 ========
  const handleBatchToggleActive = async (isActive: boolean) => {
    setBatchLoading(true)
    try {
      const payload: any = { is_active: isActive }
      if (isSelectAllFiltered) {
        const f = buildFilter()
        if (Object.keys(f).length) payload.filter = f
      } else {
        if (!selectedRowKeys.length) {
          message.warning('请先选择用户')
          setBatchLoading(false)
          return
        }
        payload.user_ids = selectedRowKeys
      }
      const res: any = await userApi.batchToggleActive(payload)
      const data = res?.data
      message.success(`已${data?.action} ${data?.updated ?? 0} 个用户`)
      setSelectedRowKeys([])
      setIsSelectAllFiltered(false)
      fetchUsers({ sortBy: userQuery.sortBy, sortOrder: userQuery.sortOrder, filters: userQuery.filters })
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '操作失败')
    } finally {
      setBatchLoading(false)
    }
  }

  const handleBatchResetPassword = async () => {
    setBatchLoading(true)
    try {
      const payload: any = {}
      if (isSelectAllFiltered) {
        const f = buildFilter()
        if (Object.keys(f).length) payload.filter = f
      } else {
        if (!selectedRowKeys.length) {
          message.warning('请先选择用户')
          setBatchLoading(false)
          return
        }
        payload.user_ids = selectedRowKeys
      }
      const res: any = await userApi.batchResetPassword(payload)
      const data = res?.data
      message.success(`已重置 ${data?.updated ?? 0} 个用户密码，默认密码：${data?.default_password ?? 'admin123'}`)
      setSelectedRowKeys([])
      setIsSelectAllFiltered(false)
      fetchUsers({ sortBy: userQuery.sortBy, sortOrder: userQuery.sortOrder, filters: userQuery.filters })
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '重置密码失败')
    } finally {
      setBatchLoading(false)
    }
  }

  const handleBatchDelete = async () => {
    setBatchLoading(true)
    try {
      const payload: any = {}
      if (isSelectAllFiltered) {
        const f = buildFilter()
        if (Object.keys(f).length) payload.filter = f
      } else {
        if (!selectedRowKeys.length) {
          message.warning('请先选择用户')
          setBatchLoading(false)
          return
        }
        payload.user_ids = selectedRowKeys
      }
      const res: any = await userApi.batchDelete(payload)
      const data = res?.data
      message.success(`已删除 ${data?.deleted ?? 0} 个用户`)
      setSelectedRowKeys([])
      setIsSelectAllFiltered(false)
      fetchUsers({ sortBy: userQuery.sortBy, sortOrder: userQuery.sortOrder, filters: userQuery.filters })
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '删除失败')
    } finally {
      setBatchLoading(false)
    }
  }

  const userColumns = [
    { title: '用户名', dataIndex: 'username', key: 'username', width: 120, sorter: true },
    { title: '显示名', dataIndex: 'display_name', key: 'display_name', width: 140, sorter: true },
    {
      title: '员工',
      dataIndex: 'emp_name',
      key: 'emp_code',
      width: 160,
      sorter: true,
      render: (_: string | null, record: UserItem) => record.emp_code
        ? <span>{record.emp_name || record.emp_code} <span style={{ color: '#94a3b8' }}>({record.emp_code})</span></span>
        : <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '岗位',
      dataIndex: 'position_name',
      key: 'position_name',
      width: 130,
      sorter: true,
      filters: [...new Set(users.map(u => u.position_name).filter(Boolean))].map(v => ({ text: v, value: v! })),
      filterSearch: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '所属组织',
      dataIndex: 'org_name',
      key: 'org_name',
      width: 140,
      sorter: true,
      filters: [...new Set(users.map(u => u.org_name).filter(Boolean))].map(v => ({ text: v, value: v! })),
      filterSearch: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '上级',
      dataIndex: 'manager_name',
      key: 'manager_name',
      width: 100,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '角色', dataIndex: 'role_code', key: 'role_code', width: 100, sorter: true,
      filters: roles.map(r => ({ text: r.role_name, value: r.role_code })),
      render: (code: string, record: UserItem) => (
        <Tag color={roleColorMap[code] || 'default'}>{record.role_name}</Tag>
      ),
    },
    {
      title: '绑定供应商', dataIndex: 'supplier_name', key: 'supplier_name', width: 180, sorter: true,
      filters: [...new Set(users.map(u => u.supplier_name).filter(Boolean))].map(v => ({ text: v, value: v! })),
      filterSearch: true,
      render: (v: string | null) => v || <span style={{ color: '#cbd5e1' }}>-</span>,
    },
    {
      title: '企业微信', dataIndex: 'wecom_user_id', key: 'wecom_user_id', width: 150,
      render: (v: string | null) => {
        if (!v) return <span style={{ color: '#cbd5e1' }}>-</span>
        const u = wecomUsers.find(item => item.userid === v)
        return u
          ? <span>{u.name} <span style={{ color: '#94a3b8' }}>({v})</span></span>
          : <span>{v}</span>
      },
    },
    {
      title: '状态', dataIndex: 'is_active', key: 'is_active', width: 80, sorter: true,
      filters: [{ text: '启用', value: 'true' }, { text: '停用', value: 'false' }],
      render: (v: boolean, record: UserItem) => (
        <Switch size="small" checked={v} checkedChildren="启用" unCheckedChildren="停用" onChange={() => handleToggleActive(record)} />
      ),
    },
    {
      title: '默认密码', dataIndex: 'is_default_password', key: 'is_default_password', width: 90,
      render: (v: boolean) => (
        <Tag color={v ? 'orange' : 'default'}>{v ? '是' : '否'}</Tag>
      ),
    },
    { title: '最后登录', dataIndex: 'last_login_time', key: 'last_login_time', width: 150, sorter: true, render: (v: string) => formatDateTime(v) },
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 150, sorter: true, render: (v: string) => formatDateTime(v) },
    {
      title: '操作', key: 'action', width: 160, fixed: 'right' as const,
      render: (_: any, record: UserItem) => (
        <Space size="small">
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} />
          {hasPermission('users', 'reset_password') && <Button size="small" icon={<KeyOutlined />} onClick={() => openResetPwd(record)} title="重置密码" />}
          {isAdmin && (
            <Popconfirm title="确认删除该用户？" onConfirm={() => handleDelete(record.id)}>
              <Button size="small" icon={<DeleteOutlined />} danger />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div style={{ height: 'calc(100vh - 130px)', display: 'flex', flexDirection: 'column' }}>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col flex="auto">
            <Space>
              <Input
                prefix={<SearchOutlined />}
                placeholder="搜索用户名 / 显示名 / 工号 / 姓名"
                value={keyword}
                allowClear
                onChange={(e) => {
                  setKeyword(e.target.value)
                  if (!e.target.value) {
                    setUserPage(1)
                    fetchUsers({ page: 1, keyword: '' })
                  }
                }}
                onPressEnter={() => { setUserPage(1); fetchUsers({ page: 1 }) }}
                style={{ width: 280 }}
              />
              {(selectedRowKeys.length > 0 || isSelectAllFiltered) && (
                <>
                  <span style={{ color: '#6b7280', fontSize: 13 }}>
                    {isSelectAllFiltered ? `已选中所有筛选结果（共 ${userTotal} 个用户）` : `已选 ${selectedRowKeys.length} 项`}
                  </span>
                  <Button size="small" loading={batchLoading} onClick={() => handleBatchToggleActive(true)}>批量启用</Button>
                  <Button size="small" loading={batchLoading} onClick={() => handleBatchToggleActive(false)}>批量停用</Button>
                  {hasPermission('users', 'reset_password') && <Button size="small" icon={<KeyOutlined />} loading={batchLoading} onClick={() => openConfirmModal('reset_password')}>批量重置密码</Button>}
                  {isAdmin && (
                    <Button size="small" danger icon={<DeleteOutlined />} loading={batchLoading} onClick={() => openConfirmModal('delete')}>批量删除</Button>
                  )}
                  <Button size="small" type="link" onClick={() => { setSelectedRowKeys([]); setIsSelectAllFiltered(false) }}>取消选择</Button>
                </>
              )}
            </Space>
          </Col>
          <Col><Space>
            <Button icon={<ReloadOutlined />} onClick={() => fetchUsers()}>刷新</Button>
            <Button icon={<SyncOutlined />} loading={syncingRoles} onClick={handleSyncRoles}>同步角色</Button>
            <Button icon={<ExportOutlined />} loading={exporting} onClick={() => setExportColumnModalOpen(true)}>导出</Button>
            {hasPermission('users', 'create') && <Button icon={<TeamOutlined />} onClick={handleOpenProvision}>批量开通用户</Button>}
            {isAdmin && <Button type="primary" icon={<UserAddOutlined />} onClick={openAdd}>新增用户</Button>}
          </Space></Col>
        </Row>
      </div>
      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table columns={userColumns} dataSource={users} rowKey="id" loading={loading} size="small" scroll={{ x: 1500, y: 'calc(100vh - 360px)' }}
          rowSelection={{
            type: 'checkbox',
            selectedRowKeys,
            onChange: (keys) => {
              if (justHandledSelectAllRef.current) {
                justHandledSelectAllRef.current = false
                return
              }
              setSelectedRowKeys(keys as number[])
              setIsSelectAllFiltered(false)
            },
            onSelectAll: (selected) => {
              if (selected) {
                justHandledSelectAllRef.current = true
                setIsSelectAllFiltered(true)
                setSelectedRowKeys([])
                message.info('已选中所有筛选结果，批量操作将应用到全部符合条件的用户')
              } else {
                setIsSelectAllFiltered(false)
                setSelectedRowKeys([])
              }
            },
          }}
          onChange={(pag: any, tableFilters: any, sorter: any) => {
            const sortField = sorter.field
            const sortOrder = sorter.order === 'ascend' ? 'asc' : sorter.order === 'descend' ? 'desc' : undefined
            const newFilters: Record<string, string[]> = {}
            if (tableFilters.role_code?.length) newFilters.role_code = tableFilters.role_code
            if (tableFilters.is_active?.length) newFilters.is_active = tableFilters.is_active
            if (tableFilters.position_name?.length) newFilters.position_name = tableFilters.position_name
            if (tableFilters.org_name?.length) newFilters.org_name = tableFilters.org_name
            if (tableFilters.supplier_name?.length) newFilters.supplier_name = tableFilters.supplier_name
            const newPage = typeof pag?.current === 'number' ? pag.current : userPage
            const newPageSize = typeof pag?.pageSize === 'number' ? pag.pageSize : userPageSize
            setUserPage(newPage)
            setUserPageSize(newPageSize)
            fetchUsers({ page: newPage, pageSize: newPageSize, sortBy: sortField, sortOrder, filters: newFilters })
          }}
          pagination={{ current: userPage, pageSize: userPageSize, total: userTotal, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`, pageSizeOptions: [20, 50, 100], showQuickJumper: true }} />
      </div>

      <ExportColumnSelector
        open={exportColumnModalOpen}
        columns={USER_EXPORT_COLUMNS}
        onConfirm={handleExportUsers}
        onCancel={() => setExportColumnModalOpen(false)}
      />

      {/* 新增/编辑用户 */}
      <Modal title={editingUser ? '编辑用户' : '新增用户'} open={modalOpen} onOk={handleSave} onCancel={() => setModalOpen(false)} width={560}>
        <Form form={form} layout="vertical">
          <Form.Item name="emp_code" label="关联员工">
            <Select
              allowClear
              showSearch
              placeholder="选择员工后自动匹配岗位权限"
              loading={employeeLoading}
              optionFilterProp="label"
              options={employeeOptions.map(employee => ({
                value: employee.emp_code,
                label: `${employee.emp_name} (${employee.emp_code})${employee.position_name ? ` - ${employee.position_name}` : ''}`,
              }))}
              filterOption={false}
              onSearch={handleEmployeeSearch}
              onDropdownVisibleChange={(open) => {
                if (open && employeeOptions.length === 0) fetchEmployeeOptions()
              }}
              onChange={handleEmployeeChange}
            />
          </Form.Item>
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
          <Form.Item name="role_id" label="角色" rules={[{ required: !hasPositionRole, message: '请选择角色' }]}>
            <Select
              placeholder={hasPositionRole ? '已从岗位自动获取角色' : '选择角色；关联员工后自动从岗位获取'}
              disabled={hasPositionRole}
              options={roles.map(r => ({ value: r.id, label: `${r.role_name} (${r.role_code})` }))}
              onChange={(roleId) => {
                const role = roles.find(r => r.id === roleId)
                if (role?.role_code !== 'supplier') {
                  form.setFieldValue('supplier_name', undefined)
                }
              }}
            />
          </Form.Item>
          {isSupplierRole && (
            <Form.Item name="supplier_name" label="绑定供应商" rules={[{ required: true, message: '请选择供应商' }]}>
              <Select
                showSearch
                placeholder="选择供应商"
                loading={supplierLoading}
                optionFilterProp="label"
                options={suppliers.map(s => ({
                  value: s.supplier_name,
                  label: s.supplier_name,
                  searchText: `${s.supplier_name} ${s.supplier_code || ''}`,
                }))}
                filterOption={(input, option) => String(option?.searchText || option?.label || '').toLowerCase().includes(input.toLowerCase())}
                onSearch={handleSupplierSearch}
                onDropdownVisibleChange={(open) => {
                  if (open && suppliers.length === 0) fetchSuppliers()
                }}
                onChange={(supplierName) => {
                  if (!editingUser && supplierName) {
                    form.setFieldsValue({
                      username: supplierName,
                      display_name: supplierName,
                      password: supplierName,
                    })
                  }
                }}
              />
            </Form.Item>
          )}
          <Form.Item name="wecom_user_id" label="企业微信账号">
            <Select
              allowClear
              showSearch
              placeholder="选择企业微信账号（可解绑）"
              optionFilterProp="label"
              options={wecomUsers.map(u => ({ value: u.userid, label: `${u.name} (${u.userid})` }))}
              notFoundContent="未加载到企业微信通讯录"
            />
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

      {/* 批量开通用户 — 选择员工 */}
      <Modal
        title="批量开通用户"
        open={provisionModalOpen}
        onOk={handleBatchProvision}
        onCancel={() => setProvisionModalOpen(false)}
        confirmLoading={provisioning}
        okText={`开通选中（${unprovSelected.length}）`}
        okButtonProps={{ disabled: unprovSelected.length === 0 }}
        cancelText="取消"
        width={1100}
        styles={{ body: { padding: '8px 24px 24px' } }}
      >
        <div style={{ margin: '8px 0 16px', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <Input
            prefix={<SearchOutlined />}
            placeholder="搜索工号 / 姓名 / 登录账号（空格分隔多人）"
            value={unprovKeyword}
            allowClear
            onChange={(e) => {
              setUnprovKeyword(e.target.value)
              setUnprovPage(1)
              fetchUnprovisioned({ page: 1, pageSize: unprovPageSize, keyword: e.target.value })
            }}
            onPressEnter={() => { setUnprovPage(1); fetchUnprovisioned() }}
            style={{ width: 280 }}
          />
          <Select
            allowClear
            placeholder="按岗位筛选"
            value={unprovPosFilter}
            onChange={(v) => {
              setUnprovPosFilter(v)
              setUnprovPage(1)
              fetchUnprovisioned({ page: 1, positionName: v })
            }}
            options={unprovPosOptions.map(v => ({ value: v, label: v }))}
            style={{ width: 180 }}
          />
          <Select
            allowClear
            placeholder="按组织筛选"
            value={unprovOrgFilter}
            onChange={(v) => {
              setUnprovOrgFilter(v)
              setUnprovPage(1)
              fetchUnprovisioned({ page: 1, orgName: v })
            }}
            options={unprovOrgOptions.map(v => ({ value: v, label: v }))}
            style={{ width: 200 }}
          />
          <Space style={{ marginLeft: 'auto' }}>
            <span style={{ color: '#6b7280', fontSize: 13 }}>共 {unprovTotal} 名员工</span>
            <Button icon={<ReloadOutlined />} onClick={() => fetchUnprovisioned()}>刷新</Button>
          </Space>
        </div>
        <Table
          rowKey="emp_code"
          size="small"
          loading={unprovLoading}
          dataSource={unprovEmployees}
          scroll={{ x: 1000, y: 420 }}
          rowSelection={{
            type: 'checkbox',
            selectedRowKeys: unprovSelected,
            onChange: (keys) => setUnprovSelected(keys as string[]),
          }}
          columns={[
            { title: '工号', dataIndex: 'emp_code', width: 140 },
            { title: '姓名', dataIndex: 'emp_name', width: 100 },
            { title: '登录账号', dataIndex: 'login_id', width: 140,
              render: (v: string) => v || <span style={{ color: '#cbd5e1' }}>-</span> },
            { title: '岗位', dataIndex: 'position_name', width: 160,
              render: (v: string) => v || <span style={{ color: '#cbd5e1' }}>-</span> },
            { title: '所属组织', dataIndex: 'org_name', width: 180,
              render: (v: string) => v || <span style={{ color: '#cbd5e1' }}>-</span> },
            { title: '员工状态', dataIndex: 'status', width: 100,
              render: (v: number) => {
                const map: Record<number, { text: string; color: string }> = {
                  0: { text: '试用期', color: 'cyan' },
                  1: { text: '在职', color: 'green' },
                  2: { text: '兼职', color: 'blue' },
                  3: { text: '外派', color: 'purple' },
                  4: { text: '解聘', color: 'red' },
                  5: { text: '离职', color: 'red' },
                  6: { text: '退休', color: 'gold' },
                  7: { text: '无效', color: 'default' },
                }
                const info = map[v] || { text: `状态${v}`, color: 'default' }
                return <Tag color={info.color}>{info.text}</Tag>
              } },
          ]}
          pagination={{
            current: unprovPage, pageSize: unprovPageSize, total: unprovTotal,
            showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条`,
            pageSizeOptions: [20, 50, 100, 200], showQuickJumper: true,
            onChange: (p: number, ps: number) => { setUnprovPage(p); setUnprovPageSize(ps); fetchUnprovisioned({ page: p, pageSize: ps }) },
            onShowSizeChange: (p: number, ps: number) => { setUnprovPage(1); setUnprovPageSize(ps); fetchUnprovisioned({ page: 1, pageSize: ps }) },
          }}
        />
      </Modal>

      {/* 高危操作二次确认 */}
      <Modal
        title={confirmAction === 'delete' ? '确认批量删除' : '确认批量重置密码'}
        open={confirmModalOpen}
        onOk={handleConfirmOk}
        onCancel={() => setConfirmModalOpen(false)}
        okButtonProps={{ danger: confirmAction === 'delete' }}
        okText="确认执行"
        cancelText="取消"
      >
        <p style={{ marginBottom: 12 }}>
          {confirmAction === 'delete'
            ? `即将删除 ${selectedRowKeys.length} 个用户，此操作不可恢复！`
            : `即将重置 ${selectedRowKeys.length} 个用户的密码为默认密码！`}
        </p>
        <p style={{ marginBottom: 8, color: '#6b7280' }}>
          请输入 <b style={{ color: '#dc2626' }}>{confirmAction === 'delete' ? '删除' : '重置'}</b> 以确认操作：
        </p>
        <Input
          value={confirmInput}
          onChange={(e) => setConfirmInput(e.target.value)}
          placeholder={`请输入"${confirmAction === 'delete' ? '删除' : '重置'}"`}
          onPressEnter={handleConfirmOk}
        />
      </Modal>
    </div>
  )
}
