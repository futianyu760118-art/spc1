import { Row, Col, Table, Tag, Spin, Segmented, Progress } from 'antd'
import { Pie, Column } from '@ant-design/charts'
import { useState, useRef, useEffect } from 'react'

interface RiskDimensionItem {
  name: string
  red_count: number
  yellow_count: number
  blue_count: number
  green_count: number
  total_count: number
}

interface RiskFactorDistributionItem {
  factor: string
  factor_label: string
  red_count: number
  yellow_count: number
  blue_count: number
  green_count: number
  total_count: number
  avg_score: number
}

interface OrderRiskDistributionData {
  by_customer: RiskDimensionItem[]
  by_product: RiskDimensionItem[]
  by_owner: RiskDimensionItem[]
  by_department: RiskDimensionItem[]
  by_risk_level: RiskDimensionItem[]
  by_factor: RiskFactorDistributionItem[]
}

interface OrderRiskDistributionProps {
  data: OrderRiskDistributionData | null
  loading: boolean
}

type DimensionKey = 'by_customer' | 'by_product' | 'by_owner' | 'by_department' | 'by_factor'

const dimensionLabels: Record<DimensionKey, string> = {
  by_customer: '按客户',
  by_product: '按产品',
  by_owner: '按责任人',
  by_department: '按部门',
  by_factor: '按风险因子',
}

const columns = [
  { title: '名称', dataIndex: 'name', key: 'name', width: 160, ellipsis: true },
  { title: '总数', dataIndex: 'total_count', key: 'total_count', width: 80, sorter: (a: RiskDimensionItem, b: RiskDimensionItem) => a.total_count - b.total_count },
  {
    title: '高风险', dataIndex: 'red_count', key: 'red_count', width: 90,
    render: (v: number) => v > 0 ? <Tag color="red">{v}</Tag> : <span style={{ color: '#94a3b8' }}>0</span>,
    sorter: (a: RiskDimensionItem, b: RiskDimensionItem) => a.red_count - b.red_count,
  },
  {
    title: '中风险', dataIndex: 'yellow_count', key: 'yellow_count', width: 90,
    render: (v: number) => v > 0 ? <Tag color="orange">{v}</Tag> : <span style={{ color: '#94a3b8' }}>0</span>,
    sorter: (a: RiskDimensionItem, b: RiskDimensionItem) => a.yellow_count - b.yellow_count,
  },
  {
    title: '低风险', dataIndex: 'blue_count', key: 'blue_count', width: 80,
    render: (v: number) => v > 0 ? <Tag color="blue">{v}</Tag> : <span style={{ color: '#94a3b8' }}>0</span>,
  },
  {
    title: '正常', dataIndex: 'green_count', key: 'green_count', width: 80,
    render: (v: number) => v > 0 ? <Tag color="green">{v}</Tag> : <span style={{ color: '#94a3b8' }}>0</span>,
  },
  {
    title: '风险占比', key: 'risk_ratio', width: 120,
    render: (_: any, r: RiskDimensionItem) => {
      const ratio = r.total_count > 0 ? Math.round(((r.red_count + r.yellow_count + r.blue_count) / r.total_count) * 100) : 0
      const color = ratio >= 60 ? '#e11d48' : ratio >= 30 ? '#f59e0b' : '#10b981'
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div style={{ width: 60, height: 6, borderRadius: 3, background: '#f1f5f9' }}>
            <div style={{ width: `${ratio}%`, height: '100%', borderRadius: 3, background: color, transition: 'width .3s' }} />
          </div>
          <span style={{ fontSize: 11, color }}>{ratio}%</span>
        </div>
      )
    },
  },
]

