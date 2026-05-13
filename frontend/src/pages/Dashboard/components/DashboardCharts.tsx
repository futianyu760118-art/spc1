import { Row, Col } from 'antd'
import { Pie, Column } from '@ant-design/charts'

interface ChartItem {
  name: string
  value: number
  color?: string
}

interface DashboardChartsProps {
  riskPie: ChartItem[]
  issueTypeBar: ChartItem[]
  poStatusPie: ChartItem[]
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card-modern" style={{ padding: '20px 24px', height: '100%' }}>
      <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>{title}</h3>
      {children}
    </div>
  )
}

export default function DashboardCharts({ riskPie, issueTypeBar, poStatusPie }: DashboardChartsProps) {
  const riskPieConfig = {
    data: riskPie,
    angleField: 'value',
    colorField: 'name',
    radius: 0.85,
    innerRadius: 0.55,
    color: riskPie.map(d => d.color || '#94a3b8'),
    label: {
      text: (d: ChartItem) => `${d.name}\n${d.value}`,
      style: { fontSize: 11, fontWeight: 500 },
    },
    legend: {
      color: {
        position: 'bottom' as const,
        layout: { justifyContent: 'center' },
      },
    },
    statistic: {
      title: { content: '总订单', style: { fontSize: '12px', color: '#94a3b8' } },
      content: {
        content: String(riskPie.reduce((s, d) => s + d.value, 0)),
        style: { fontSize: '24px', fontWeight: 700, color: '#1e293b' },
      },
    },
    interaction: { elementHighlight: true },
    height: 260,
  }

  const issueBarConfig = {
    data: issueTypeBar,
    xField: 'name',
    yField: 'value',
    color: '#6366f1',
    columnStyle: { radius: [4, 4, 0, 0] },
    label: {
      text: 'value',
      position: 'inside' as const,
      style: { fill: '#fff', fontSize: 11, fontWeight: 600 },
    },
    axis: {
      x: { title: false, label: { style: { fontSize: 11 } } },
      y: { title: false, label: { style: { fontSize: 11 } } },
    },
    height: 260,
  }

  const poStatusConfig = {
    data: poStatusPie,
    angleField: 'value',
    colorField: 'name',
    radius: 0.85,
    innerRadius: 0.55,
    color: poStatusPie.map(d => d.color || '#94a3b8'),
    label: {
      text: (d: ChartItem) => `${d.name}\n${d.value}`,
      style: { fontSize: 11, fontWeight: 500 },
    },
    legend: {
      color: {
        position: 'bottom' as const,
        layout: { justifyContent: 'center' },
      },
    },
    statistic: {
      title: { content: '总PO', style: { fontSize: '12px', color: '#94a3b8' } },
      content: {
        content: String(poStatusPie.reduce((s, d) => s + d.value, 0)),
        style: { fontSize: '24px', fontWeight: 700, color: '#1e293b' },
      },
    },
    interaction: { elementHighlight: true },
    height: 260,
  }

  return (
    <Row gutter={[14, 14]} style={{ marginBottom: 18 }}>
      <Col xs={24} md={8}>
        <ChartCard title="订单风险分布">
          {riskPie.length > 0 ? (
            <Pie {...riskPieConfig} />
          ) : (
            <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无数据</div>
          )}
        </ChartCard>
      </Col>
      <Col xs={24} md={8}>
        <ChartCard title="异常问题类型分布">
          {issueTypeBar.length > 0 ? (
            <Column {...issueBarConfig} />
          ) : (
            <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无异常</div>
          )}
        </ChartCard>
      </Col>
      <Col xs={24} md={8}>
        <ChartCard title="PO 状态分布">
          {poStatusPie.length > 0 ? (
            <Pie {...poStatusConfig} />
          ) : (
            <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无数据</div>
          )}
        </ChartCard>
      </Col>
    </Row>
  )
}
