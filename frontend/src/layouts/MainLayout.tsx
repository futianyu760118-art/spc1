import { useState, useMemo, useEffect, useCallback, useRef } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, Button, Dropdown, Space, Modal, Form, Input, message, Result, Badge, Popover, Tabs, List, Tag, Typography, notification as antNotification } from 'antd'
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
  NotificationOutlined,
  CheckOutlined,
  SoundOutlined,
  IdcardOutlined,
} from '@ant-design/icons'
import { useAuthStore } from '../store/auth'
import { authApi, notificationApi } from '../services/api'
import FeedbackButton from '../pages/BasicDataCenter/FeedbackManagement/FeedbackButton'
import ShareButton from '../components/ShareButton'
import { FloatingAssistant, TopBarAssistant } from '../components/Assistant'
import FontSizeSetting from '../components/FontSizeSetting'
import { SUPPLIER_PORTAL_PATHS } from '../constants/permissions'

const { Sider, Content } = Layout

type PermissionAwareItem = {
  key: string
  icon?: React.ReactNode
  label: string
  permission?: string
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
      { key: '/schedule-plans', icon: <ProjectOutlined />, label: '计划排产', permission: 'production.schedule_plans' },
      { key: '/product-process-capacities', icon: <DatabaseOutlined />, label: '产品工序产能', permission: 'production.product_process_capacities' },
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
      { key: '/product-samples', icon: <FileTextOutlined />, label: '产品封样', permission: 'exceptions.product_samples' },
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
      { key: '/order-standards', icon: <FileTextOutlined />, label: '订单标准', permission: 'rules.order_standards' },
      { key: '/work-instructions', icon: <AuditOutlined />, label: '作业指导书', permission: 'rules.work_instructions' },
      { key: '/responsibility-map', icon: <TeamOutlined />, label: '责任归属', permission: 'rules.responsibility' },
      { key: '/status-dict', icon: <AppstoreOutlined />, label: '状态字典', permission: 'rules.status_dict' },
    ],
  },
  {
    key: 'basicdata-center',
    icon: <DatabaseOutlined />,
    label: '基础数据与集成中心',
    children: [
      { key: '/import', icon: <ImportOutlined />, label: '数据集成', permission: 'basicdata.import' },
      {
        key: 'basicdata-management',
        icon: <DatabaseOutlined />,
        label: '基础数据管理',
        permission: 'basicdata.data',
        children: [
          { key: '/basicdata/customers', icon: <UserOutlined />, label: '客户', permission: 'basicdata.data' },
          { key: '/basicdata/suppliers', icon: <ShoppingCartOutlined />, label: '供应商', permission: 'basicdata.data' },
          { key: '/basicdata/materials', icon: <AppstoreOutlined />, label: '物料', permission: 'basicdata.data' },
          { key: '/basicdata/skus', icon: <ContainerOutlined />, label: 'SKU', permission: 'basicdata.data' },
          { key: '/basicdata/products', icon: <FileTextOutlined />, label: '产品', permission: 'basicdata.data' },
          { key: '/basicdata/warehouses', icon: <ContainerOutlined />, label: '仓库', permission: 'basicdata.data' },
          { key: '/basicdata/processes', icon: <RocketOutlined />, label: '工序', permission: 'basicdata.data' },
          { key: '/basicdata/organizations', icon: <TeamOutlined />, label: '组织', permission: 'basicdata.data' },
          { key: '/basicdata/positions', icon: <IdcardOutlined />, label: '岗位', permission: 'basicdata.data' },
          { key: '/basicdata/employees', icon: <UserOutlined />, label: '人员', permission: 'basicdata.data' },
        ],
      },
      { key: '/users', icon: <UserOutlined />, label: '用户管理', permission: 'users' },
      { key: '/audit', icon: <AuditOutlined />, label: '审计日志', permission: 'audit' },
      { key: '/sync-config', icon: <SwapOutlined />, label: '同步SQL配置', permission: 'settings' },
      { key: '/basicdata/feedback', icon: <MessageOutlined />, label: '问题反馈', permission: 'basicdata.feedback' },
      { key: '/basicdata/files', icon: <FolderOpenOutlined />, label: '文件管理', permission: 'basicdata.files' },
      { key: '/announcements', icon: <NotificationOutlined />, label: '公告管理', permission: 'announcements' },
    ],
  },
]

