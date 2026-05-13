import { Row, Col, Table, Tag, Progress, Spin } from 'antd'
import { Line } from '@ant-design/charts'
import { useRef, useEffect } from 'react'
import {
  PlusCircleOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  RiseOutlined,
  SyncOutlined,
} from '@ant-design/icons'

interface RiskDimensionItem {
  name: string
  red_count: number
  yellow_count: number
  green_count: number
  total_count: number
}

interface ClosureAchievementData {
  new_issues: number
  closed_issues: number
  overdue_issues: number
  escalated_issues: number
  repeated_issues: number
  closure_rate: number
  on_time_rate: number
  by_type: RiskDimensionItem[]
  by_owner: RiskDimensionItem[]
  trend: Array<{ date: string; new: number; closed: number }>
}

interface ClosureAchievementProps {
  data: ClosureAchievementData | null
  loading: boolean
}

const ISSUE_TYPE_LABELS: Record<string, string> = {
  delivery_delay: '交期延期',
  shortage: '欠料风险',
  eta_delay: 'ETA延期',
  process_lag: '工序滞后',
  quality: '品质异常',
  inspection_ng: '客检NG',
  holiday_risk: '假期风险',
  long_lead: '长周期物料',
}

function KpiCard({ icon, label, value, color, sub }: {
  icon: React.ReactNode; label: string; value: number | string; color: string; sub?: string
}) {
  return (
    <div className="card-modern" style={{ padding: '18px 20px', height: '100%' }}>
      <div className="flex items-center justify-between" style={{ marginBottom: 8 }}>
        <span style={{ fontSize: 13, fontWeight: 500, color: '#475569' }}>{label}</span>
        <span style={{ color, fontSize: 18 }}>{icon}</span>
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, color }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

const typeColumns = [
  { title: '异常类型', dataIndex: 'name', key: 'name', width: 140, ellipsis: true, render: (name: string) => ISSUE_TYPE_LABELS[name] || name },
  { title: '总数', dataIndex: 'total_count', key: 'total_count', width: 70 },
  {
    title: '高风险', dataIndex: 'red_count', key: 'red_count', width: 80,
    render: (v: number) => v > 0 ? <Tag color="red">{v}</Tag> : <span style={{ color: '#94a3b8' }}>0</span>,
  },
  {
    title: '中风险', dataIndex: 'yellow_count', key: 'yellow_count', width: 80,
    render: (v: number) => v > 0 ? <Tag color="orange">{v}</Tag> : <span style={{ color: '#94a3b8' }}>0</span>,
  },
]

const ownerColumns = [
  { title: '责任人', dataIndex: 'name', key: 'name', width: 120 },
  { title: '总数', dataIndex: 'total_count', key: 'total_count', width: 70 },
  {
    title: '高风险', dataIndex: 'red_count', key: 'red_count', width: 80,
    render: (v: number) => v > 0 ? <Tag color="red">{v}</Tag> : <span style={{ color: '#94a3b8' }}>0</span>,
  },
  {
    title: '中风险', dataIndex: 'yellow_count', key: 'yellow_count', width: 80,
    render: (v: number) => v > 0 ? <Tag color="orange">{v}</Tag> : <span style={{ color: '#94a3b8' }}>0</span>,
  },
]

export default function ClosureAchievement({ data, loading }: ClosureAchievementProps) {
  const lineChartRef = useRef<any>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      requestAnimationFrame(() => {
        lineChartRef.current?.resize()
      })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  if (loading || !data) return <Spin />

  const closurePct = Math.round(data.closure_rate * 100)
  const onTimePct = Math.round(data.on_time_rate * 100)

  // 趋势图数据
  const trendData: Array<{ date: string; type: string; value: number }> = []
  data.trend.forEach(t => {
    trendData.push({ date: t.date.slice(5), type: '新增', value: t.new })
    trendData.push({ date: t.date.slice(5), type: '关闭', value: t.closed })
  })

  const trendConfig = {
    data: trendData,
    xField: 'date',
    yField: 'value',
    colorField: 'type',
    color: ['#e11d48', '#10b981'],
    smooth: true,
    point: { shapeField: 'square', sizeField: 4 },
    axis: {
      x: { title: false, label: { style: { fontSize: 10 } } },
      y: { title: false, label: { style: { fontSize: 10 } } },
    },
    legend: { color: { position: 'top' as const } },
    height: 220,
  }

  return (
    <div ref={containerRef}>
      {/* 核心指标 */}
      <Row gutter={[14, 14]} style={{ marginBottom: 18 }}>
        <Col xs={12} sm={8} lg={4}>
          <KpiCard icon={<PlusCircleOutlined />} label="新增异常(7天)" value={data.new_issues} color="#6366f1" />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <KpiCard icon={<CheckCircleOutlined />} label="已关闭(7天)" value={data.closed_issues} color="#10b981" />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <KpiCard icon={<ClockCircleOutlined />} label="逾期异常" value={data.overdue_issues} color="#e11d48" />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <KpiCard icon={<RiseOutlined />} label="升级异常" value={data.escalated_issues} color="#f59e0b" />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <KpiCard icon={<SyncOutlined />} label="重复异常" value={data.repeated_issues} color="#8b5cf6" />
        </Col>
        <Col xs={12} sm={8} lg={4}>
          <div className="card-modern" style={{ padding: '18px 20px', height: '100%' }}>
            <div style={{ fontSize: 13, fontWeight: 500, color: '#475569', marginBottom: 10 }}>闭环率 / 按时率</div>
            <div style={{ marginBottom: 8 }}>
              <div className="flex items-center justify-between" style={{ marginBottom: 4 }}>
                <span style={{ fontSize: 12, color: '#64748b' }}>闭环率</span>
                <span style={{ fontSize: 16, fontWeight: 700, color: closurePct >= 80 ? '#10b981' : closurePct >= 50 ? '#f59e0b' : '#e11d48' }}>{closurePct}%</span>
              </div>
              <Progress percent={closurePct} showInfo={false} strokeColor={closurePct >= 80 ? '#10b981' : closurePct >= 50 ? '#f59e0b' : '#e11d48'} size="small" />
            </div>
            <div>
              <div className="flex items-center justify-between" style={{ marginBottom: 4 }}>
                <span style={{ fontSize: 12, color: '#64748b' }}>按时率</span>
                <span style={{ fontSize: 16, fontWeight: 700, color: onTimePct >= 80 ? '#10b981' : onTimePct >= 50 ? '#f59e0b' : '#e11d48' }}>{onTimePct}%</span>
              </div>
              <Progress percent={onTimePct} showInfo={false} strokeColor={onTimePct >= 80 ? '#10b981' : onTimePct >= 50 ? '#f59e0b' : '#e11d48'} size="small" />
            </div>
          </div>
        </Col>
      </Row>

      <Row gutter={[14, 14]} style={{ marginBottom: 18 }}>
        {/* 趋势图 */}
        <Col xs={24} lg={12}>
          <div className="card-modern" style={{ padding: '20px 24px', height: '100%' }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600, color: '#475569' }}>近7天异常趋势</h3>
            {trendData.length > 0 ? (
              <Line {...trendConfig} onReady={(chart: any) => { lineChartRef.current = chart }} />
            ) : (
              <div style={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#94a3b8' }}>暂无趋势数据</div>
            )}
          </div>
        </Col>

        {/* 按类型分布 */}
        <Col xs={24} lg={12}>
          <div className="card-modern" style={{ padding: '20px 24px', height: '100%' }}>
            <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600, color: '#475569' }}>按异常类型分布</h3>
            <Table
              columns={typeColumns}
              dataSource={data.by_type}
              rowKey="name"
              size="small"
              pagination={false}
              scroll={{ y: 200 }}
              locale={{ emptyText: '暂无数据' }}
            />
          </div>
        </Col>
      </Row>

      {/* 按责任人分布 */}
      <div className="card-modern" style={{ padding: '2px 0 0' }}>
        <div style={{ padding: '16px 20px 8px' }}>
          <h3 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: '#475569' }}>按责任人分布</h3>
        </div>
        <div className="table-modern">
          <Table
            columns={ownerColumns}
            dataSource={data.by_owner}
            rowKey="name"
            size="middle"
            scroll={{ y: 'calc(100vh - 680px)' }}
            locale={{ emptyText: '暂无数据' }}
            pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条`, style: { padding: '0 16px' } }}
          />
        </div>
      </div>
    </div>
  )
}
