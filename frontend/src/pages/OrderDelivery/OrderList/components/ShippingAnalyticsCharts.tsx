import { useState } from 'react'
import { Row, Col, Spin, Segmented } from 'antd'
import { Pie, Column } from '@ant-design/charts'

interface ChartItem {
  name: string
  value: number
  color?: string
}

interface ShippingAnalyticsData {
  change_distribution: ChartItem[]
  change_by_dept: ChartItem[]
  change_by_customer: ChartItem[]
  delivery_stats: ChartItem[]
  delivery_by_dept: ChartItem[]
  delivery_by_customer: ChartItem[]
}

interface Props {
  loading: boolean
  data: ShippingAnalyticsData | null
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card-modern" style={{ padding: '16px 20px', height: '100%' }}>
      <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>{title}</h3>
      {children}
    </div>
  )
}

export default function ShippingAnalyticsCharts({ loading, data }: Props) {
  const [changeDim, setChangeDim] = useState<'dept' | 'customer'>('dept')
  const [deliveryDim, setDeliveryDim] = useState<'dept' | 'customer'>('dept')

  if (!data) {
    return (
      <Spin spinning={loading}>
        <Row gutter={[14, 14]} style={{ marginBottom: 16 }}>
          <Col xs={24} md={12}>
            <ChartCard title="出货计划变更次数分布">
              <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>加载中...</div>
            </ChartCard>
          </Col>
          <Col xs={24} md={12}>
            <ChartCard title="变更集中度">
              <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>加载中...</div>
            </ChartCard>
          </Col>
          <Col xs={24} md={12}>
            <ChartCard title="发货完成情况">
              <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>加载中...</div>
            </ChartCard>
          </Col>
          <Col xs={24} md={12}>
            <ChartCard title="按时交付率">
              <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>加载中...</div>
            </ChartCard>
          </Col>
        </Row>
      </Spin>
    )
  }

  const changeDistributionConfig = {
    data: data.change_distribution,
    xField: 'name',
    yField: 'value',
    color: '#6366f1',
    columnStyle: { radius: [4, 4, 0, 0] },
    label: {
      text: 'value',
      position: 'outside' as const,
      style: { fontSize: 12, fontWeight: 600 },
    },
    axis: {
      x: { title: false, label: { style: { fontSize: 12 } } },
      y: { title: false, label: { style: { fontSize: 11 } } },
    },
    height: 280,
  }

  const changeItems = changeDim === 'dept' ? data.change_by_dept : data.change_by_customer
  const hasChangeItems = changeItems.length > 0

  const changeByDimConfig = {
    data: changeItems,
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
    height: 280,
  }

  const deliveryPieConfig = {
    data: data.delivery_stats,
    angleField: 'value',
    colorField: 'name',
    radius: 0.85,
    innerRadius: 0.55,
    color: data.delivery_stats.map(d => d.color || '#94a3b8'),
    label: {
      text: (d: ChartItem) => `${d.name}\n${d.value}`,
      style: { fontSize: 12, fontWeight: 500 },
    },
    legend: {
      color: {
        position: 'bottom' as const,
        layout: { justifyContent: 'center' },
      },
    },
    statistic: {
      title: { content: '已完成', style: { fontSize: '12px', color: '#94a3b8' } },
      content: {
        content: String(data.delivery_stats.reduce((s, d) => s + d.value, 0)),
        style: { fontSize: '24px', fontWeight: 700, color: '#1e293b' },
      },
    },
    interaction: { elementHighlight: true },
    height: 280,
  }

  const deliveryItems = deliveryDim === 'dept' ? data.delivery_by_dept : data.delivery_by_customer
  const hasDeliveryItems = deliveryItems.length > 0

  const deliveryByDimConfig = {
    data: deliveryItems,
    xField: 'name',
    yField: 'value',
    color: '#16a34a',
    columnStyle: { radius: [4, 4, 0, 0] },
    label: {
      text: (d: ChartItem) => `${(d.value * 100).toFixed(0)}%`,
      position: 'outside' as const,
      style: { fontSize: 11, fontWeight: 600 },
    },
    axis: {
      x: { title: false, label: { style: { fontSize: 11 }, autoRotate: true } },
      y: { title: false, label: { style: { fontSize: 11, formatter: (v: number) => `${(v * 100).toFixed(0)}%` } } },
    },
    scale: { y: { nice: true, max: 1, min: 0 } },
    height: 280,
  }

  return (
    <Spin spinning={loading}>
      <Row gutter={[14, 14]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={12}>
          <ChartCard title="出货计划变更次数分布">
            {data.change_distribution.length > 0 ? (
              <Column {...changeDistributionConfig} />
            ) : (
              <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无数据</div>
            )}
          </ChartCard>
        </Col>
        <Col xs={24} md={12}>
          <ChartCard title="变更集中度">
            <div style={{ marginBottom: 8 }}>
              <Segmented
                size="small"
                options={[
                  { label: '部门', value: 'dept' },
                  { label: '客户', value: 'customer' },
                ]}
                value={changeDim}
                onChange={(v) => setChangeDim(v as 'dept' | 'customer')}
              />
            </div>
            {hasChangeItems ? (
              <Column {...changeByDimConfig} />
            ) : (
              <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无数据</div>
            )}
          </ChartCard>
        </Col>
        <Col xs={24} md={12}>
          <ChartCard title="发货完成情况">
            {data.delivery_stats.length > 0 ? (
              <Pie {...deliveryPieConfig} />
            ) : (
              <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无数据</div>
            )}
          </ChartCard>
        </Col>
        <Col xs={24} md={12}>
          <ChartCard title="按时交付率">
            <div style={{ marginBottom: 8 }}>
              <Segmented
                size="small"
                options={[
                  { label: '部门', value: 'dept' },
                  { label: '客户', value: 'customer' },
                ]}
                value={deliveryDim}
                onChange={(v) => setDeliveryDim(v as 'dept' | 'customer')}
              />
            </div>
            {hasDeliveryItems ? (
              <Column {...deliveryByDimConfig} />
            ) : (
              <div style={{ height: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无数据</div>
            )}
          </ChartCard>
        </Col>
      </Row>
    </Spin>
  )
}