const factorColumns = [
  { title: '因子', dataIndex: 'factor_label', key: 'factor_label', width: 100 },
  {
    title: '涉及订单', dataIndex: 'total_count', key: 'total_count', width: 90,
    sorter: (a: RiskFactorDistributionItem, b: RiskFactorDistributionItem) => a.total_count - b.total_count,
  },
  {
    title: '高风险', dataIndex: 'red_count', key: 'red_count', width: 90,
    render: (v: number) => v > 0 ? <Tag color="red">{v}</Tag> : <span style={{ color: '#94a3b8' }}>0</span>,
    sorter: (a: RiskFactorDistributionItem, b: RiskFactorDistributionItem) => a.red_count - b.red_count,
  },
  {
    title: '中风险', dataIndex: 'yellow_count', key: 'yellow_count', width: 90,
    render: (v: number) => v > 0 ? <Tag color="orange">{v}</Tag> : <span style={{ color: '#94a3b8' }}>0</span>,
    sorter: (a: RiskFactorDistributionItem, b: RiskFactorDistributionItem) => a.yellow_count - b.yellow_count,
  },
  {
    title: '低风险', dataIndex: 'blue_count', key: 'blue_count', width: 80,
    render: (v: number) => v > 0 ? <Tag color="blue">{v}</Tag> : <span style={{ color: '#94a3b8' }}>0</span>,
  },
  {
    title: '正常', dataIndex: 'green_count', key: 'green_count', width: 80,
    render: (v: number) => v > 0 ? <Tag color="green">{v}</Tag> : <span style={{ color: '#94a3b8' }}>0</span>,
  },
  {
    title: '平均分值', dataIndex: 'avg_score', key: 'avg_score', width: 130,
    sorter: (a: RiskFactorDistributionItem, b: RiskFactorDistributionItem) => a.avg_score - b.avg_score,
    render: (v: number) => {
      const color = v >= 10 ? '#e11d48' : v >= 5 ? '#f59e0b' : '#10b981'
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Progress percent={Math.min(v / 30 * 100, 100)} size="small" strokeColor={color} showInfo={false} style={{ width: 60, marginBottom: 0 }} />
          <span style={{ fontSize: 12, fontWeight: 600, color }}>{v}</span>
        </div>
      )
    },
  },
]

