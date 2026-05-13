import { Row, Col, Table, Tag, Spin, Card } from 'antd'
import { useNavigate } from 'react-router-dom'
import {
  ShoppingCartOutlined,
  WarningOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  AlertOutlined,
  CarOutlined,
  FieldTimeOutlined,
} from '@ant-design/icons'
import RiskBadge from '../../../components/RiskBadge'

interface TodayOverviewData {
  due_today: number
  due_today_red: number
  due_today_yellow: number
  shortage_orders: number
  pending_close_issues: number
  overdue_tasks: number
  in_transit_po: number
  eta_overdue_po: number
  total_orders: number
  red_orders: number
  yellow_orders: number
  blue_orders: number
  green_orders: number
}

interface TodayDueOrder {
  order_no: string
  line_no: string | null
  customer: string | null
  product_name: string | null
  order_qty: number | null
  promised_date: string | null
  risk_level: string | null
  owner: string | null
}

interface TodayOverviewProps {
  overview: TodayOverviewData | null
  dueOrders: TodayDueOrder[]
  loading: boolean
}

const STAT_COLORS: Record<string, string> = {
  'stat-total': '#6366f1', 'stat-red': '#e11d48', 'stat-yellow': '#f59e0b',
  'stat-blue': '#3b82f6', 'stat-green': '#16a34a', 'stat-overdue': '#e11d48', 'stat-transit': '#2563eb',
}

function StatCard({ icon, label, value, className, sub, onClick, clickable }: {
  icon: React.ReactNode; label: string; value: number | string; className: string; sub?: string; onClick?: () => void; clickable?: boolean
}) {
  const color = STAT_COLORS[className] || '#6366f1'
  return (
    <Card 
      size="small" 
      className="card-modern" 
      style={{ padding: 0, cursor: clickable ? 'pointer' : 'default', transition: clickable ? 'all 0.2s' : 'none' }}
      onClick={onClick}
      hoverable={clickable}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{ width: 44, height: 44, borderRadius: 10, background: `${color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, color }}>
          {icon}
        </div>
        <div>
          <div style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>{value ?? '-'}</div>
          <div style={{ fontSize: 12, color: '#64748b' }}>{label}</div>
          {sub && <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>{sub}</div>}
        </div>
      </div>
    </Card>
  )
}

const dueOrderColumns = [
  { title: '订单号', dataIndex: 'order_no', key: 'order_no', width: 120 },
  { title: '行号', dataIndex: 'line_no', key: 'line_no', width: 70 },
  { title: '客户', dataIndex: 'customer', key: 'customer', ellipsis: true },
  { title: '数量', dataIndex: 'order_qty', key: 'order_qty', width: 90, render: (v: number) => v?.toLocaleString() },
  { title: '交期', dataIndex: 'promised_date', key: 'promised_date', width: 110 },
  {
    title: '风险', dataIndex: 'risk_level', key: 'risk_level', width: 80,
    render: (level: string) => <RiskBadge level={level} />,
  },
  { title: '责任人', dataIndex: 'owner', key: 'owner', width: 90 },
]

export default function TodayOverview({ overview: o, dueOrders, loading }: TodayOverviewProps) {
  const navigate = useNavigate()

  if (!o) return <Spin />

  const handleRiskClick = (riskLevel: string) => {
    navigate(`/order-risk-pool?risk_level=${riskLevel}`)
  }

  return (
    <div>
      {/* 核心指标卡片 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '今日应交', value: o.due_today, icon: <ShoppingCartOutlined />, color: '#6366f1', sub: `红${o.due_today_red} 黄${o.due_today_yellow}` },
          { title: '总订单', value: o.total_orders, icon: <CheckCircleOutlined />, color: '#6366f1' },
          { title: '高风险订单', value: o.red_orders, icon: <WarningOutlined />, color: '#e11d48', riskLevel: 'red', clickable: true },
          { title: '中风险订单', value: o.yellow_orders, icon: <ExclamationCircleOutlined />, color: '#f59e0b', riskLevel: 'yellow', clickable: true },
          { title: '低风险订单', value: o.blue_orders, icon: <ExclamationCircleOutlined />, color: '#3b82f6', riskLevel: 'blue', clickable: true },
          { title: '正常订单', value: o.green_orders, icon: <CheckCircleOutlined />, color: '#16a34a' },
        ].map((card, i) => (
          <Col flex={1} key={i}>
            <StatCard
              icon={card.icon}
              label={card.title}
              value={card.value}
              className={card.riskLevel ? `stat-${card.riskLevel}` : 'stat-total'}
              sub={card.sub}
              onClick={card.clickable ? () => handleRiskClick(card.riskLevel!) : undefined}
              clickable={card.clickable}
            />
          </Col>
        ))}
      </Row>

      {/* 第二行：待关闭异常 + 在途PO + ETA超期 */}
      <Row gutter={16} style={{ marginBottom: 16 }}>
        {[
          { title: '待关闭异常', value: o.pending_close_issues, icon: <ClockCircleOutlined />, color: '#2563eb' },
          { title: '在途PO', value: o.in_transit_po, icon: <CarOutlined />, color: '#2563eb' },
          { title: 'ETA超期PO', value: o.eta_overdue_po, icon: <FieldTimeOutlined />, color: '#e11d48' },
        ].map((card, i) => (
          <Col span={8} key={i}>
            <StatCard
              icon={card.icon}
              label={card.title}
              value={card.value}
              className={card.title === 'ETA超期PO' ? 'stat-overdue' : 'stat-transit'}
            />
          </Col>
        ))}
      </Row>

      {/* 今日应交订单表 */}
      <div className="card-modern" style={{ padding: '2px 0 0' }}>
        <div style={{ padding: '16px 20px 8px' }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: '#475569' }}>今日应交订单</h3>
        </div>
        <div className="table-modern">
          <Table
            columns={dueOrderColumns}
            dataSource={dueOrders}
            rowKey={(r) => `${r.order_no}-${r.line_no}`}
            loading={loading}
            size="middle"
            scroll={{ x: 900, y: 'calc(100vh - 520px)' }}
            locale={{ emptyText: '今日无应交订单' }}
            pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条`, style: { padding: '0 16px' } }}
          />
        </div>
      </div>
    </div>
  )
}
