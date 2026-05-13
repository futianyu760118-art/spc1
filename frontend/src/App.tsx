import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import Dashboard from './pages/Dashboard/index'
import OrderList from './pages/OrderDelivery/OrderList/index'
import RunOrderList from './pages/OrderDelivery/RunOrderList/index'
import DomesticOrders from './pages/OrderDelivery/DomesticOrders/index'
import DomesticShipment from './pages/OrderDelivery/DomesticShipment/index'
import OrderRiskPool from './pages/OrderDelivery/OrderRiskPool/index'
import PurchasePlan from './pages/MaterialCenter/PurchasePlan/index'
import MaterialIssues from './pages/MaterialCenter/MaterialIssues/index'
import LongLeadMaterials from './pages/MaterialCenter/LongLeadMaterials/index'
import KitAnalysis from './pages/MaterialCenter/KitAnalysis/index'
import SupplierRisk from './pages/MaterialCenter/SupplierRisk/index'
import SupplierPayment from './pages/MaterialCenter/SupplierPayment/index'
import OrderDetail from './pages/OrderDelivery/OrderDetail/index'
import IssueLedger from './pages/ExceptionCenter/IssueLedger/index'
import ExceptionPool from './pages/ExceptionCenter/ExceptionPool/index'
import IssueLogView from './pages/ExceptionCenter/IssueLogView/index'
import ChangeLogView from './pages/ExceptionCenter/ChangeLogView/index'
import QualityIssues from './pages/ExceptionCenter/QualityIssues/index'
import ClosureTracking from './pages/ExceptionCenter/ClosureTracking/index'
import DataImport from './pages/MasterDataCenter/DataIntegration/index'
import { RiskRules, InspectionRules, NodeStandards, ResponsibilityMap, StatusDictionary } from './pages/RulesCenter'
import { UserManagement, AuditLog, SyncSqlConfig, FeedbackManagement, FileManagement } from './pages/MasterDataCenter'
import Customers from './pages/MasterDataCenter/Customers'
import Suppliers from './pages/MasterDataCenter/Suppliers'
import Materials from './pages/MasterDataCenter/Materials'
import SKUs from './pages/MasterDataCenter/SKUs'
import Products from './pages/MasterDataCenter/Products'
import Warehouses from './pages/MasterDataCenter/Warehouses'
import Processes from './pages/MasterDataCenter/Processes'
import Organizations from './pages/MasterDataCenter/Organizations'
import Employees from './pages/MasterDataCenter/Employees'
import ProductionOverview from './pages/ProductionCenter/ProductionOverview/index'
import FrontProcess from './pages/ProductionCenter/FrontProcess/index'
import SMT from './pages/ProductionCenter/SMT/index'
import Lean from './pages/ProductionCenter/Lean/index'
import Assembly from './pages/ProductionCenter/Assembly/index'
import Packaging from './pages/ProductionCenter/Packaging/index'
import ProcessExceptions from './pages/ProductionCenter/ProcessExceptions/index'
import MeetingCenter from './pages/MeetingCenter/index'
import NPICenter from './pages/NPICenter/index'
import Login from './pages/Login'
import { useAuthStore } from './store/auth'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/"
          element={
            <PrivateRoute>
              <MainLayout />
            </PrivateRoute>
          }
        >
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="orders" element={<OrderList />} />
          <Route path="run-orders" element={<RunOrderList />} />
          <Route path="domestic-orders" element={<DomesticOrders />} />
          <Route path="domestic-shipment" element={<DomesticShipment />} />
          <Route path="order-risk-pool" element={<OrderRiskPool />} />
          <Route path="purchase-plan" element={<PurchasePlan />} />
          <Route path="material-issues" element={<MaterialIssues />} />
          <Route path="long-lead-materials" element={<LongLeadMaterials />} />
          <Route path="kit-analysis" element={<KitAnalysis />} />
          <Route path="supplier-risk" element={<SupplierRisk />} />
          <Route path="supplier-payment" element={<SupplierPayment />} />
          <Route path="orders/:orderNo/lines/:lineNo" element={<OrderDetail />} />
          <Route path="issues" element={<ExceptionPool />} />
          <Route path="issue-log" element={<IssueLogView />} />
          <Route path="change-log" element={<ChangeLogView />} />
          <Route path="quality-issues" element={<QualityIssues />} />
          <Route path="closure-tracking" element={<ClosureTracking />} />
          <Route path="production" element={<Navigate to="/production-overview" replace />} />
          <Route path="production-overview" element={<ProductionOverview />} />
          <Route path="front-process" element={<FrontProcess />} />
          <Route path="smt" element={<SMT />} />
          <Route path="lean" element={<Lean />} />
          <Route path="assembly" element={<Assembly />} />
          <Route path="packaging" element={<Packaging />} />
          <Route path="process-exceptions" element={<ProcessExceptions />} />
          <Route path="meetings" element={<MeetingCenter />} />
          <Route path="npi" element={<NPICenter />} />
          <Route path="import" element={<DataImport />} />
          <Route path="risk-rules" element={<RiskRules />} />
          <Route path="inspection-rules" element={<InspectionRules />} />
          <Route path="node-standards" element={<NodeStandards />} />
          <Route path="responsibility-map" element={<ResponsibilityMap />} />
          <Route path="status-dict" element={<StatusDictionary />} />
          <Route path="users" element={<UserManagement />} />
          <Route path="audit" element={<AuditLog />} />
          <Route path="sync-config" element={<SyncSqlConfig />} />
          <Route path="masterdata" element={<Navigate to="/masterdata/customers" replace />} />
          <Route path="masterdata/customers" element={<Customers />} key="customers" />
          <Route path="masterdata/suppliers" element={<Suppliers />} key="suppliers" />
          <Route path="masterdata/materials" element={<Materials />} key="materials" />
          <Route path="masterdata/skus" element={<SKUs />} key="skus" />
          <Route path="masterdata/products" element={<Products />} key="products" />
          <Route path="masterdata/warehouses" element={<Warehouses />} key="warehouses" />
          <Route path="masterdata/processes" element={<Processes />} key="processes" />
          <Route path="masterdata/organizations" element={<Organizations />} key="organizations" />
          <Route path="masterdata/employees" element={<Employees />} key="employees" />
          <Route path="masterdata/feedback" element={<FeedbackManagement />} key="feedback" />
          <Route path="masterdata/files" element={<FileManagement />} key="files" />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
