import { Row, Col, Spin } from 'antd'
import { Pie, Column } from '@ant-design/charts'

interface ChartItem {
  name: string
  value: number
  color?: string
}

interface AnalysisChartsProps {
  loading: boolean
  statusDistribution: ChartItem[]
  supplierOverdueTop5: ChartItem[]
  materialShortageTop5: ChartItem[]
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card-modern" style={{ padding: '16px 20px', height: '100%' }}>
      <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>{title}</h3>
      {children}
    </div>
  )
}

export default function AnalysisCharts({ loading, statusDistribution, supplierOverdueTop5, materialShortageTop5 }: AnalysisChartsProps) {
  const statusPieConfig = {
    data: statusDistribution,
    angleField: 'value',
    colorField: 'name',
    radius: 0.85,
    innerRadius: 0.55,
    color: statusDistribution.map(d => d.color || '#94a3b8'),
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
      title: { content: '总计划', style: { fontSize: '12px', color: '#94a3b8' } },
      content: {
        content: String(statusDistribution.reduce((s, d) => s + d.value, 0)),
        style: { fontSize: '22px', fontWeight: 700, color: '#1e293b' },
      },
    },
    interaction: { elementHighlight: true },
    height: 240,
  }

  const supplierOverdueConfig = {
    data: supplierOverdueTop5,
    xField: 'name',
    yField: 'value',
    color: '#e11d48',
    columnStyle: { radius: [4, 4, 0, 0] },
    label: {
      text: 'value',
      position: 'outside' as const,
      style: { fontSize: 11, fontWeight: 600 },
    },
    axis: {
      x: { title: false, label: { style: { fontSize: 11 }, autoRotate: true } },
      y: { title: false, label: { style: { fontSize: 11 } } },
    },
    height: 240,
  }

  const materialShortageConfig = {
    data: materialShortageTop5,
    xField: 'name',
    yField: 'value',
    color: '#f59e0b',
    columnStyle: { radius: [4, 4, 0, 0] },
    label: {
      text: 'value',
      position: 'outside' as const,
      style: { fontSize: 11, fontWeight: 600 },
    },
    axis: {
      x: { title: false, label: { style: { fontSize: 11 }, autoRotate: true } },
      y: { title: false, label: { style: { fontSize: 11 } } },
    },
    height: 240,
  }

  return (
    <Spin spinning={loading}>
      <Row gutter={[14, 14]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={8}>
          <ChartCard title="采购状态分布">
            {statusDistribution.length > 0 ? (
              <Pie {...statusPieConfig} />
            ) : (
              <div style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无数据</div>
            )}
          </ChartCard>
        </Col>
        <Col xs={24} md={8}>
          <ChartCard title="供应商逾期 Top 5">
            {supplierOverdueTop5.length > 0 ? (
              <Column {...supplierOverdueConfig} />
            ) : (
              <div style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无逾期</div>
            )}
          </ChartCard>
        </Col>
        <Col xs={24} md={8}>
          <ChartCard title="缺料物料 Top 5">
            {materialShortageTop5.length > 0 ? (
              <Column {...materialShortageConfig} />
            ) : (
              <div style={{ height: 240, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无缺料</div>
            )}
          </ChartCard>
        </Col>
      </Row>
    </Spin>
  )
}