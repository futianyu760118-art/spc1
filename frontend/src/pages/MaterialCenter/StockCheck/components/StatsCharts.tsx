import { useEffect, useState } from 'react'
import { Row, Col, Spin, Empty, Collapse } from 'antd'
import { Pie, Bar } from '@ant-design/charts'
import { materialApi } from '@/services/api'

interface TopDiffMaterial {
  material_code: string
  material_name: string
  diff_qty: number
  unit?: string | null
}

interface StatsData {
  total_checked: number
  gain_count: number
  loss_count: number
  flat_count: number
  total_gain_qty: number
  total_loss_qty: number
  top_diff_materials: TopDiffMaterial[]
}

interface StatsFilters {
  check_type?: string
  date_from?: string
  date_to?: string
  status?: string
}

interface StatsChartsProps {
  filters: StatsFilters
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card-modern" style={{ padding: '16px 20px', height: '100%' }}>
      <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>{title}</h3>
      {children}
    </div>
  )
}

function fmt(n: number | null | undefined): string {
  if (n == null) return '0'
  const v = Number(n)
  return Number.isInteger(v) ? String(v) : v.toFixed(2)
}

export default function StatsCharts({ filters }: StatsChartsProps) {
  const [data, setData] = useState<StatsData | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    materialApi
      .getStockCheckStats(filters)
      .then((res: any) => {
        if (cancelled) return
        setData(res.data ?? null)
      })
      .catch(() => {
        if (!cancelled) setData(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [JSON.stringify(filters)])

  const pieData = data
    ? [
        { name: '盘盈', value: data.gain_count, color: '#10b981' },
        { name: '盘亏', value: data.loss_count, color: '#ef4444' },
        { name: '持平', value: data.flat_count, color: '#94a3b8' },
      ].filter((d) => d.value > 0)
    : []

  const barData = (data?.top_diff_materials ?? []).map((m) => ({
    label: m.material_code || m.material_name || '—',
    full: `${m.material_name || ''} (${m.material_code || ''})`,
    value: Number(m.diff_qty) || 0,
    type: (Number(m.diff_qty) || 0) >= 0 ? '盘盈' : '盘亏',
    unit: m.unit || '',
  }))

  const pieConfig = {
    data: pieData,
    angleField: 'value',
    colorField: 'name',
    radius: 0.85,
    innerRadius: 0.55,
    color: pieData.map((d) => d.color),
    label: {
      text: (d: { name: string; value: number }) => `${d.name}\n${d.value}`,
      style: { fontSize: 11, fontWeight: 500 },
    },
    legend: {
      color: {
        position: 'bottom' as const,
        layout: { justifyContent: 'center' },
      },
    },
    statistic: {
      title: { content: '已盘', style: { fontSize: '12px', color: '#94a3b8' } },
      content: {
        content: String(data?.total_checked ?? 0),
        style: { fontSize: '22px', fontWeight: 700, color: '#1e293b' },
      },
    },
    interaction: { elementHighlight: true },
    height: 260,
  }

  const barConfig = {
    data: barData,
    xField: 'value',
    yField: 'label',
    colorField: 'type',
    color: (datum: any) => (datum.type === '盘盈' ? '#10b981' : '#ef4444'),
    barStyle: { radius: [0, 4, 4, 0] },
    axis: {
      x: { title: false, label: { style: { fontSize: 11 } } },
      y: { title: false, label: { style: { fontSize: 11 }, autoEllipsis: true, autoRotate: false } },
    },
    tooltip: {
      title: 'full',
      items: [{ name: '净差异', field: 'value', valueFormatter: (v: number) => fmt(v) }],
    },
    height: 260,
  }

  return (
    <Collapse
      defaultActiveKey={['stats']}
      bordered={false}
      style={{ marginBottom: 16, background: 'transparent' }}
      items={[
        {
          key: 'stats',
          label: '统计图表',
          children: (
            <Spin spinning={loading}>
              <Row gutter={[14, 14]}>
                <Col xs={24} md={8}>
                  <ChartCard title="盘盈盘亏分布">
                    {pieData.length > 0 ? (
                      <Pie {...pieConfig} />
                    ) : (
                      <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Empty description={loading ? '加载中…' : '暂无已盘数据'} />
                      </div>
                    )}
                  </ChartCard>
                </Col>
                <Col xs={24} md={16}>
                  <ChartCard title="差异物料 Top 10（按净差异）">
                    {barData.length > 0 ? (
                      <Bar {...barConfig} />
                    ) : (
                      <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Empty description={loading ? '加载中…' : '暂无差异物料'} />
                      </div>
                    )}
                  </ChartCard>
                </Col>
              </Row>
            </Spin>
          ),
        },
      ]}
    />
  )
}
