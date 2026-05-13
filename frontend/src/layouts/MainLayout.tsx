import { useState, useMemo, useEffect } from 'react'
import { Outlet, useNavigate, useLocation, Link } from 'react-router-dom'
import { Layout, Menu, Button, Dropdown, Space, Breadcrumb, Modal, Form, Input, message, Result } from 'antd'
import {
  DashboardOutlined,
  ShoppingCartOutlined,
  WarningOutlined,
  ImportOutlined,
  SettingOutlined,
  KeyOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  UserOutlined,
  HomeOutlined,
  BellOutlined,
  FileTextOutlined,
  UnorderedListOutlined,
  ExperimentOutlined,
  ContainerOutlined,
  AuditOutlined,
  RocketOutlined,
  TeamOutlined,
  ProjectOutlined,
  ToolOutlined,
  DatabaseOutlined,
  AppstoreOutlined,
  SwapOutlined,
  AccountBookOutlined,
  MessageOutlined,
  FolderOpenOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '../store/auth'
import { authApi } from '../services/api'
import FeedbackButton from '../pages/MasterDataCenter/FeedbackManagement/FeedbackButton'
import { FloatingAssistant } from '../components/Assistant'

const { Sider, Content } = Layout

// ---------- Menu definition with permission-based visibility ----------
type PermissionAwareItem = {
  key: string
  icon?: React.ReactNode
  label: string
  permission?: string  // resource name — menu item visible if user has resource.read
  children?: PermissionAwareItem[]
}

const allMenuItems: PermissionAwareItem[] = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '供应链驾驶舱', permission: 'dashboard' },
  {
    key: 'order-delivery',
    icon: <FileTextOutlined />,
    label: '订单交付中心',
    permission: 'orders',
    children: [
      { key: '/orders', icon: <UnorderedListOutlined />, label: '订单总控台', permission: 'orders.list' },
      { key: '/run-orders', icon: <RocketOutlined />, label: '跑单管理', permission: 'orders.run_orders' },
      { key: '/order-risk-pool', icon: <WarningOutlined />, label: '订单风险池', permission: 'orders.risk_pool' },
    ],
  },
  {
    key: 'material-center',
    icon: <ExperimentOutlined />,
    label: '物料齐套中心',
    permission: 'materials',
    children: [
      { key: '/purchase-plan', icon: <ShoppingCartOutlined />, label: '采购到料计划', permission: 'materials.purchase_plan' },
      { key: '/material-issues', icon: <WarningOutlined />, label: '问题物料池', permission: 'materials.issues' },
      { key: '/long-lead-materials', icon: <ContainerOutlined />, label: '长交期物料池', permission: 'materials.long_lead' },
      { key: '/kit-analysis', icon: <AppstoreOutlined />, label: '齐套分析', permission: 'materials.kit_analysis' },
      { key: '/supplier-risk', icon: <AuditOutlined />, label: '供应商风险分析', permission: 'materials.supplier_risk' },
      { key: '/supplier-payment', icon: <AccountBookOutlined />, label: '供应商付款排程', permission: 'materials.supplier_payment' },
    ],
  },
  {
    key: 'production-center',
    icon: <RocketOutlined />,
    label: '生产协同中心',
    permission: 'production',
    children: [
      { key: '/production-overview', icon: <DashboardOutlined />, label: '生产总览', permission: 'production.overview' },
      { key: '/front-process', icon: <ContainerOutlined />, label: '前道管理', permission: 'production.front_process' },
      { key: '/smt', icon: <ExperimentOutlined />, label: '贴片管理', permission: 'production.smt' },
      { key: '/lean', icon: <AuditOutlined />, label: '精益管理', permission: 'production.lean' },
      { key: '/assembly', icon: <ToolOutlined />, label: '组装管理', permission: 'production.assembly' },
      { key: '/packaging', icon: <ContainerOutlined />, label: '包装管理', permission: 'production.packaging' },
      { key: '/process-exceptions', icon: <WarningOutlined />, label: '工序异常池', permission: 'production.exceptions' },
    ],
  },
  {
    key: 'exception-center',
    icon: <WarningOutlined />,
    label: '异常与质量中心',
    permission: 'exceptions',
    children: [
      { key: '/issues', icon: <WarningOutlined />, label: '异常总池', permission: 'exceptions.pool' },
      { key: '/issue-log', icon: <FileTextOutlined />, label: '问题日志', permission: 'exceptions.issue_log' },
      { key: '/change-log', icon: <SwapOutlined />, label: '变更日志', permission: 'exceptions.change_log' },
      { key: '/quality-issues', icon: <AuditOutlined />, label: '品质异常', permission: 'exceptions.quality' },
      { key: '/closure-tracking', icon: <AuditOutlined />, label: '闭环跟踪', permission: 'exceptions.closure' },
    ],
  },
  {
    key: 'meeting-center',
    icon: <TeamOutlined />,
    label: '会议与任务中心',
    children: [
      { key: '/meetings', icon: <TeamOutlined />, label: '会议与行动项', permission: 'meetings' },
    ],
  },
  {
    key: 'npi-center',
    icon: <ProjectOutlined />,
    label: '新品/NPI项目中心',
    children: [
      { key: '/npi', icon: <ProjectOutlined />, label: '项目总览', permission: 'npi' },
    ],
  },
  {
    key: 'rules-center',
    icon: <ToolOutlined />,
    label: '规则配置中心',
    permission: 'rules',
    children: [
      { key: '/risk-rules', icon: <SettingOutlined />, label: '预警规则', permission: 'rules.risk_rules' },
      { key: '/inspection-rules', icon: <AuditOutlined />, label: '点检规则', permission: 'rules.inspection' },
      { key: '/node-standards', icon: <ContainerOutlined />, label: '节点标准', permission: 'rules.node_standards' },
      { key: '/responsibility-map', icon: <TeamOutlined />, label: '责任归属', permission: 'rules.responsibility' },
      { key: '/status-dict', icon: <AppstoreOutlined />, label: '状态字典', permission: 'rules.status_dict' },
    ],
  },
  {
    key: 'masterdata-center',
    icon: <DatabaseOutlined />,
    label: '主数据与集成中心',
    children: [
      { key: '/import', icon: <ImportOutlined />, label: '数据集成', permission: 'masterdata.import' },
      {
        key: 'masterdata-management',
        icon: <DatabaseOutlined />,
        label: '主数据管理',
        permission: 'masterdata.data',
        children: [
          { key: '/masterdata/customers', icon: <UserOutlined />, label: '客户主数据', permission: 'masterdata.data' },
          { key: '/masterdata/suppliers', icon: <ShoppingCartOutlined />, label: '供应商主数据', permission: 'masterdata.data' },
          { key: '/masterdata/materials', icon: <AppstoreOutlined />, label: '物料主数据', permission: 'masterdata.data' },
          { key: '/masterdata/skus', icon: <ContainerOutlined />, label: 'SKU主数据', permission: 'masterdata.data' },
          { key: '/masterdata/products', icon: <FileTextOutlined />, label: '产品主数据', permission: 'masterdata.data' },
          { key: '/masterdata/warehouses', icon: <ContainerOutlined />, label: '仓库主数据', permission: 'masterdata.data' },
          { key: '/masterdata/processes', icon: <RocketOutlined />, label: '工序主数据', permission: 'masterdata.data' },
          { key: '/masterdata/organizations', icon: <TeamOutlined />, label: '组织主数据', permission: 'masterdata.data' },
          { key: '/masterdata/employees', icon: <UserOutlined />, label: '人员主数据', permission: 'masterdata.data' },
        ],
      },
      { key: '/users', icon: <UserOutlined />, label: '用户管理', permission: 'users' },
      { key: '/audit', icon: <AuditOutlined />, label: '审计日志', permission: 'audit' },
      { key: '/sync-config', icon: <SwapOutlined />, label: '同步SQL配置', permission: 'settings' },
      { key: '/masterdata/feedback', icon: <MessageOutlined />, label: '问题反馈', permission: 'masterdata.feedback' },
      { key: '/masterdata/files', icon: <FolderOpenOutlined />, label: '文件管理', permission: 'masterdata.files' },
    ],
  },
]

