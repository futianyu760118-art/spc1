import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Drawer,
  Input,
  InputNumber,
  Radio,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tag,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useNavigate } from 'react-router-dom'
import dayjs from 'dayjs'
import { monthlyCapacityPlanApi } from '../../../services/monthlyCapacityPlan'

interface StageSummary {
  stage: string
  label: string
  workdays: number
  daily_hours: number
  manpower: number
  demand_hours: number
  available_hours: number
  utilization: number | null
  gap: number
  surplus: number
  required_days_85: number | null
  required_days_12: number | null
}

interface OrderRow {
  order_no: string
  line_no: string
  product_code?: string
  product_name?: string
  bom_no?: string
  shipping_plan?: string
  quantity: number
  status?: string
  schedule_bucket?: string
  assembly_price: number
  packaging_price: number
  assembly_hours: number
  packaging_hours: number
  total_hours: number
  has_schedule: boolean
}

interface OrderMasterRow {
  order_no: string
  line_count: number
  total_quantity: number
  shipping_plan_start?: string
  shipping_plan_end?: string
  assembly_hours: number
  packaging_hours: number
  total_hours: number
  scheduled_count: number
  lines: OrderRow[]
}

interface MissingRow {
  order_no: string
  line_no: string
  bom_no?: string
  reason: string
}

interface PlanData {
  year: number
  month: number
  month_label: string
  params?: {
    workdays?: number
    workdays_requested?: number
    daily_hours?: number
    assembly_manpower?: number
    packaging_manpower?: number
    include_sunday?: boolean
    include_scheduled?: boolean
  }
  summary: {
    order_count: number
    total_quantity: number
    demand_hours: number
    available_hours: number
    utilization: number | null
    gap: number
    surplus: number
    required_days_85: number
    required_days_12: number
  }
  stages: StageSummary[]
  orders: OrderRow[]
  missing: MissingRow[]
}

const STAGE_OPTIONS = [
  { value: 'all', label: '全部阶段' },
  { value: 'assembly', label: '组装' },
  { value: 'packaging', label: '包装' },
]

function num(value?: number | null, digits = 2) {
  if (value === null || value === undefined) return '-'
  return Number(value).toFixed(digits)
}

function csvEscape(value: unknown) {
  const text = String(value ?? '')
  return `"${text.replace(/"/g, '""')}"`
}

const SCENARIO_SETTINGS_KEY = 'monthly_capacity_plan_scenario_v1'

interface SavedScenarioSettings {
  workdays?: number
  dailyHours?: number
  assemblyManpower?: number
  packagingManpower?: number
  includeSunday?: boolean
  includeScheduled?: boolean
}

