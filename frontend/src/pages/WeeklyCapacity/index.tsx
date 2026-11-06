import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Card,
  Col,
  Empty,
  Input,
  Row,
  Segmented,
  Spin,
  Statistic,
  Table,
  Tag,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useSearchParams } from 'react-router-dom'
import { monthlyCapacityPlanApi } from '../../services/monthlyCapacityPlan'

interface WeekRow {
  order_no: string
  line_no: string
  product_code?: string
  product_name?: string
  bom_no?: string
  stage: string
  stage_label: string
  quantity: number
  manpower: number
  daily_work_hours: number
  hours: number
  status: string
  remark?: string
  continued_from_prev_week: boolean
}

interface WeekDay {
  date: string
  weekday: string
  order_count: number
  line_count: number
  total_qty: number
  rows: WeekRow[]
}

interface WeekData {
  week_start: string
  week_end: string
  generated_at: string
  has_plan: boolean
  summary: {
    order_count: number
    line_count: number
    total_qty: number
    stage_hours: Record<string, number>
  }
  days: WeekDay[]
}

const STAGE_OPTIONS = [
  { label: '全部', value: 'all' },
  { label: '组装', value: 'assembly' },
  { label: '包装', value: 'packaging' },
]

function formatNumber(value?: number | null) {
  return Number(value || 0).toLocaleString('zh-CN')
}

function statusTag(status: string) {
  if (status === 'risk') return <Tag color="red">超负荷</Tag>
  if (status === 'warn') return <Tag color="orange">注意</Tag>
  return <Tag color="green">正常</Tag>
}