function filterMenuByPermission(items: PermissionAwareItem[], hasPermission: (resource: string, action: string) => boolean): PermissionAwareItem[] {
  return items
    .map(item => {
      // Parent group: visibility determined by visible children, not parent's own coarse permission
      if (item.children) {
        const filtered = filterMenuByPermission(item.children, hasPermission)
        if (filtered.length > 0) return { ...item, children: filtered }
        return null
      }
      // Leaf item: check own permission (fallback to parent resource handled inside hasPermission)
      if (!item.permission || hasPermission(item.permission, 'read')) return item
      return null
    })
    .filter(Boolean) as PermissionAwareItem[]
}

// Strip custom `permission` field to produce clean Ant Design MenuProps items
function toAntdItems(items: PermissionAwareItem[]): any[] {
  return items.map(({ permission: _perm, children, ...rest }) => ({
    ...rest,
    ...(children ? { children: toAntdItems(children) } : {}),
  }))
}

// Map path → display label
const breadcrumbMap: Record<string, string> = {
  '/dashboard': '供应链驾驶舱',
  '/orders': '订单总控台',
  '/run-orders': '跑单管理',
  '/order-risk-pool': '订单风险池',
  '/purchase-plan': '采购到料计划',
  '/material-issues': '问题物料池',
  '/long-lead-materials': '长交期物料池',
  '/kit-analysis': '齐套分析',
  '/supplier-risk': '供应商风险分析',
  '/supplier-payment': '供应商付款排程',
  '/issues': '异常总池',
  '/issue-log': '问题日志',
  '/change-log': '变更日志',
  '/quality-issues': '品质异常',
  '/closure-tracking': '闭环跟踪',
  '/production-overview': '生产总览',
  '/front-process': '前道管理',
  '/smt': '贴片管理',
  '/lean': '精益管理',
  '/assembly': '组装管理',
  '/packaging': '包装管理',
  '/process-exceptions': '工序异常池',
  '/meetings': '会议与行动项',
  '/npi': '项目总览',
  '/import': '数据集成',
  '/masterdata/customers': '客户主数据',
  '/masterdata/suppliers': '供应商主数据',
  '/masterdata/materials': '物料主数据',
  '/masterdata/skus': 'SKU主数据',
  '/masterdata/products': '产品主数据',
  '/masterdata/warehouses': '仓库主数据',
  '/masterdata/processes': '工序主数据',
  '/masterdata/organizations': '组织主数据',
  '/masterdata/employees': '人员主数据',
  '/risk-rules': '预警规则',
  '/inspection-rules': '点检规则',
  '/node-standards': '节点标准',
  '/responsibility-map': '责任归属',
  '/status-dict': '状态字典',
  '/users': '用户管理',
  '/audit': '审计日志',
  '/sync-config': '同步SQL配置',
  '/masterdata/feedback': '问题反馈',
  '/masterdata/files': '文件管理',
}