function filterMenuByPermission(items: PermissionAwareItem[], hasPermission: (resource: string, action: string) => boolean): PermissionAwareItem[] {
  return items
    .map(item => {
      if (item.children) {
        const filtered = filterMenuByPermission(item.children, hasPermission)
        if (filtered.length > 0) return { ...item, children: filtered }
        return null
      }
      if (!item.permission || hasPermission(item.permission, 'read')) return item
      return null
    })
    .filter(Boolean) as PermissionAwareItem[]
}

function filterMenuByPath(items: PermissionAwareItem[], targetPath: string, hasPermission: (resource: string, action: string) => boolean): PermissionAwareItem[] {
  return items
    .map(item => {
      if (item.children) {
        const filtered = filterMenuByPath(item.children, targetPath, hasPermission)
        if (filtered.length > 0) return { ...item, children: filtered }
        return null
      }
      if (item.key === targetPath && (!item.permission || hasPermission(item.permission, 'read'))) return item
      return null
    })
    .filter(Boolean) as PermissionAwareItem[]
}

const supplierPortalPaths = new Set<string>(SUPPLIER_PORTAL_PATHS)

function filterSupplierPortalMenu(items: PermissionAwareItem[], hasPermission: (resource: string, action: string) => boolean): PermissionAwareItem[] {
  return items
    .map(item => {
      if (item.children) {
        const filtered = filterSupplierPortalMenu(item.children, hasPermission)
        if (filtered.length > 0) return { ...item, children: filtered }
        return null
      }
      if (supplierPortalPaths.has(item.key) && (!item.permission || hasPermission(item.permission, 'read'))) return item
      return null
    })
    .filter(Boolean) as PermissionAwareItem[]
}

function toAntdItems(items: PermissionAwareItem[]): any[] {
  return items.map(({ permission: _perm, children, ...rest }) => ({
    ...rest,
    ...(children ? { children: toAntdItems(children) } : {}),
  }))
}

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
  '/schedule-plans': 'production-center',
  '/product-process-capacities': 'production-center',
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
  '/product-samples': 'exception-center',
  '/closure-tracking': 'exception-center',
  '/meetings': 'meeting-center',
  '/npi': 'npi-center',
  '/risk-rules': 'rules-center',
  '/inspection-rules': 'rules-center',
  '/node-standards': 'rules-center',
  '/order-standards': 'rules-center',
  '/work-instructions': 'rules-center',
  '/responsibility-map': 'rules-center',
  '/status-dict': 'rules-center',
  '/import': 'basicdata-center',
  '/basicdata/customers': 'basicdata-management',
  '/basicdata/suppliers': 'basicdata-management',
  '/basicdata/materials': 'basicdata-management',
  '/basicdata/skus': 'basicdata-management',
  '/basicdata/products': 'basicdata-management',
  '/basicdata/warehouses': 'basicdata-management',
  '/basicdata/processes': 'basicdata-management',
  '/basicdata/organizations': 'basicdata-management',
  '/basicdata/positions': 'basicdata-management',
  '/basicdata/employees': 'basicdata-management',
  '/users': 'basicdata-center',
  '/audit': 'basicdata-center',
  '/sync-config': 'basicdata-center',
  '/basicdata/feedback': 'basicdata-center',
  '/basicdata/files': 'basicdata-center',
  '/announcements': 'basicdata-center',
}

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
  '/product-samples': 'exceptions.product_samples',
  '/closure-tracking': 'exceptions.closure',
  '/production-overview': 'production.overview',
  '/schedule-plans': 'production.schedule_plans',
  '/product-process-capacities': 'production.product_process_capacities',
  '/front-process': 'production.front_process',
  '/smt': 'production.smt',
  '/lean': 'production.lean',
  '/assembly': 'production.assembly',
  '/packaging': 'production.packaging',
  '/process-exceptions': 'production.exceptions',
  '/meetings': 'meetings',
  '/npi': 'npi',
  '/import': 'basicdata.import',
  '/risk-rules': 'rules.risk_rules',
  '/inspection-rules': 'rules.inspection',
  '/node-standards': 'rules.node_standards',
  '/order-standards': 'rules.order_standards',
  '/work-instructions': 'rules.work_instructions',
  '/responsibility-map': 'rules.responsibility',
  '/status-dict': 'rules.status_dict',
  '/users': 'users',
  '/audit': 'audit',
  '/sync-config': 'settings',
  '/basicdata/customers': 'basicdata.data',
  '/basicdata/suppliers': 'basicdata.data',
  '/basicdata/materials': 'basicdata.data',
  '/basicdata/skus': 'basicdata.data',
  '/basicdata/products': 'basicdata.data',
  '/basicdata/warehouses': 'basicdata.data',
  '/basicdata/processes': 'basicdata.data',
  '/basicdata/organizations': 'basicdata.data',
  '/basicdata/positions': 'basicdata.data',
  '/basicdata/employees': 'basicdata.data',
  '/basicdata/feedback': 'basicdata.feedback',
  '/basicdata/files': 'basicdata.files',
  '/announcements': 'announcements',
}