function loadSavedScenarioSettings(): SavedScenarioSettings {
  try {
    const raw = localStorage.getItem(SCENARIO_SETTINGS_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

export default function MonthlyCapacityPlan() {
  const navigate = useNavigate()
  const now = dayjs()
  const savedScenario = useMemo(loadSavedScenarioSettings, [])
  const [year, setYear] = useState(now.year())
  const [month, setMonth] = useState(now.month() + 1)
  const [stage, setStage] = useState('all')
  const [workdays, setWorkdays] = useState(savedScenario.workdays ?? 26)
  const [dailyHours, setDailyHours] = useState(savedScenario.dailyHours ?? 12)
  const [assemblyManpower, setAssemblyManpower] = useState(savedScenario.assemblyManpower ?? 12)
  const [packagingManpower, setPackagingManpower] = useState(savedScenario.packagingManpower ?? 9)
  const [includeSunday, setIncludeSunday] = useState(savedScenario.includeSunday ?? false)
  const [includeScheduled, setIncludeScheduled] = useState(savedScenario.includeScheduled ?? true)
  const [scenarioReady, setScenarioReady] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [data, setData] = useState<PlanData | null>(null)
  const [preview, setPreview] = useState<any>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [aiLoading, setAiLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [orderDrawerOpen, setOrderDrawerOpen] = useState(false)

  useEffect(() => {
    try {
      localStorage.setItem(
        SCENARIO_SETTINGS_KEY,
        JSON.stringify({
          workdays,
          dailyHours,
          assemblyManpower,
          packagingManpower,
          includeSunday,
          includeScheduled,
        }),
      )
    } catch {
      // localStorage 不可用时忽略
    }
  }, [
    assemblyManpower,
    dailyHours,
    includeSunday,
    includeScheduled,
    packagingManpower,
    workdays,
  ])

  useEffect(() => {
    let active = true
    monthlyCapacityPlanApi
      .getScenario()
      .then((res: any) => {
        if (!active) return
        const scenario = res.data || {}
        if (typeof scenario.workdays === 'number') setWorkdays(scenario.workdays)
        if (typeof scenario.daily_hours === 'number') setDailyHours(scenario.daily_hours)
        if (typeof scenario.assembly_manpower === 'number') setAssemblyManpower(scenario.assembly_manpower)
        if (typeof scenario.packaging_manpower === 'number') setPackagingManpower(scenario.packaging_manpower)
        if (typeof scenario.include_sunday === 'boolean') setIncludeSunday(scenario.include_sunday)
        if (typeof scenario.include_scheduled === 'boolean') setIncludeScheduled(scenario.include_scheduled)
      })
      .catch(() => {
        // 后端暂不可用时继续使用本地缓存
      })
      .finally(() => {
        if (active) setScenarioReady(true)
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!scenarioReady) return
    const timer = window.setTimeout(() => {
      monthlyCapacityPlanApi
        .saveScenario({
          workdays,
          daily_hours: dailyHours,
          assembly_manpower: assemblyManpower,
          packaging_manpower: packagingManpower,
          include_sunday: includeSunday,
          include_scheduled: includeScheduled,
        })
        .catch(() => {
          // 保存失败不打断当前操作
        })
    }, 600)
    return () => window.clearTimeout(timer)
  }, [
    assemblyManpower,
    dailyHours,
    includeSunday,
    includeScheduled,
    packagingManpower,
    scenarioReady,
    workdays,
  ])

  const load = useCallback(async () => {
    setLoading(true)
    setPreview(null)
    try {
      const res: any = await monthlyCapacityPlanApi.getMonthlyCapacityPlan({
        year,
        month,
        stage,
        workdays,
        daily_hours: dailyHours,
        assembly_manpower: assemblyManpower,
        packaging_manpower: packagingManpower,
        include_sunday: includeSunday,
        include_scheduled: includeScheduled,
        keyword: keyword.trim() || undefined,
      })
      setData(res.data || null)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [
    assemblyManpower,
    dailyHours,
    includeSunday,
    includeScheduled,
    keyword,
    month,
    packagingManpower,
    stage,
    workdays,
    year,
  ])

  useEffect(() => {
    // 条件变化只清空旧结果，不自动请求；统一由“重新计算”按钮触发
    setData(null)
    setPreview(null)
  }, [year, month, stage, includeSunday, includeScheduled, keyword])

  const generatePreview = async () => {
    setPreviewLoading(true)
    try {
      const res: any = await monthlyCapacityPlanApi.getAllocationPreview({
        year,
        month,
        stage,
        workdays,
        daily_hours: dailyHours,
        assembly_manpower: assemblyManpower,
        packaging_manpower: packagingManpower,
        include_sunday: includeSunday,
        include_scheduled: includeScheduled,
        keyword: keyword.trim() || undefined,
      })
      setPreview(res.data || null)
    } catch {
      setPreview(null)
    } finally {
      setPreviewLoading(false)
    }
  }

  const generateAiPreview = async () => {
    setAiLoading(true)
    try {
      const res: any = await monthlyCapacityPlanApi.getAiAllocationPreview({
        year,
        month,
        stage,
        workdays,
        daily_hours: dailyHours,
        assembly_manpower: assemblyManpower,
        packaging_manpower: packagingManpower,
        include_sunday: includeSunday,
        include_scheduled: includeScheduled,
        keyword: keyword.trim() || undefined,
      })
      setPreview(res.data || null)
    } catch {
      setPreview(null)
    } finally {
      setAiLoading(false)
    }
  }

  const showGenerateResult = (result: any, label: string) => {
    if (result.unscheduled_count || result.late_count) {
      message.warning(
        `已生成 ${result.created_count ?? 0} 条；未排完 ${result.unscheduled_count ?? 0} 条，延期 ${result.late_count ?? 0} 条`,
        8,
      )
    } else {
      message.success(`已生成${label} ${result.created_count ?? 0} 条`)
    }
    navigate('/engineering/new-schedule/plans')
  }

  const generateSchedule = async () => {
    setGenerating(true)
    try {
      const res: any = await monthlyCapacityPlanApi.generateMonthlyPlans({
        year,
        month,
        workdays,
        daily_hours: dailyHours,
        assembly_manpower: assemblyManpower,
        packaging_manpower: packagingManpower,
        include_sunday: includeSunday,
        include_scheduled: includeScheduled,
      })
      showGenerateResult(res.data || {}, '新排产方案')
    } catch {
      // 全局拦截器提示
    } finally {
      setGenerating(false)
    }
  }

  const generateAiSchedule = async () => {
    const orderSequence = preview?.ai?.order_sequence || []
    if (!orderSequence.length) {
      message.warning('请先生成 AI 排产预览')
      return
    }
    setGenerating(true)
    try {
      const res: any = await monthlyCapacityPlanApi.generateAiMonthlyPlans(
        {
          year,
          month,
          workdays,
          daily_hours: dailyHours,
          assembly_manpower: assemblyManpower,
          packaging_manpower: packagingManpower,
          include_sunday: includeSunday,
          include_scheduled: includeScheduled,
        },
        orderSequence,
      )
      showGenerateResult(res.data || {}, ' AI 排产方案')
    } catch {
      // 全局拦截器提示
    } finally {
      setGenerating(false)
    }
  }

  const summary = data?.summary
  const stages = data?.stages || []
  const orders = data?.orders || []
  const missing = data?.missing || []
  const uniqueOrderCount = new Set(orders.map((item) => item.order_no)).size

  const orderGroups = useMemo<OrderMasterRow[]>(() => {
    const groups = new Map<string, OrderMasterRow>()
    for (const row of orders) {
      let group = groups.get(row.order_no)
      if (!group) {
        group = {
          order_no: row.order_no,
          line_count: 0,
          total_quantity: 0,
          shipping_plan_start: row.shipping_plan,
          shipping_plan_end: row.shipping_plan,
          assembly_hours: 0,
          packaging_hours: 0,
          total_hours: 0,
          scheduled_count: 0,
          lines: [],
        }
        groups.set(row.order_no, group)
      }
      group.line_count += 1
      group.total_quantity += row.quantity
      group.assembly_hours += row.assembly_hours
      group.packaging_hours += row.packaging_hours
      group.total_hours += row.total_hours
      group.scheduled_count += row.has_schedule ? 1 : 0
      group.lines.push(row)
      if (row.shipping_plan) {
        if (!group.shipping_plan_start || row.shipping_plan < group.shipping_plan_start) {
          group.shipping_plan_start = row.shipping_plan
        }
        if (!group.shipping_plan_end || row.shipping_plan > group.shipping_plan_end) {
          group.shipping_plan_end = row.shipping_plan
        }
      }
    }
    return Array.from(groups.values()).sort((a, b) => {
      const left = a.shipping_plan_start || '9999-12-31'
      const right = b.shipping_plan_start || '9999-12-31'
      return left.localeCompare(right) || a.order_no.localeCompare(b.order_no)
    })
  }, [orders])

  const lineColumns: ColumnsType<OrderRow> = [
    { title: '行号', dataIndex: 'line_no', width: 70 },
    { title: '产品编码', dataIndex: 'product_code', width: 180, ellipsis: true },
    { title: 'BOM', dataIndex: 'bom_no', width: 220, ellipsis: true },
    { title: '出货计划', dataIndex: 'shipping_plan', width: 110 },
    {
      title: '数量',
      dataIndex: 'quantity',
      width: 100,
      align: 'right',
      render: (value: number) => num(value, 0),
    },
    {
      title: '组装单价',
      dataIndex: 'assembly_price',
      width: 100,
      align: 'right',
      render: (value: number) => num(value, 4),
    },
    {
      title: '包装单价',
      dataIndex: 'packaging_price',
      width: 100,
      align: 'right',
      render: (value: number) => num(value, 4),
    },
    {
      title: '组装人时',
      dataIndex: 'assembly_hours',
      width: 100,
      align: 'right',
      render: (value: number) => num(value),
    },
    {
      title: '包装人时',
      dataIndex: 'packaging_hours',
      width: 100,
      align: 'right',
      render: (value: number) => num(value),
    },
    {
      title: '合计人时',
      dataIndex: 'total_hours',
      width: 110,
      align: 'right',
      render: (value: number) => num(value),
    },
    {
      title: '排产状态',
      dataIndex: 'has_schedule',
      width: 100,
      render: (value: boolean) => (
        <Tag color={value ? 'green' : 'default'}>{value ? '已排' : '未排'}</Tag>
      ),
    },
  ]

  const masterColumns: ColumnsType<OrderMasterRow> = [
    { title: '订单号', dataIndex: 'order_no', width: 200, fixed: 'left' },
    { title: '行数', dataIndex: 'line_count', width: 70, align: 'right' },
    {
      title: '总数量',
      dataIndex: 'total_quantity',
      width: 100,
      align: 'right',
      render: (value: number) => num(value, 0),
    },
    {
      title: '出货计划',
      width: 190,
      render: (_: unknown, row: OrderMasterRow) => {
        if (!row.shipping_plan_start) return '-'
        if (row.shipping_plan_start === row.shipping_plan_end) return row.shipping_plan_start
        return `${row.shipping_plan_start} ~ ${row.shipping_plan_end}`
      },
    },
    {
      title: '组装人时',
      dataIndex: 'assembly_hours',
      width: 100,
      align: 'right',
      render: (value: number) => num(value),
    },
    {
      title: '包装人时',
      dataIndex: 'packaging_hours',
      width: 100,
      align: 'right',
      render: (value: number) => num(value),
    },
    {
      title: '合计人时',
      dataIndex: 'total_hours',
      width: 110,
      align: 'right',
      render: (value: number) => num(value),
    },
    {
      title: '排产状态',
      width: 100,
      render: (_: unknown, row: OrderMasterRow) => {
        if (row.scheduled_count === 0) return <Tag>未排</Tag>
        if (row.scheduled_count === row.line_count) return <Tag color="green">已排</Tag>
        return <Tag color="orange">部分已排</Tag>
      },
    },
  ]

  const renderOrderTable = () => (
    <Table<OrderMasterRow>
      rowKey="order_no"
      size="small"
      bordered
      loading={loading}
      columns={masterColumns}
      dataSource={orderGroups}
      scroll={{ x: 1200 }}
      expandable={{
        expandedRowRender: (record) => (
          <Table<OrderRow>
            rowKey={(line) => `${line.order_no}-${line.line_no}`}
            size="small"
            bordered
            pagination={false}
            columns={lineColumns}
            dataSource={record.lines}
            scroll={{ x: 1450 }}
          />
        ),
      }}
      pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (value) => `共 ${value} 单` }}
    />
  )

  const missingColumns: ColumnsType<MissingRow> = [
    { title: '订单号', dataIndex: 'order_no', width: 200 },
    { title: '行号', dataIndex: 'line_no', width: 80 },
    { title: 'BOM', dataIndex: 'bom_no', width: 240, ellipsis: true, render: (value?: string) => value || '-' },
    { title: '原因', dataIndex: 'reason' },
  ]

  const stageCards = useMemo(
    () =>
      stages.map((item) => (
        <Col xs={24} md={8} key={item.stage}>
          <Card size="small" title={`${item.label}（${item.stage}）`}>
            <Row gutter={12}>
              <Col span={12}>
                <Statistic title="需求人时" value={item.demand_hours} precision={2} />
              </Col>
              <Col span={12}>
                <Statistic title="可用人时" value={item.available_hours} precision={2} />
              </Col>
              <Col span={12}>
                <Statistic
                  title="利用率"
                  value={item.utilization ?? '-'}
                  suffix={item.utilization === null ? '' : '%'}
                  precision={item.utilization === null ? undefined : 2}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title={item.gap >= 0 ? '缺口' : '富余'}
                  value={Math.abs(item.gap)}
                  precision={2}
                  valueStyle={{ color: item.gap > 0 ? '#cf1322' : '#3f8600' }}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="8.5h 需要天数"
                  value={item.required_days_85 ?? '-'}
                  precision={2}
                />
              </Col>
              <Col span={12}>
                <Statistic
                  title="12h 需要天数"
                  value={item.required_days_12 ?? '-'}
                  precision={2}
                />
              </Col>
            </Row>
            <div style={{ marginTop: 10, color: '#8c8c8c', fontSize: 12 }}>
              可用 = {item.workdays} 天 × {item.daily_hours}h × {item.manpower} 人 ={' '}
              {num(item.available_hours)} 人时
            </div>
            <div style={{ color: '#8c8c8c', fontSize: 12 }}>
              需求 = Σ 数量 × 阶段单价 ÷ 小时单价
            </div>
          </Card>
        </Col>
      )),
    [stages],
  )

  const lateMap = useMemo(() => {
    const map = new Map<string, any>()
    for (const item of preview?.late || []) {
      map.set(`${item.order_no}-${item.line_no}-${item.stage}`, item)
    }
    return map
  }, [preview])

  const previewColumns: ColumnsType<any> = [
    { title: '日期', dataIndex: 'date', width: 110 },
    { title: '阶段', dataIndex: 'stage_label', width: 80 },
    { title: '订单号', dataIndex: 'order_no', width: 180 },
    { title: '行号', dataIndex: 'line_no', width: 70 },
    { title: '产品编码', dataIndex: 'product_code', width: 180, ellipsis: true },
    { title: '出货计划', dataIndex: 'shipping_plan', width: 110 },
    {
      title: '当天数量',
      dataIndex: 'quantity',
      width: 100,
      align: 'right',
      render: (value: number) => num(value, 0),
    },
    {
      title: '当天工时',
      dataIndex: 'hours',
      width: 100,
      align: 'right',
      render: (value: number) => num(value),
    },
    {
      title: '当天容量',
      dataIndex: 'daily_capacity',
      width: 100,
      align: 'right',
      render: (value: number) => num(value),
    },
    {
      title: '状态',
      width: 100,
      render: (_: unknown, row: any) => {
        const late = lateMap.get(`${row.order_no}-${row.line_no}-${row.stage}`)
        return late ? <Tag color="red">延期 {late.late_days} 天</Tag> : <Tag color="green">正常</Tag>
      },
    },
  ]

  const exportCsv = () => {
    if (!data) return
    const header = [
      '订单号',
      '行号',
      '产品编码',
      'BOM',
      '出货计划',
      '数量',
      '组装单价',
      '包装单价',
      '组装人时',
      '包装人时',
      '合计人时',
      '排产状态',
    ]
    const lines = orders.map((row) =>
      [
        row.order_no,
        row.line_no,
        row.product_code,
        row.bom_no,
        row.shipping_plan,
        row.quantity,
        row.assembly_price,
        row.packaging_price,
        row.assembly_hours,
        row.packaging_hours,
        row.total_hours,
        row.has_schedule ? '已排' : '未排',
      ]
        .map(csvEscape)
        .join(','),
    )
    const blob = new Blob([`\ufeff${[header.map(csvEscape).join(','), ...lines].join('\n')}`], {
      type: 'text/csv;charset=utf-8',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `月度产能规划_${data.month_label}.csv`
    link.click()
    URL.revokeObjectURL(url)
    message.success('已导出')
  }

  return (
    <div style={{ padding: 16 }}>
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Card
          title="月度产能规划"
          extra={
            <Space>
              <Button onClick={generateAiPreview} loading={aiLoading}>
                AI 排产
              </Button>
              <Button type="primary" onClick={generatePreview} loading={previewLoading}>
                生成每日预览
              </Button>
              <Button onClick={generateSchedule} loading={generating}>
                生成排产方案
              </Button>
              <Button onClick={load} loading={loading}>
                重新计算
              </Button>
              <Button onClick={exportCsv} disabled={!data}>
                导出 CSV
              </Button>
            </Space>
          }
        >
          <Space wrap size={16}>
            <span>
              年份
              <Select
                style={{ width: 100, marginLeft: 8 }}
                value={year}
                onChange={setYear}
                options={Array.from({ length: 5 }, (_, index) => {
                  const value = now.year() - 1 + index
                  return { value, label: `${value}年` }
                })}
              />
            </span>
            <span>
              月份
              <Select
                style={{ width: 100, marginLeft: 8 }}
                value={month}
                onChange={setMonth}
                options={Array.from({ length: 12 }, (_, index) => ({
                  value: index + 1,
                  label: `${index + 1}月`,
                }))}
              />
            </span>
            <span>
              阶段
              <Select
                style={{ width: 130, marginLeft: 8 }}
                value={stage}
                onChange={setStage}
                options={STAGE_OPTIONS}
              />
            </span>
            <span>
              工作天数
              <InputNumber
                min={1}
                max={31}
                value={workdays}
                onChange={(value) => setWorkdays(Number(value || 1))}
                style={{ width: 90, marginLeft: 8 }}
              />
            </span>
            <span>
              日工时
              <Radio.Group
                value={dailyHours}
                onChange={(event) => setDailyHours(Number(event.target.value))}
                style={{ marginLeft: 8 }}
                options={[
                  { label: '8.5h', value: 8.5 },
                  { label: '12h', value: 12 },
                ]}
                optionType="button"
              />
            </span>
            <span>
              组装人数
              <InputNumber
                min={1}
                max={500}
                value={assemblyManpower}
                onChange={(value) => setAssemblyManpower(Number(value || 1))}
                style={{ width: 90, marginLeft: 8 }}
              />
            </span>
            <span>
              包装人数
              <InputNumber
                min={1}
                max={500}
                value={packagingManpower}
                onChange={(value) => setPackagingManpower(Number(value || 1))}
                style={{ width: 90, marginLeft: 8 }}
              />
            </span>
            <span>
              周日生产/加班
              <Switch
                checked={includeSunday}
                onChange={setIncludeSunday}
                style={{ marginLeft: 8 }}
              />
            </span>
            <Checkbox
              checked={includeScheduled}
              onChange={(event) => setIncludeScheduled(event.target.checked)}
            >
              包含已排产
            </Checkbox>
            <Input.Search
              allowClear
              placeholder="订单号 / 产品 / BOM"
              style={{ width: 260 }}
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onSearch={load}
            />
          </Space>
        </Card>

        <Alert
          type="info"
          showIcon
          message="只读预算：统计出货计划在所选月份的订单，不写排产计划、不修改基础条件。"
          description={
            `组装、包装分别计算；已按订单池规则排除 Y 开头 BOM、P- 样品行和 HJY 样品单。` +
            `本月实际可用工作日：${data?.params?.workdays ?? '-'} 天（填写 ${data?.params?.workdays_requested ?? workdays} 天）。` +
            `开启“周日生产/加班”后，周日会按人工确认计入可用产能。` +
            `缺 BOM、缺工价/产能的订单会进入数据缺失清单。人数、工时、工作天数会自动记住，刷新后保留；修改后点“重新计算”。`
          }
        />

        {summary && (
          <Card>
            <Row gutter={[16, 16]}>
              <Col xs={12} md={4}>
                <Statistic title="订单行数 / 订单数" value={`${summary.order_count} / ${uniqueOrderCount}`} />
                <Button type="link" size="small" onClick={() => setOrderDrawerOpen(true)}>
                  查看订单明细
                </Button>
              </Col>
              <Col xs={12} md={4}>
                <Statistic title="总数量" value={summary.total_quantity} precision={0} />
              </Col>
              <Col xs={12} md={4}>
                <Statistic title="需求人时" value={summary.demand_hours} precision={2} />
              </Col>
              <Col xs={12} md={4}>
                <Statistic title="可用人时" value={summary.available_hours} precision={2} />
              </Col>
              <Col xs={12} md={4}>
                <Statistic
                  title="利用率"
                  value={summary.utilization ?? '-'}
                  suffix={summary.utilization === null ? '' : '%'}
                  precision={summary.utilization === null ? undefined : 2}
                />
              </Col>
              <Col xs={12} md={4}>
                <Statistic
                  title={summary.gap >= 0 ? '缺口' : '富余'}
                  value={Math.abs(summary.gap)}
                  precision={2}
                  valueStyle={{ color: summary.gap > 0 ? '#cf1322' : '#3f8600' }}
                />
              </Col>
              <Col xs={12} md={4}>
                <Statistic title="8.5h 需要天数" value={summary.required_days_85} precision={2} />
              </Col>
              <Col xs={12} md={4}>
                <Statistic title="12h 需要天数" value={summary.required_days_12} precision={2} />
              </Col>
            </Row>
            <div style={{ marginTop: 12, color: '#595959', fontSize: 12, lineHeight: 1.8 }}>
              <div>
                可用人时 = {data?.params?.workdays ?? '-'} 天 × {data?.params?.daily_hours ?? '-'}h ×
                （{stages.map((item) => `${item.manpower}人`).join(' + ') || '-'}）=
                <strong> {num(summary.available_hours)} 人时</strong>
              </div>
              <div>
                需求人时 = Σ（数量 × 阶段单价合计 ÷ 小时单价）=
                <strong> {num(summary.demand_hours)} 人时</strong>
              </div>
              <div>
                利用率 = 需求人时 ÷ 可用人时 = {num(summary.demand_hours)} ÷{' '}
                {num(summary.available_hours)} =
                <strong> {summary.utilization ?? '-'}%</strong>
              </div>
              <div>
                需要天数 = 需求人时 ÷（人数 × 日工时）；8.5h 和 12h 分别计算，取各阶段最大值。
              </div>
            </div>
          </Card>
        )}

        <Row gutter={[16, 16]}>{stageCards}</Row>

        {preview && (
          <Card title={preview.ai ? 'AI 每日分配预览' : '每日分配预览'} size="small">
            <Space direction="vertical" size={12} style={{ width: '100%' }}>
              {preview.ai && (
                <Alert
                  type="info"
                  showIcon
                  message={`AI 排产建议（${preview.ai.provider}）`}
                  description={
                    `${preview.ai.summary || ''}` +
                    (preview.ai.risks?.length ? ` 风险：${preview.ai.risks.join('；')}` : '') +
                    (preview.ai.appended_count
                      ? ` 有 ${preview.ai.appended_count} 行未包含在 AI 顺序中，已按交期补到末尾。`
                      : '')
                  }
                  action={
                    <Button type="primary" size="small" loading={generating} onClick={generateAiSchedule}>
                      确认生成 AI 批次
                    </Button>
                  }
                />
              )}
              <Alert
                type={preview.late?.length || preview.unscheduled?.length ? 'warning' : 'success'}
                showIcon
                message={
                  `预览工作日 ${preview.workdays} 天，分配 ${preview.allocations?.length || 0} 条，延期 ${preview.late?.length || 0} 条，未排 ${preview.unscheduled?.length || 0} 条` +
                  (preview.overflow_days ? `；产能不足，已顺延到后续月份 ${preview.overflow_days} 个工作日` : '')
                }
                description="只读预览，不写排产计划；同一订单优先排在同一天，整单放不下才按整数数量拆分；包装在组装完成后的下一个生产日。"
              />
              <Table
                rowKey={(row: any) => `${row.date}-${row.stage}-${row.order_no}-${row.line_no}`}
                size="small"
                bordered
                columns={previewColumns}
                dataSource={preview.allocations || []}
                scroll={{ x: 1200 }}
                pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (value) => `共 ${value} 条` }}
              />
              {!!preview.unscheduled?.length && (
                <Alert
                  type="error"
                  showIcon
                  message="有订单未排完"
                  description={preview.unscheduled
                    .slice(0, 5)
                    .map((item: any) => `${item.order_no}/${item.line_no} ${item.stage} 剩余 ${item.remaining_hours}h`)
                    .join('；')}
                />
              )}
            </Space>
          </Card>
        )}

        <Card title="订单产能明细（主表按订单，展开看行明细）" size="small">
          {renderOrderTable()}
        </Card>

        <Card title={`数据缺失（${missing.length}）`} size="small">
          <Table<MissingRow>
            rowKey={(row) => `${row.order_no}-${row.line_no}-${row.reason}`}
            size="small"
            columns={missingColumns}
            dataSource={missing}
            pagination={false}
            locale={{ emptyText: '没有数据缺失' }}
          />
        </Card>

        <Drawer
          title={`订单明细：${summary?.order_count ?? 0} 行 / ${uniqueOrderCount} 单`}
          width={1200}
          open={orderDrawerOpen}
          onClose={() => setOrderDrawerOpen(false)}
        >
          {renderOrderTable()}
        </Drawer>
      </Space>
    </div>
  )
}