// Map path → parent group label (for breadcrumb nesting)
const parentGroupMap: Record<string, string> = {
  '/orders': '订单交付中心',
  '/run-orders': '订单交付中心',
  '/order-risk-pool': '订单交付中心',
  '/purchase-plan': '物料齐套中心',
  '/material-issues': '物料齐套中心',
  '/long-lead-materials': '物料齐套中心',
  '/kit-analysis': '物料齐套中心',
  '/supplier-risk': '物料齐套中心',
  '/supplier-payment': '物料齐套中心',
  '/production-overview': '生产协同中心',
  '/front-process': '生产协同中心',
  '/smt': '生产协同中心',
  '/lean': '生产协同中心',
  '/assembly': '生产协同中心',
  '/packaging': '生产协同中心',
  '/process-exceptions': '生产协同中心',
  '/issues': '异常与质量中心',
  '/issue-log': '异常与质量中心',
  '/change-log': '异常与质量中心',
  '/quality-issues': '异常与质量中心',
  '/closure-tracking': '异常与质量中心',
  '/meetings': '会议与任务中心',
  '/npi': '新品/NPI项目中心',
  '/risk-rules': '规则配置中心',
  '/inspection-rules': '规则配置中心',
  '/node-standards': '规则配置中心',
  '/responsibility-map': '规则配置中心',
  '/status-dict': '规则配置中心',
  '/import': '主数据与集成中心',
  '/masterdata/customers': '主数据管理',
  '/masterdata/suppliers': '主数据管理',
  '/masterdata/materials': '主数据管理',
  '/masterdata/skus': '主数据管理',
  '/masterdata/products': '主数据管理',
  '/masterdata/warehouses': '主数据管理',
  '/masterdata/processes': '主数据管理',
  '/masterdata/organizations': '主数据管理',
  '/masterdata/employees': '主数据管理',
  '/users': '主数据与集成中心',
  '/audit': '主数据与集成中心',
  '/sync-config': '主数据与集成中心',
  '/masterdata/feedback': '主数据与集成中心',
  '/masterdata/files': '主数据与集成中心',
}