export default function OrderRiskDistribution({ data, loading }: OrderRiskDistributionProps) {
  const [dimension, setDimension] = useState<DimensionKey>('by_customer')
  const pieChartRef = useRef<any>(null)
  const barChartRef = useRef<any>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      requestAnimationFrame(() => {
        pieChartRef.current?.resize()
        barChartRef.current?.resize()
      })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  if (loading || !data) return <Spin />

  const isFactorMode = dimension === 'by_factor'
  const factorItems = data.by_factor || []

  // 非因子维度的常规数据
  const items = !isFactorMode ? (data[dimension] || []) : []

  // 饼图数据 — 因子模式下按因子占比，否则按风险等级
  const pieData = isFactorMode
    ? factorItems.map(item => ({
        name: item.factor_label,
        value: item.total_count,
        color: item.avg_score >= 10 ? '#e11d48' : item.avg_score >= 5 ? '#f59e0b' : '#10b981',
      }))
    : data.by_risk_level.map(item => ({
        name: item.name === 'red' ? '高风险' : item.name === 'yellow' ? '中风险' : item.name === 'blue' ? '低风险' : item.name === 'green' ? '正常' : item.name,
        value: item.total_count,
        color: item.name === 'red' ? '#e11d48' : item.name === 'yellow' ? '#f59e0b' : item.name === 'blue' ? '#3b82f6' : item.name === 'green' ? '#10b981' : '#94a3b8',
      }))

  const pieConfig = {
    data: pieData,
    angleField: 'value',
    colorField: 'name',
    radius: 0.85,
    innerRadius: 0.55,
    color: pieData.map(d => d.color),
    label: {
      text: (d: any) => `${d.name}\n${d.value}`,
      style: { fontSize: 11, fontWeight: 500 },
    },
    legend: {
      color: { position: 'bottom' as const, layout: { justifyContent: 'center' } },
    },
    statistic: {
      title: { content: isFactorMode ? '因子分布' : '总订单', style: { fontSize: '12px', color: '#94a3b8' } },
      content: {
        content: String(pieData.reduce((s, d) => s + d.value, 0)),
        style: { fontSize: '24px', fontWeight: 700, color: '#1e293b' },
      },
    },
    interaction: { elementHighlight: true },
    height: 260,
  }

  // 柱状图数据 — 因子模式下按因子红/黄/绿，否则按维度
  const barData: Array<{ name: string; type: string; value: number }> = []
  if (isFactorMode) {
    factorItems.forEach(item => {
      barData.push({ name: item.factor_label, type: '高风险', value: item.red_count })
      barData.push({ name: item.factor_label, type: '中风险', value: item.yellow_count })
      barData.push({ name: item.factor_label, type: '低风险', value: item.blue_count })
      barData.push({ name: item.factor_label, type: '正常', value: item.green_count })
    })
  } else {
    items.slice(0, 10).forEach(item => {
      barData.push({ name: item.name, type: '高风险', value: item.red_count })
      barData.push({ name: item.name, type: '中风险', value: item.yellow_count })
      barData.push({ name: item.name, type: '低风险', value: item.blue_count })
      barData.push({ name: item.name, type: '正常', value: item.green_count })
    })
  }

  const barConfig = {
    data: barData,
    xField: 'name',
    yField: 'value',
    colorField: 'type',
    stack: true,
    color: ['#e11d48', '#f59e0b', '#3b82f6', '#10b981'],
    columnStyle: { radius: [4, 4, 0, 0] },
    axis: {
      x: { title: false, label: { style: { fontSize: 10 }, autoRotate: true } },
      y: { title: false, label: { style: { fontSize: 10 } } },
    },
    legend: { color: { position: 'top' as const } },
    height: 260,
  }

  return (
    <div ref={containerRef}>
      {/* 维度切换 */}
      <div style={{ marginBottom: 14 }}>
        <Segmented
          value={dimension}
          onChange={(v) => setDimension(v as DimensionKey)}
          options={Object.entries(dimensionLabels).map(([key, label]) => ({ value: key, label }))}
        />
      </div>

      <Row gutter={[14, 14]} style={{ marginBottom: 18 }}>
        {/* 饼图 */}
        <Col xs={24} md={8}>
          <div className="card-modern" style={{ padding: '20px 24px', height: '100%' }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600, color: '#475569' }}>
              {isFactorMode ? '因子占比分布' : '风险等级分布'}
            </h3>
            {pieData.length > 0 ? (
              <Pie {...pieConfig} onReady={(chart: any) => { pieChartRef.current = chart }} />
            ) : (
              <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无数据</div>
            )}
          </div>
        </Col>

        {/* 柱状图 */}
        <Col xs={24} md={16}>
          <div className="card-modern" style={{ padding: '20px 24px', height: '100%' }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600, color: '#475569' }}>
              {dimensionLabels[dimension]}风险分布
            </h3>
            {barData.length > 0 ? (
              <Column {...barConfig} onReady={(chart: any) => { barChartRef.current = chart }} />
            ) : (
              <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无数据</div>
            )}
          </div>
        </Col>
      </Row>

      {/* 详细表格 */}
      <div className="card-modern" style={{ padding: '2px 0 0' }}>
        <div style={{ padding: '16px 20px 8px' }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: '#475569' }}>
            {dimensionLabels[dimension]}风险明细
          </h3>
        </div>
        <div className="table-modern">
          <Table
            columns={(isFactorMode ? factorColumns : columns) as any[]}
            dataSource={(isFactorMode ? factorItems : items) as any[]}
            rowKey={isFactorMode ? 'factor' : 'name'}
            size="middle"
            scroll={{ y: 'calc(100vh - 580px)' }}
            locale={{ emptyText: '暂无数据' }}
            pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 条`, style: { padding: '0 16px' } }}
          />
        </div>
      </div>
    </div>
  )
}
