import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { TabBar } from 'antd-mobile'
import { AppOutline, SetOutline, UserOutline } from 'antd-mobile-icons'
import { useAuthStore } from '@/store/auth'
import MobileLoginPage from './pages/MobileLoginPage'
import WorkbenchPage from './pages/WorkbenchPage'
import AppsPage from './pages/AppsPage'
import MePage from './pages/MePage'
import StockCheckListPage from './pages/stock/StockCheckListPage'
import StockCheckCreatePage from './pages/stock/StockCheckCreatePage'
import StockCheckDetailPage from './pages/stock/StockCheckDetailPage'
import StockCheckEntryPage from './pages/stock/StockCheckEntryPage'
import StockCheckManagePage from './pages/stock/StockCheckManagePage'

function AuthGuard() {
  const token = useAuthStore((s) => s.currentToken)
  const location = useLocation()
  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <Outlet />
}

const TABS = [
  { key: '/', title: '工作台', icon: <AppOutline /> },
  { key: '/apps', title: '应用', icon: <SetOutline /> },
  { key: '/me', title: '我的', icon: <UserOutline /> },
]

function TabLayout() {
  const location = useLocation()
  const navigate = useNavigate()
  const activeKey = '/' + (location.pathname.split('/')[1] || '')
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <div style={{ flex: 1, overflowY: 'auto' }}>
        <Outlet />
      </div>
      <div style={{ borderTop: '1px solid #eee', background: '#fff', paddingBottom: 'env(safe-area-inset-bottom)' }}>
        <TabBar activeKey={activeKey} onChange={(k) => navigate(k)}>
          {TABS.map((t) => (
            <TabBar.Item key={t.key} icon={t.icon} title={t.title} />
          ))}
        </TabBar>
      </div>
    </div>
  )
}

export default function AppMobile() {
  return (
    <BrowserRouter basename="/m">
      <Routes>
        <Route path="/login" element={<MobileLoginPage />} />
        <Route element={<AuthGuard />}>
          <Route element={<TabLayout />}>
            <Route path="/" element={<WorkbenchPage />} />
            <Route path="/apps" element={<AppsPage />} />
            <Route path="/me" element={<MePage />} />
          </Route>
          <Route path="/stock-check" element={<StockCheckListPage />} />
          <Route path="/stock-check/new" element={<StockCheckCreatePage />} />
          <Route path="/stock-check/:checkId" element={<StockCheckDetailPage />} />
          <Route path="/stock-check/:checkId/items/:itemId" element={<StockCheckEntryPage />} />
          <Route path="/stock-check/:checkId/manage" element={<StockCheckManagePage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