// Map path → parent group menu key (for auto-expanding sub-menus)
const pathToGroupKey: Record<string, string> = {
  '/orders': 'order-delivery',
  '/run-orders': 'order-delivery',
  '/order-risk-pool': 'order-delivery',
  '/purchase-plan': 'material-center',
  '/material-issues': 'material-center',
  '/long-lead-materials': 'material-center',
  '/kit-analysis': 'material-center',
  '/supplier-risk': 'material-center',
  '/supplier-payment': 'material-center',
  '/production-overview': 'production-center',
  '/front-process': 'production-center',
  '/smt': 'production-center',
  '/lean': 'production-center',
  '/assembly': 'production-center',
  '/packaging': 'production-center',
  '/process-exceptions': 'production-center',
  '/issues': 'exception-center',
  '/issue-log': 'exception-center',
  '/change-log': 'exception-center',
  '/quality-issues': 'exception-center',
  '/closure-tracking': 'exception-center',
  '/meetings': 'meeting-center',
  '/npi': 'npi-center',
  '/risk-rules': 'rules-center',
  '/inspection-rules': 'rules-center',
  '/node-standards': 'rules-center',
  '/responsibility-map': 'rules-center',
  '/status-dict': 'rules-center',
  '/import': 'masterdata-center',
  '/masterdata/customers': 'masterdata-management',
  '/masterdata/suppliers': 'masterdata-management',
  '/masterdata/materials': 'masterdata-management',
  '/masterdata/skus': 'masterdata-management',
  '/masterdata/products': 'masterdata-management',
  '/masterdata/warehouses': 'masterdata-management',
  '/masterdata/processes': 'masterdata-management',
  '/masterdata/organizations': 'masterdata-management',
  '/masterdata/employees': 'masterdata-management',
  '/users': 'masterdata-center',
  '/audit': 'masterdata-center',
  '/sync-config': 'masterdata-center',
  '/masterdata/feedback': 'masterdata-center',
  '/masterdata/files': 'masterdata-center',
}

// Path → required permission for route-level access control
const pathToPermission: Record<string, string> = {
  '/dashboard': 'dashboard',
  '/orders': 'orders.list',
  '/run-orders': 'orders.run_orders',
  '/domestic-orders': 'orders.list',
  '/domestic-shipment': 'orders.list',
  '/order-risk-pool': 'orders.risk_pool',
  '/purchase-plan': 'materials.purchase_plan',
  '/material-issues': 'materials.issues',
  '/long-lead-materials': 'materials.long_lead',
  '/kit-analysis': 'materials.kit_analysis',
  '/supplier-risk': 'materials.supplier_risk',
  '/supplier-payment': 'materials.supplier_payment',
  '/issues': 'exceptions.pool',
  '/issue-log': 'exceptions.issue_log',
  '/change-log': 'exceptions.change_log',
  '/quality-issues': 'exceptions.quality',
  '/closure-tracking': 'exceptions.closure',
  '/production-overview': 'production.overview',
  '/front-process': 'production.front_process',
  '/smt': 'production.smt',
  '/lean': 'production.lean',
  '/assembly': 'production.assembly',
  '/packaging': 'production.packaging',
  '/process-exceptions': 'production.exceptions',
  '/meetings': 'meetings',
  '/npi': 'npi',
  '/import': 'masterdata.import',
  '/risk-rules': 'rules.risk_rules',
  '/inspection-rules': 'rules.inspection',
  '/node-standards': 'rules.node_standards',
  '/responsibility-map': 'rules.responsibility',
  '/status-dict': 'rules.status_dict',
  '/users': 'users',
  '/audit': 'audit',
  '/sync-config': 'settings',
  '/masterdata/customers': 'masterdata.data',
  '/masterdata/suppliers': 'masterdata.data',
  '/masterdata/materials': 'masterdata.data',
  '/masterdata/skus': 'masterdata.data',
  '/masterdata/products': 'masterdata.data',
  '/masterdata/warehouses': 'masterdata.data',
  '/masterdata/processes': 'masterdata.data',
  '/masterdata/organizations': 'masterdata.data',
  '/masterdata/employees': 'masterdata.data',
  '/masterdata/feedback': 'masterdata.feedback',
  '/masterdata/files': 'masterdata.files',
}

