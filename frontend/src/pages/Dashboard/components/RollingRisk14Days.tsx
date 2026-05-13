import { Row, Col, Table, Tag, Tooltip, Spin, Card } from 'antd'
import { CalendarOutlined, WarningOutlined, ExclamationCircleOutlined, AlertOutlined } from '@ant-design/icons'
import { Column } from '@ant-design/charts'
import { useRef, useEffect, useState } from 'react'
import RiskBadge from '../../../components/RiskBadge'
import RiskDetailModal from '../../../components/RiskDetailModal'

interface RollingRiskDay {
  date: string
  due_count: number
  red_count: number
  yellow_count: number
  blue_count: number
  orders: Array<{
    order_no: string
    line_no: string | null
    customer: string | null
    product_name: string | null
    order_qty: number | null
    promised_date: string | null
    risk_level: string | null
    owner: string | null
    risk_score: number | null
    risk_factors: Record<string, number> | null
    risk_assessed_at: string | null
  }>
}

interface RollingRiskData {
  days: RollingRiskDay[]
  total_due: number
  total_red: number
  total_yellow: number
  total_blue: number
}

interface RollingRiskProps {
  data: RollingRiskData | null
  loading: boolean
  onDayClick: (date: string) => void
  selectedDate: string | null
}

function DayCard({ day, selected, onClick }: { day: RollingRiskDay; selected: boolean; onClick: () => void }) {
  const isToday = day.date === new Date().toISOString().slice(0, 10)
  const hasRisk = day.red_count > 0 || day.yellow_count > 0

  return (
    <div
      onClick={onClick}
      className={`rolling-day-card ${selected ? 'rolling-day-selected' : ''} ${hasRisk ? 'rolling-day-risk' : ''}`}
      style={{ cursor: 'pointer' }}
    >
      <div style={{ fontSize: 12, color: isToday ? '#6366f1' : '#64748b', fontWeight: isToday ? 700 : 500 }}>
        {isToday ? '今日' : new Date(day.date + 'T00:00:00').toLocaleDateString('zh-CN', { weekday: 'short' })}
      </div>
      <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 6 }}>
        {day.date.slice(5)}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: hasRisk ? '#e11d48' : '#10b981' }}>
        {day.due_count}
      </div>
      <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
        {day.red_count > 0 && <Tag color="red" style={{ fontSize: 10, margin: 0, padding: '0 4px' }}>红{day.red_count}</Tag>}
        {day.yellow_count > 0 && <Tag color="orange" style={{ fontSize: 10, margin: 0, padding: '0 4px' }}>黄{day.yellow_count}</Tag>}
        {day.blue_count > 0 && <Tag color="blue" style={{ fontSize: 10, margin: 0, padding: '0 4px' }}>蓝{day.blue_count}</Tag>}
      </div>
    </div>
  )
}

const orderColumns = [
  { title: '订单号', dataIndex: 'order_no', key: 'order_no', width: 120 },
  { title: '客户', dataIndex: 'customer', key: 'customer', ellipsis: true },
  { title: '数量', dataIndex: 'order_qty', key: 'order_qty', width: 80, render: (v: number) => v?.toLocaleString() },
  {
    title: '风险', dataIndex: 'risk_level', key: 'risk_level', width: 80,
    render: (level: string, record: any) => (
      <RiskBadge
        level={level}
        onClick={() => record.onRiskClick && record.onRiskClick(record)}
      />
    ),
  },
]

export default function RollingRisk14Days({ data, loading, onDayClick, selectedDate }: RollingRiskProps) {
  const barChartRef = useRef<any>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [riskModalOpen, setRiskModalOpen] = useState(false)
  const [selectedOrder, setSelectedOrder] = useState<any>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      requestAnimationFrame(() => {
        barChartRef.current?.resize()
      })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  if (loading || !data) return <Spin />

  // 柱状图数据
  const chartData: Array<{ date: string; type: string; value: number }> = []
  data.days.forEach(d => {
    chartData.push({ date: d.date.slice(5), type: '高风险', value: d.red_count })
    chartData.push({ date: d.date.slice(5), type: '中风险', value: d.yellow_count })
    chartData.push({ date: d.date.slice(5), type: '低风险', value: d.blue_count })
  })

  const chartConfig = {
    data: chartData,
    xField: 'date',
    yField: 'value',
    colorField: 'type',
    stack: true,
    color: ['#e11d48', '#f59e0b', '#3b82f6'],
    columnStyle: { radius: [2, 2, 0, 0] },
    axis: {
      x: { title: false, label: { style: { fontSize: 10 } } },
      y: { title: false, label: { style: { fontSize: 10 } } },
    },
    legend: {
      color: { position: 'top' as const },
    },
    height: 200,
  }

  const selectedDay = data.days.find(d => d.date === selectedDate)

  // 为订单添加onRiskClick处理
  const ordersWithClickHandler = selectedDay?.orders.map(order => ({
    ...order,
    onRiskClick: (record: any) => {
      setSelectedOrder(record)
      setRiskModalOpen(true)
    }
  })) || []

  return (
    <div ref={containerRef}>
      {/* 汇总条 */}
      <Row gutter={16} style={{ marginBottom: 14 }}>
        {[
          { title: '14天应交', value: data.total_due, icon: <CalendarOutlined />, color: '#6366f1' },
          { title: '高风险', value: data.total_red, icon: <WarningOutlined />, color: '#e11d48' },
          { title: '中风险', value: data.total_yellow, icon: <ExclamationCircleOutlined />, color: '#f59e0b' },
          { title: '低风险', value: data.total_blue, icon: <AlertOutlined />, color: '#3b82f6' },
        ].map((card, i) => (
          <Col span={6} key={i}>
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

      {/* 14天日历条 */}
      <div style={{
        display: 'flex', gap: 8, overflowX: 'auto', marginBottom: 18,
        padding: '4px 0',
      }}>
        {data.days.map(day => (
          <DayCard
            key={day.date}
            day={day}
            selected={day.date === selectedDate}
            onClick={() => onDayClick(day.date)}
          />
        ))}
      </div>

      {/* 柱状图 + 订单表 */}
      <Row gutter={[14, 14]}>
        <Col xs={24} lg={10}>
          <div className="card-modern" style={{ padding: '20px 24px', height: '100%' }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600, color: '#475569' }}>交付节奏与风险分布</h3>
            {chartData.length > 0 ? (
              <Column {...chartConfig} onReady={(chart: any) => { barChartRef.current = chart }} />
            ) : (
              <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>
                暂无数据
              </div>
            )}
          </div>
        </Col>
        <Col xs={24} lg={14}>
          <div className="card-modern" style={{ padding: '2px 0 0' }}>
            <div style={{ padding: '16px 20px 8px' }}>
              <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: '#475569' }}>
                {selectedDate ? `${selectedDate} 风险订单` : '点击日期查看风险订单'}
              </h3>
            </div>
            <div className="table-modern">
              <Table
                columns={orderColumns}
                dataSource={ordersWithClickHandler}
                rowKey={(r) => `${r.order_no}-${r.line_no}`}
                size="middle"
                scroll={{ y: 260 }}
                locale={{ emptyText: selectedDate ? '该日无风险订单' : '请点击上方日期查看' }}
                pagination={false}
              />
            </div>
          </div>
        </Col>
      </Row>

      {/* 风险详情弹窗 */}
      <RiskDetailModal
        visible={riskModalOpen}
        order={selectedOrder}
        onClose={() => { setRiskModalOpen(false); setSelectedOrder(null) }}
      />
    </div>
  )
}