function getRequiredPermission(pathname: string): string | undefined {
  if (pathToPermission[pathname]) return pathToPermission[pathname]
  if (pathname.startsWith('/orders/')) return 'orders.list'
  return undefined
}

export default function MainLayout() {
  const { currentUser, logout, hasPermission, isSupplierUser, isShareUser, getShareTargetPath, exitShare, originalToken, setAuth } = useAuthStore()
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const [bellOpen, setBellOpen] = useState(false)
  const [notifTab, setNotifTab] = useState('announcement_system')
  const [notifList, setNotifList] = useState<any[]>([])
  const [notifLoading, setNotifLoading] = useState(false)
  const [unreadTotal, setUnreadTotal] = useState(0)
  const [unreadByType, setUnreadByType] = useState<Record<string, number>>({})
  const [pwdModalOpen, setPwdModalOpen] = useState(false)
  const [pwdForm] = Form.useForm()
  const toastShown = useRef(false)
  const canUseTopbar = useMemo(() => ({
    share: hasPermission('topbar.share', 'read'),
    feedback: hasPermission('topbar.feedback', 'read'),
    aiSearch: hasPermission('topbar.ai_search', 'read'),
    fontSize: hasPermission('topbar.font_size', 'read'),
    notifications: hasPermission('topbar.notifications', 'read'),
  }), [hasPermission, currentUser])

  const fetchUnreadCount = useCallback(async () => {
    if (!originalToken || isShareUser() || !canUseTopbar.notifications) return
    try {
      const res: any = await notificationApi.unreadCount()
      setUnreadTotal(res.data?.total || 0)
      setUnreadByType(res.data?.by_type || {})
    } catch { /* silent */ }
  }, [originalToken, isShareUser, canUseTopbar.notifications])

  const fetchNotifList = useCallback(async (tab?: string) => {
    if (!originalToken || isShareUser() || !canUseTopbar.notifications) return
    setNotifLoading(true)
    try {
      const activeTab = tab || notifTab
      const params: Record<string, any> = { page_size: 30 }
      if (activeTab === 'announcement_system') {
        const [annRes, sysRes] = await Promise.all([
          notificationApi.list({ ...params, type: 'announcement' }),
          notificationApi.list({ ...params, type: 'system' })
        ])
        const items = [...(annRes.data?.items || []), ...(sysRes.data?.items || [])]
        items.sort((a: any, b: any) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
        setNotifList(items)
      } else if (activeTab === 'alert') {
        const res: any = await notificationApi.list(params)
        const items = (res.data?.items || []).filter((n: any) => n.type !== 'announcement' && n.type !== 'system')
        setNotifList(items)
      }
    } catch { /* silent */ }
    setNotifLoading(false)
  }, [originalToken, isShareUser, notifTab, canUseTopbar.notifications])

  useEffect(() => {
    if (!originalToken || isShareUser()) return
    authApi.getMe()
      .then((res: any) => {
        if (res.data) {
          setAuth(originalToken, res.data)
        }
      })
      .catch(() => {})
  }, [originalToken, isShareUser, setAuth])

  useEffect(() => {
    if (!originalToken || isShareUser() || !canUseTopbar.notifications) return
    fetchUnreadCount()
    const timer = setInterval(fetchUnreadCount, 60000)
    return () => clearInterval(timer)
  }, [originalToken, isShareUser, canUseTopbar.notifications, fetchUnreadCount])

  useEffect(() => {
    if (!originalToken || isShareUser() || !canUseTopbar.notifications || toastShown.current) return
    if (sessionStorage.getItem('notif_toast_shown')) { toastShown.current = true; return }
    const showToast = async () => {
      try {
        const res: any = await notificationApi.list({ is_read: false, page_size: 5 })
        const items = (res.data?.items || []).filter((n: any) => n.priority === 'important' || n.priority === 'urgent')
        if (items.length > 0) {
          antNotification.info({
            message: '您有新的公告',
            description: items.map((n: any) => n.title).join('、'),
            placement: 'topRight',
            duration: 8,
            onClick: () => { setBellOpen(true) },
          })
        }
      } catch { /* silent */ }
      toastShown.current = true
      sessionStorage.setItem('notif_toast_shown', '1')
    }
    const t = setTimeout(showToast, 2000)
    return () => clearTimeout(t)
  }, [originalToken, isShareUser, canUseTopbar.notifications])

  useEffect(() => {
    if (bellOpen) fetchNotifList(notifTab)
  }, [bellOpen, notifTab, fetchNotifList])

  const handleMarkRead = async (id: number) => {
    await notificationApi.markRead(id)
    setNotifList(prev => prev.map(n => n.id === id ? { ...n, is_read: true } : n))
    fetchUnreadCount()
  }

  const handleMarkAllRead = async () => {
    if (notifTab === 'announcement_system') {
      await Promise.all([
        notificationApi.markAllRead('announcement'),
        notificationApi.markAllRead('system')
      ])
    } else {
      await notificationApi.markAllRead(notifTab)
    }
    setNotifList(prev => prev.map(n => ({ ...n, is_read: true })))
    fetchUnreadCount()
  }

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

  const menuItems = useMemo(() => {
    if (isShareUser()) {
      const targetPath = getShareTargetPath()
      if (targetPath) {
        return toAntdItems(filterMenuByPath(allMenuItems, targetPath, hasPermission))
      }
      return []
    }
    if (isSupplierUser()) {
      return toAntdItems(filterSupplierPortalMenu(allMenuItems, hasPermission))
    }
    return toAntdItems(filterMenuByPermission(allMenuItems, hasPermission))
  }, [hasPermission, currentUser, isSupplierUser, isShareUser, getShareTargetPath])

  const requiredPermission = getRequiredPermission(location.pathname)
  const canViewCurrentPage = !requiredPermission || hasPermission(requiredPermission, 'read')
  const openKeys = useMemo(() => {
    const gk = pathToGroupKey[location.pathname]
    return gk ? [gk] : []
  }, [location.pathname])

  return (
    <Layout className="min-h-screen" style={{ background: '#f0f4f8' }}>
      {!isShareUser() && (
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
          <div className="flex items-center gap-3 px-6" style={{ height: 72, paddingTop: 16, paddingBottom: 16 }}>
            <div style={{ width: 40, height: 40, borderRadius: 12, background: 'linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #a855f7 100%)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, boxShadow: '0 2px 8px rgba(99, 102, 241, 0.3)' }}>
              <span style={{ color: '#fff', fontWeight: 700, fontSize: 'calc(1rem * var(--font-size-scale))', letterSpacing: 1 }}>S</span>
            </div>
            {!collapsed && (
              <div className="flex flex-col">
                <span className="font-bold" style={{ color: '#fff', fontSize: 'calc(1.125rem * var(--font-size-scale))', letterSpacing: 0.5 }}>
                  SPC 中台
                </span>
                <span style={{ color: '#94a3b8', fontSize: 'calc(0.6875rem * var(--font-size-scale))', fontWeight: 400, letterSpacing: 1, textTransform: 'uppercase' }}>
                  供应链协同
                </span>
              </div>
            )}
          </div>

          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[location.pathname]}
            defaultOpenKeys={openKeys}
            items={menuItems}
            onClick={({ key }) => navigate(key)}
          />
        </Sider>
      )}

      <Layout style={{ marginLeft: !isShareUser() && collapsed ? 80 : (!isShareUser() ? 256 : 0), transition: 'margin-left .2s', minHeight: '100vh' }}>
        <div className="header-bar" style={{ position: 'sticky', top: 0, zIndex: 9 }}>
          {!isShareUser() && (
            <Space size="middle">
              <Button
                type="text"
                icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
                onClick={() => setCollapsed(!collapsed)}
                style={{ fontSize: 'calc(0.875rem * var(--font-size-scale))', width: 36, height: 36, borderRadius: 10 }}
              />
            </Space>
          )}
          <Space size="middle">
            {!isShareUser() && !isSupplierUser() && canUseTopbar.share && <ShareButton />}
            {!isSupplierUser() && canUseTopbar.feedback && <FeedbackButton />}
            {!isSupplierUser() && canUseTopbar.aiSearch && <TopBarAssistant />}
            {canUseTopbar.fontSize && <FontSizeSetting />}
            {canUseTopbar.notifications && (
              <Popover
                open={bellOpen}
                onOpenChange={setBellOpen}
                trigger="click"
                placement="bottomRight"
                overlayStyle={{ width: 380 }}
                content={
                  <div style={{ margin: '-12px -16px' }}>
                    <Tabs
                      activeKey={notifTab}
                      onChange={setNotifTab}
                      centered
                      size="small"
                      style={{ marginBottom: 0 }}
                      items={[
                        {
                          key: 'announcement_system',
                          label: <span style={{ fontSize: 'calc(0.875rem * var(--font-size-scale))' }}><SoundOutlined /> 公告系统 {(unreadByType['announcement'] || 0) + (unreadByType['system'] || 0) > 0 ? <Badge count={(unreadByType['announcement'] || 0) + (unreadByType['system'] || 0)} size="small" offset={[4, -2]} /> : null}</span>,
                        },
                        {
                          key: 'alert',
                          label: <span style={{ fontSize: 'calc(0.875rem * var(--font-size-scale))' }}><WarningOutlined /> 提醒 {(unreadByType['material_alert'] || 0) + (unreadByType['exception_alert'] || 0) > 0 ? <Badge count={(unreadByType['material_alert'] || 0) + (unreadByType['exception_alert'] || 0)} size="small" offset={[4, -2]} /> : null}</span>,
                        },
                      ]}
                    />
                    <List
                      loading={notifLoading}
                      dataSource={notifList}
                      locale={{ emptyText: '暂无消息' }}
                      style={{ maxHeight: 360, overflowY: 'auto', padding: '0 12px' }}
                      renderItem={(item: any) => (
                        <List.Item
                          key={item.id}
                          style={{ cursor: 'pointer', padding: '10px 4px', opacity: item.is_read ? 0.55 : 1 }}
                          onClick={() => { if (!item.is_read) handleMarkRead(item.id) }}
                        >
                          <List.Item.Meta
                            title={
                              <Space size={4}>
                                {!item.is_read && <Badge status="processing" />}
                                <Typography.Text style={{ fontSize: 'calc(0.875rem * var(--font-size-scale))' }} strong={!item.is_read}>{item.title}</Typography.Text>
                                {item.priority === 'urgent' && <Tag color="red" style={{ fontSize: 'calc(0.875rem * var(--font-size-scale))', lineHeight: '18px' }}>紧急</Tag>}
                                {item.priority === 'important' && <Tag color="gold" style={{ fontSize: 'calc(0.875rem * var(--font-size-scale))', lineHeight: '18px' }}>重要</Tag>}
                              </Space>
                            }
                            description={<Typography.Text type="secondary" style={{ fontSize: 'calc(0.875rem * var(--font-size-scale))' }}>{item.created_at}</Typography.Text>}
                          />
                        </List.Item>
                      )}
                    />
                    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 12px', borderTop: '1px solid #f0f0f0' }}>
                      <Button type="link" size="small" icon={<CheckOutlined />} onClick={handleMarkAllRead} style={{ fontSize: 'calc(0.875rem * var(--font-size-scale))' }}>全部已读</Button>
                      <Button type="link" size="small" onClick={() => { setBellOpen(false); navigate('/announcements') }} style={{ fontSize: 'calc(0.875rem * var(--font-size-scale))' }}>查看全部</Button>
                    </div>
                  </div>
                }
              >
                <Badge count={unreadTotal} size="small" offset={[-4, 4]}>
                  <Button type="text" icon={<BellOutlined />} style={{ fontSize: 'calc(0.875rem * var(--font-size-scale))', width: 36, height: 36, borderRadius: 10, color: '#64748b' }} />
                </Badge>
              </Popover>
            )}
            {isShareUser() ? (
              <Button
                type="primary"
                icon={<LogoutOutlined />}
                onClick={() => { exitShare(); navigate('/dashboard') }}
              >
                退出分享
              </Button>
            ) : (
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
                    <UserOutlined style={{ color: '#fff', fontSize: 'calc(0.875rem * var(--font-size-scale))' }} />
                  </div>
                  <span style={{ color: '#334155', fontSize: 'calc(0.875rem * var(--font-size-scale))', fontWeight: 500 }}>
                    {currentUser && 'display_name' in currentUser ? (currentUser.display_name || currentUser.username) : '用户'}
                  </span>
                </Space>
              </Dropdown>
            )}
          </Space>
        </div>

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

        <Content style={{ padding: '12px 24px 24px' }}>
          {canViewCurrentPage ? (
            <Outlet />
          ) : (
            <Result
              status="403"
              title="无访问权限"
              subTitle={`缺少 ${requiredPermission}.read 权限`}
            />
          )}
        </Content>
      </Layout>
    </Layout>
  )
}