function getRequiredPermission(pathname: string): string | undefined {
  if (pathToPermission[pathname]) return pathToPermission[pathname]
  // 订单详情页 /orders/:orderNo/lines/:lineNo
  if (pathname.startsWith('/orders/')) return 'orders.list'
  return undefined
}

export default function MainLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const logout = useAuthStore((s: any) => s.logout)
  const user = useAuthStore((s: any) => s.user)
  const token = useAuthStore((s: any) => s.token)
  const setAuth = useAuthStore((s: any) => s.setAuth)
  const hasPermission = useAuthStore((s: any) => s.hasPermission)
  const [pwdModalOpen, setPwdModalOpen] = useState(false)
  const [pwdForm] = Form.useForm()

  // Refresh permissions on mount in case role was modified while user was logged in
  useEffect(() => {
    if (!token) return
    authApi.getMe()
      .then((res: any) => setAuth(token, res.data))
      .catch(() => { /* getMe failure handled by axios interceptor (401 → logout) */ })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleChangePassword = async () => {
    try {
      const values = await pwdForm.validateFields()
      await authApi.changePassword(values.old_password, values.new_password)
      message.success('密码修改成功')
      setPwdModalOpen(false)
      pwdForm.resetFields()
    } catch (e: any) {
      if (e?.response?.data?.detail) message.error(e.response.data.detail)
    }
  }

  // Permission-aware menu items — depend on user so menu re-renders when permissions refresh
  const menuItems = useMemo(() => toAntdItems(filterMenuByPermission(allMenuItems, hasPermission)), [hasPermission, user])

  // Auto-open parent sub-menu for the current path
  const openKeys = useMemo(() => {
    const gk = pathToGroupKey[location.pathname]
    return gk ? [gk] : []
  }, [location.pathname])

  const breadcrumbItems = useMemo(() => {
    const items: { title: React.ReactNode }[] = [
      { title: <Link to="/dashboard"><HomeOutlined /> <span style={{ marginLeft: 4 }}>首页</span></Link> },
    ]
    const path = location.pathname
    if (path !== '/dashboard') {
      // Insert parent group breadcrumb if applicable
      const parentLabel = parentGroupMap[path]
      if (parentLabel) {
        items.push({ title: parentLabel })
      }
      const label = breadcrumbMap[path]
      if (label) {
        items.push({ title: label })
      } else if (path.startsWith('/orders/')) {
        items.push({ title: <Link to="/orders">订单交付中心</Link> })
        items.push({ title: '订单详情' })
      }
    }
    return items
  }, [location.pathname])

  return (
    <Layout className="min-h-screen" style={{ background: '#f0f4f8' }}>
      {/* ===== 左侧菜单 ===== */}
      <Sider
        trigger={null}
        collapsible
        collapsed={collapsed}
        width={256}
        className="sidebar-modern"
        style={{
          overflowY: 'auto',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
          zIndex: 10,
        }}
      >
        {/* Logo Section */}
        <div 
          className="flex items-center gap-3 px-6" 
          style={{ 
            height: 72, 
            paddingTop: 16,
            paddingBottom: 16,
          }}
        >
          <div 
            style={{ 
              width: 40, 
              height: 40, 
              borderRadius: 12, 
              background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%)',
              display: 'flex', 
              alignItems: 'center', 
              justifyContent: 'center', 
              flexShrink: 0,
              boxShadow: '0 2px 8px rgba(99, 102, 241, 0.3)'
            }}
          >
            <span style={{ color: '#fff', fontWeight: 700, fontSize: 16, letterSpacing: 1 }}>S</span>
          </div>
          {!collapsed && (
            <div className="flex flex-col">
              <span 
                className="font-bold" 
                style={{ 
                  color: '#fff',
                  fontSize: 18, 
                  letterSpacing: 0.5,
                }}
              >
                SPC 中台
              </span>
              <span 
                style={{ 
                  color: '#94a3b8', 
                  fontSize: 11, 
                  fontWeight: 400,
                  letterSpacing: 1,
                  textTransform: 'uppercase'
                }}
              >
                供应链协同
              </span>
            </div>
          )}
        </div>

        {/* Menu */}
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          defaultOpenKeys={openKeys}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>

      <Layout style={{ marginLeft: collapsed ? 80 : 256, transition: 'margin-left .2s', minHeight: '100vh' }}>
        {/* ===== 顶部导航 ===== */}
        <div className="header-bar" style={{ position: 'sticky', top: 0, zIndex: 9 }}>
          <Space size="middle">
            <Button
              type="text"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed(!collapsed)}
              style={{ fontSize: 16, width: 36, height: 36, borderRadius: 10 }}
            />
          </Space>
          <Space size="middle">
            <FeedbackButton />
            <Button type="text" icon={<BellOutlined />} style={{ fontSize: 16, width: 36, height: 36, borderRadius: 10, color: '#64748b' }} />
            <Dropdown
              menu={{
                items: [
                  { key: 'change-pwd', icon: <KeyOutlined />, label: '修改密码' },
                  { type: 'divider' as const },
                  { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', danger: true },
                ],
                onClick: ({ key }) => {
                  if (key === 'logout') { logout(); navigate('/login') }
                  if (key === 'change-pwd') { pwdForm.resetFields(); setPwdModalOpen(true) }
                },
              }}
            >
              <Space className="cursor-pointer" style={{ padding: '4px 12px', borderRadius: 10 }}>
                <div style={{ width: 30, height: 30, borderRadius: 8, background: 'linear-gradient(135deg, #6366f1, #818cf8)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <UserOutlined style={{ color: '#fff', fontSize: 13 }} />
                </div>
                <span style={{ color: '#334155', fontSize: 13, fontWeight: 500 }}>
                  {user?.display_name || user?.username || '用户'}
                </span>
              </Space>
            </Dropdown>
          </Space>
        </div>

        {/* ===== 面包屑 ===== */}
        <div style={{ padding: '14px 24px 0' }}>
          <Breadcrumb items={breadcrumbItems} style={{ fontSize: 13 }} />
        </div>

        {/* ===== 修改密码弹窗 ===== */}
        <Modal
          title="修改密码"
          open={pwdModalOpen}
          onOk={handleChangePassword}
          onCancel={() => setPwdModalOpen(false)}
          width={420}
          okText="确认修改"
        >
          <Form form={pwdForm} layout="vertical" style={{ marginTop: 16 }}>
            <Form.Item name="old_password" label="原密码" rules={[{ required: true, message: '请输入原密码' }]}>
              <Input.Password placeholder="输入当前密码" />
            </Form.Item>
            <Form.Item name="new_password" label="新密码" rules={[{ required: true, message: '请输入新密码' }, { min: 6, message: '密码至少6位' }]}>
              <Input.Password placeholder="至少6位" />
            </Form.Item>
            <Form.Item
              name="confirm_password"
              label="确认新密码"
              dependencies={['new_password']}
              rules={[
                { required: true, message: '请确认新密码' },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    if (!value || getFieldValue('new_password') === value) return Promise.resolve()
                    return Promise.reject(new Error('两次密码不一致'))
                  },
                }),
              ]}
            >
              <Input.Password placeholder="再次输入新密码" />
            </Form.Item>
          </Form>
        </Modal>

        {/* ===== 页面内容 ===== */}
        <Content style={{ padding: '16px 24px 24px' }}>
          {(() => {
            const requiredPerm = getRequiredPermission(location.pathname)
            const hasAccess = !requiredPerm || hasPermission(requiredPerm, 'read')
            if (hasAccess) return <Outlet />
            return (
              <Result
                status="403"
                title="403"
                subTitle="抱歉，您没有访问该页面的权限。"
                extra={<Button type="primary" onClick={() => navigate('/dashboard')}>返回首页</Button>}
              />
            )
          })()}
        </Content>
      </Layout>
      <FloatingAssistant />
    </Layout>
  )
}
