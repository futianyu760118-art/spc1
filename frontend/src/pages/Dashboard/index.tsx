import { useEffect, useState, useCallback } from 'react'
import { Tabs, Button, message, Space, Modal, Spin } from 'antd'
import {
  ReloadOutlined,
  EyeOutlined,
  CalendarOutlined,
  PieChartOutlined,
  CheckSquareOutlined,
  ShoppingCartOutlined,
  RocketOutlined,
} from '@ant-design/icons'
import TodayOverview from './components/TodayOverview'
import RollingRisk14Days from './components/RollingRisk14Days'
import OrderRiskDistribution from './components/OrderRiskDistribution'
import ClosureAchievement from './components/ClosureAchievement'
import ProcurementBoard from './components/ProcurementBoard'
import ShipmentBoard from './components/ShipmentBoard'
import { dashboardApi, riskApi } from '../../services/api'

type DashboardTab = 'today' | 'rolling' | 'distribution' | 'closure' | 'procurement' | 'shipment'

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState<DashboardTab>('today')
  const [scanning, setScanning] = useState(false)

  // 今日总览
  const [todayOverview, setTodayOverview] = useState<any>(null)
  const [todayDueOrders, setTodayDueOrders] = useState<any[]>([])
  const [todayLoading, setTodayLoading] = useState(false)

  // 14天滚动风险
  const [rollingRisk, setRollingRisk] = useState<any>(null)
  const [rollingLoading, setRollingLoading] = useState(false)
  const [selectedDate, setSelectedDate] = useState<string | null>(
    new Date().toISOString().slice(0, 10)
  )

  // 订单风险分布
  const [riskDistribution, setRiskDistribution] = useState<any>(null)
  const [distributionLoading, setDistributionLoading] = useState(false)

  // 闭环达成
  const [closureData, setClosureData] = useState<any>(null)
  const [closureLoading, setClosureLoading] = useState(false)

  // ===== 数据获取 =====

  const fetchTodayOverview = useCallback(async () => {
    setTodayLoading(true)
    try {
      const [overviewRes, ordersRes]: any[] = await Promise.all([
        dashboardApi.getTodayOverview(),
        dashboardApi.getTodayDueOrders({ page: 1, page_size: 50 }),
      ])
      setTodayOverview(overviewRes.data)
      setTodayDueOrders(ordersRes.data.items || [])
    } catch {
      message.error('获取今日总览失败')
    } finally {
      setTodayLoading(false)
    }
  }, [])

  const fetchRollingRisk = useCallback(async () => {
    setRollingLoading(true)
    try {
      const res: any = await dashboardApi.getRollingRisk()
      setRollingRisk(res.data)
    } catch {
      message.error('获取滚动风险数据失败')
    } finally {
      setRollingLoading(false)
    }
  }, [])

  const fetchRiskDistribution = useCallback(async () => {
    setDistributionLoading(true)
    try {
      const res: any = await dashboardApi.getOrderRiskDistribution()
      setRiskDistribution(res.data)
    } catch {
      message.error('获取风险分布数据失败')
    } finally {
      setDistributionLoading(false)
    }
  }, [])

  const fetchClosureAchievement = useCallback(async () => {
    setClosureLoading(true)
    try {
      const res: any = await dashboardApi.getClosureAchievement()
      setClosureData(res.data)
    } catch {
      message.error('获取闭环数据失败')
    } finally {
      setClosureLoading(false)
    }
  }, [])

  // 按Tab加载
  useEffect(() => {
    if (activeTab === 'today' && !todayOverview) fetchTodayOverview()
    else if (activeTab === 'rolling' && !rollingRisk) fetchRollingRisk()
    else if (activeTab === 'distribution' && !riskDistribution) fetchRiskDistribution()
    else if (activeTab === 'closure' && !closureData) fetchClosureAchievement()
  }, [activeTab])

  // 风险扫描
  const handleScan = () => {
    Modal.confirm({
      title: '确认触发风险扫描',
      content: '将对所有活跃订单执行风险扫描并生成异常记录，确认继续？',
      okText: '确认扫描',
      cancelText: '取消',
      onOk: async () => {
        setScanning(true)
        try {
          const res: any = await riskApi.scan()
          message.success(`扫描完成: ${res.data.new_issues} 个新问题, ${res.data.updated_orders} 个订单更新`)
          // 刷新当前Tab
          if (activeTab === 'today') fetchTodayOverview()
          else if (activeTab === 'rolling') fetchRollingRisk()
          else if (activeTab === 'distribution') fetchRiskDistribution()
          else if (activeTab === 'closure') fetchClosureAchievement()
        } catch {
          message.error('风险扫描失败')
        } finally {
          setScanning(false)
        }
      },
    })
  }

  const handleRefresh = () => {
    if (activeTab === 'today') { setTodayOverview(null); fetchTodayOverview() }
    else if (activeTab === 'rolling') { setRollingRisk(null); fetchRollingRisk() }
    else if (activeTab === 'distribution') { setRiskDistribution(null); fetchRiskDistribution() }
    else if (activeTab === 'closure') { setClosureData(null); fetchClosureAchievement() }
  }

  const tabItems = [
    {
      key: 'today',
      label: (
        <span><EyeOutlined style={{ marginRight: 6 }} />今日总览</span>
      ),
      children: (
        <TodayOverview
          overview={todayOverview}
          dueOrders={todayDueOrders}
          loading={todayLoading}
        />
      ),
    },
    {
      key: 'rolling',
      label: (
        <span><CalendarOutlined style={{ marginRight: 6 }} />14天滚动风险</span>
      ),
      children: (
        <RollingRisk14Days
          data={rollingRisk}
          loading={rollingLoading}
          onDayClick={setSelectedDate}
          selectedDate={selectedDate}
        />
      ),
    },
    {
      key: 'distribution',
      label: (
        <span><PieChartOutlined style={{ marginRight: 6 }} />订单风险分布</span>
      ),
      children: (
        <OrderRiskDistribution
          data={riskDistribution}
          loading={distributionLoading}
        />
      ),
    },
    {
      key: 'closure',
      label: (
        <span><CheckSquareOutlined style={{ marginRight: 6 }} />闭环达成看板</span>
      ),
      children: (
        <ClosureAchievement
          data={closureData}
          loading={closureLoading}
        />
      ),
    },
    {
      key: 'procurement',
      label: (
        <span><ShoppingCartOutlined style={{ marginRight: 6 }} />采购看板</span>
      ),
      children: <ProcurementBoard />,
    },
    {
      key: 'shipment',
      label: (
        <span><RocketOutlined style={{ marginRight: 6 }} />出货计划看板</span>
      ),
      children: <ShipmentBoard />,
    },
  ]

  return (
    <div>
      {/* ===== Tab 视图 ===== */}
      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as DashboardTab)}
        items={tabItems}
        type="card"
        className="dashboard-tabs"
        tabBarExtraContent={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={handleRefresh}>刷新</Button>
            <Button type="primary" icon={<ReloadOutlined />} onClick={handleScan} loading={scanning}>风险扫描</Button>
          </Space>
        }
      />
    </div>
  )
}
