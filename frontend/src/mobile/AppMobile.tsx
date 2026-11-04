import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuthStore } from '@/store/auth'
import MobileLoginPage from './pages/MobileLoginPage'
import WorkbenchPage from './pages/WorkbenchPage'
import MePage from './pages/MePage'
import NotificationsPage from './pages/NotificationsPage'
import ApprovalDetailPage from './pages/ApprovalDetailPage'
import StockCheckListPage from './pages/stock/StockCheckListPage'
import StockCheckCreatePage from './pages/stock/StockCheckCreatePage'
import StockCheckDetailPage from './pages/stock/StockCheckDetailPage'
import StockCheckEntryPage from './pages/stock/StockCheckEntryPage'
import StockCheckManagePage from './pages/stock/StockCheckManagePage'
import ScanCountPage from './pages/stock/ScanCountPage'

function AuthGuard() {
  const token = useAuthStore((s) => s.currentToken)
  const location = useLocation()
  if (!token) {
    // 保留查询参数（如企微 OAuth 的 ?code=），否则回跳 /m/ 时 code 丢失造成免登死循环
    return <Navigate to={`/login${location.search}`} replace state={{ from: location.pathname }} />
  }
  return <Outlet />
}

export default function AppMobile() {
  return (
    <BrowserRouter basename="/m">
      <Routes>
        <Route path="/login" element={<MobileLoginPage />} />
        <Route element={<AuthGuard />}>
          <Route path="/" element={<WorkbenchPage />} />
          <Route path="/me" element={<MePage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/approvals/items/:bizType/:id" element={<ApprovalDetailPage />} />
          <Route path="/stock-check" element={<StockCheckListPage />} />
          <Route path="/stock-check/new" element={<StockCheckCreatePage />} />
          <Route path="/stock-check/:checkId" element={<StockCheckDetailPage />} />
          <Route path="/stock-check/:checkId/items/:itemId" element={<StockCheckEntryPage />} />
          <Route path="/stock-check/:checkId/manage" element={<StockCheckManagePage />} />
          <Route path="/scan-count" element={<ScanCountPage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