export default function WeeklyCapacity() {
  const [searchParams] = useSearchParams()
  const weekStart = searchParams.get('week_start') || undefined
  const [data, setData] = useState<WeekData | null>(null)
  const [loading, setLoading] = useState(false)
  const [selectedDate, setSelectedDate] = useState('')
  const [stage, setStage] = useState('all')
  const [keyword, setKeyword] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await monthlyCapacityPlanApi.getWeeklyCapacity({
        week_start: weekStart,
      })
      setData(res.data || null)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [weekStart])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    if (!data?.days?.length) return
    if (!data.days.some((day) => day.date === selectedDate)) {
      const firstWithRows = data.days.find((day) => day.rows.length > 0)
      setSelectedDate(firstWithRows?.date || data.days[0].date)
    }
  }, [data, selectedDate])

  const selectedDay = data?.days.find((day) => day.date === selectedDate)
  const maxDayQty = useMemo(
    () => Math.max(1, ...(data?.days || []).map((day) => day.total_qty)),
    [data],
  )

  const filteredRows = useMemo(() => {
    const rows = selectedDay?.rows || []
    const lowered = keyword.trim().toLowerCase()
    return rows.filter((row) => {
      if (stage !== 'all' && row.stage !== stage) return false
      if (!lowered) return true
      return [row.order_no, row.product_code, row.product_name, row.bom_no]
        .join(' ')
        .toLowerCase()
        .includes(lowered)
    })
  }, [selectedDay, stage, keyword])

  const columns: ColumnsType<WeekRow> = [
    { title: '日期', width: 90, render: () => selectedDay?.date.slice(5) || '-' },
    { title: '订单号', dataIndex: 'order_no', width: 170 },
    { title: '行号', dataIndex: 'line_no', width: 60 },
    { title: '产品编码', dataIndex: 'product_code', width: 170, ellipsis: true },
    { title: '产品名称', dataIndex: 'product_name', width: 200, ellipsis: true },
    { title: 'BOM', dataIndex: 'bom_no', width: 180, ellipsis: true },
    {
      title: '工序',
      dataIndex: 'stage_label',
      width: 70,
      render: (value: string) => (
        <Tag color={value === '组装' ? 'blue' : 'green'}>{value}</Tag>
      ),
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      width: 80,
      align: 'right',
      render: (value: number) => formatNumber(value),
    },
    { title: '人数', dataIndex: 'manpower', width: 60, align: 'right' },
    {
      title: '日工时',
      dataIndex: 'daily_work_hours',
      width: 80,
      align: 'right',
      render: (value: number) => `${value}h`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value: string, row) => (
        <span>
          {statusTag(value)}
          {row.continued_from_prev_week && <Tag>延续</Tag>}
        </span>
      ),
    },
    { title: '备注', dataIndex: 'remark', width: 160, render: (value?: string) => value || '-' },
  ]

  if (loading && !data) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 80 }}>
        <Spin size="large" tip="加载下周产能计划..." />
      </div>
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: '#f3f5f8', padding: 12 }}>
      <div style={{ maxWidth: 1440, margin: '0 auto' }}>
        <Card
          title="下周产能计划"
          extra={<Tag color="blue">只读</Tag>}
          styles={{ body: { padding: 16 } }}
        >
          {data ? (
            <>
              <div style={{ color: '#595959', marginBottom: 12 }}>
                周期 <b>{data.week_start}</b> ~ <b>{data.week_end}</b>
                <span style={{ marginLeft: 12, color: '#8c8c8c' }}>
                  生成时间 {data.generated_at?.replace('T', ' ')}
                </span>
              </div>

              {!data.has_plan && (
                <Alert
                  type="warning"
                  showIcon
                  message="下周暂无排产计划"
                  description="请先在「新排产方案」中生成并激活下周计划后再推送。"
                  style={{ marginBottom: 12 }}
                />
              )}

              <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
                <Col xs={12} md={4}>
                  <Statistic title="订单数" value={data.summary.order_count} />
                </Col>
                <Col xs={12} md={4}>
                  <Statistic title="订单行数" value={data.summary.line_count} />
                </Col>
                <Col xs={12} md={4}>
                  <Statistic
                    title="总数量"
                    value={data.summary.total_qty}
                    formatter={(value) => formatNumber(Number(value))}
                  />
                </Col>
                <Col xs={12} md={4}>
                  <Statistic
                    title="组装人时"
                    value={data.summary.stage_hours.assembly || 0}
                    precision={1}
                  />
                </Col>
                <Col xs={12} md={4}>
                  <Statistic
                    title="包装人时"
                    value={data.summary.stage_hours.packaging || 0}
                    precision={1}
                  />
                </Col>
              </Row>

              <div style={{ fontWeight: 600, marginBottom: 8 }}>每日排产负荷</div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
                  gap: 8,
                  marginBottom: 16,
                }}
              >
                {data.days.map((day) => {
                  const active = day.date === selectedDate
                  const pct = day.total_qty > 0
                    ? Math.max(3, Math.round((day.total_qty / maxDayQty) * 100))
                    : 0
                  return (
                    <button
                      key={day.date}
                      type="button"
                      onClick={() => setSelectedDate(day.date)}
                      style={{
                        textAlign: 'left',
                        border: `1px solid ${active ? '#1677ff' : '#e8e8e8'}`,
                        background: active ? '#f0f7ff' : '#fff',
                        borderRadius: 4,
                        padding: '8px 9px',
                        cursor: 'pointer',
                      }}
                    >
                      <div style={{ color: '#8c8c8c', fontSize: 11 }}>{day.weekday}</div>
                      <div style={{ fontWeight: 700, fontSize: 13 }}>{day.date.slice(5)}</div>
                      <div style={{ height: 4, background: '#f0f0f0', borderRadius: 2, margin: '7px 0 5px' }}>
                        <div style={{ width: `${pct}%`, height: '100%', background: '#1677ff', borderRadius: 2 }} />
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between', color: '#8c8c8c', fontSize: 10 }}>
                        <span>{formatNumber(day.total_qty)} 件</span>
                        <span>{day.line_count} 行</span>
                      </div>
                    </button>
                  )
                })}
              </div>

              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 12,
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  marginBottom: 10,
                }}
              >
                <Segmented
                  options={STAGE_OPTIONS}
                  value={stage}
                  onChange={(value) => setStage(String(value))}
                />
                <Input.Search
                  allowClear
                  placeholder="订单号 / 产品 / BOM"
                  style={{ width: 260, maxWidth: '100%' }}
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                />
              </div>

              <div style={{ color: '#8c8c8c', fontSize: 12, marginBottom: 8 }}>
                <b>{selectedDay?.date || '-'}</b>
                {selectedDay ? ` ${selectedDay.weekday}` : ''}
                <span style={{ marginLeft: 10 }}>当日订单 {selectedDay?.order_count || 0} 个</span>
                <span style={{ marginLeft: 10 }}>明细 {selectedDay?.line_count || 0} 行</span>
                <span style={{ marginLeft: 10 }}>数量 {formatNumber(selectedDay?.total_qty)} 件</span>
                <span style={{ marginLeft: 10 }}>当前筛选 {filteredRows.length} 行</span>
              </div>

              <Table<WeekRow>
                rowKey={(row) => `${row.order_no}-${row.line_no}-${row.stage}`}
                size="small"
                bordered
                columns={columns}
                dataSource={filteredRows}
                pagination={{ pageSize: 50, showSizeChanger: false }}
                scroll={{ x: 1320 }}
                locale={{ emptyText: <Empty description="当日无排产" /> }}
              />
            </>
          ) : (
            <Empty description="暂无下周产能数据" />
          )}
        </Card>
      </div>
    </div>
  )
}
