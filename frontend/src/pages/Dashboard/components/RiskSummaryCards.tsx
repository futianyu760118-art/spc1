import { Row, Col, Card } from 'antd'
import {
  WarningOutlined,
  ExclamationCircleOutlined,
  CheckCircleOutlined,
  ReloadOutlined,
  ShoppingCartOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons'

interface RiskSummaryCardsProps {
  summary: {
    total_orders: number
    red_count: number
    yellow_count: number
    green_count: number
    in_transit_count: number
    eta_overdue_count: number
  }
}

export default function RiskSummaryCards({ summary: s }: RiskSummaryCardsProps) {
  const cards = [
    { title: '总订单', value: s.total_orders, icon: <ShoppingCartOutlined />, color: '#6366f1' },
    { title: '高风险', value: s.red_count, icon: <WarningOutlined />, color: '#e11d48' },
    { title: '中风险', value: s.yellow_count, icon: <ExclamationCircleOutlined />, color: '#f59e0b' },
    { title: '正常', value: s.green_count, icon: <CheckCircleOutlined />, color: '#16a34a' },
    { title: '在途PO', value: s.in_transit_count, icon: <ClockCircleOutlined />, color: '#2563eb' },
    { title: 'ETA超期', value: s.eta_overdue_count, icon: <ReloadOutlined />, color: '#e11d48' },
  ]
  return (
    <Row gutter={16} style={{ marginBottom: 16 }}>
      {cards.map((card, i) => (
        <Col flex={1} key={i}>
          <Card size="small" className="card-modern" style={{ padding: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 44, height: 44, borderRadius: 10, background: `${card.color}15`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, color: card.color }}>
                {card.icon}
              </div>
              <div>
                <div style={{ fontSize: 22, fontWeight: 700, color: '#1e293b' }}>{card.value}</div>
                <div style={{ fontSize: 12, color: '#64748b' }}>{card.title}</div>
              </div>
            </div>
          </Card>
        </Col>
      ))}
    </Row>
  )
}
