import { useCallback, useEffect, useState } from 'react'
import type { Key } from 'react'
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { Dayjs } from 'dayjs'
import { useNavigate } from 'react-router-dom'
import { monthlyCapacityPlanApi } from '../../../services/monthlyCapacityPlan'
import { useAuthStore } from '../../../store/auth'
import { textColumnFilter, textFilterIcon } from '../../MaterialCenter/StockCheck/TextColumnFilter'

interface PlanBatch {
  batch_no: string
  schedule_month: string
  is_active: boolean
  row_count: number
  order_count: number
  quantity_total: number
  date_start?: string
  date_end?: string
  created_by?: string
  created_at?: string
}

interface PlanRow {
  id: number
  batch_no?: string
  is_active?: boolean
  order_no: string
  line_no: string
  product_code?: string
  product_name?: string
  bom_no?: string
  schedule_bucket: string
  quantity: number
  source_order_qty?: number
  upph: number
  manpower: number
  daily_work_hours: number
  required_hours?: number
  plan_date?: string
  source_promised_date?: string
  status: string
  warning?: string | null
}

interface Draft {
  date?: Dayjs
  hours?: number
  stage?: string
}

const STAGE_OPTIONS = [
  { value: 'all', label: '全部阶段' },
  { value: 'assembly', label: '组装' },
  { value: 'packaging', label: '包装' },
]

const STAGE_LABEL: Record<string, string> = {
  assembly: '组装',
  packaging: '包装',
}

const STATUS_FILTERS = [
  { text: '正常', value: 'normal' },
  { text: '超工时', value: 'warning' },
]

function textFilterProps(placeholder: string) {
  return {
    filterDropdown: textColumnFilter({ placeholder }),
    filterIcon: textFilterIcon,
  }
}

function includesKeyword(value: unknown, keyword: unknown) {
  return String(value ?? '').toLowerCase().includes(String(keyword ?? '').toLowerCase())
}

export default function NewSchedulePlans() {
  const navigate = useNavigate()
  const hasPermission = useAuthStore((state) => state.hasPermission)
  const now = dayjs()
  const [year, setYear] = useState(now.year())
  const [month, setMonth] = useState(now.month() + 1)
  const [stage, setStage] = useState('all')
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [rows, setRows] = useState<PlanRow[]>([])
  const [batches, setBatches] = useState<PlanBatch[]>([])
  const [selectedBatch, setSelectedBatch] = useState<string | undefined>()
  const [batchLoading, setBatchLoading] = useState(false)
  const [restoring, setRestoring] = useState(false)
  const [drafts, setDrafts] = useState<Record<number, Draft>>({})
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])
  const [bulkDate, setBulkDate] = useState<Dayjs | null>(null)
  const [bulkHours, setBulkHours] = useState<number | null>(null)
  const [bulkStage, setBulkStage] = useState<string | null>(null)
  const [savingId, setSavingId] = useState<number | null>(null)
  const [pushing, setPushing] = useState(false)

  const activeBatchNo = batches.find((batch) => batch.is_active)?.batch_no
  const viewingBatchNo = selectedBatch ?? activeBatchNo
  const viewingBatch = batches.find((batch) => batch.batch_no === viewingBatchNo)
  const isHistorical = !!viewingBatch && !viewingBatch.is_active
  const canAdjust = hasPermission('production.monthly_capacity_plan', 'manage')
  const readOnly = isHistorical || !canAdjust

  const loadBatches = useCallback(async () => {
    setBatchLoading(true)
    try {
      const res: any = await monthlyCapacityPlanApi.listMonthlyPlanBatches({ year, month })
      setBatches(res.data || [])
    } catch {
      setBatches([])
    } finally {
      setBatchLoading(false)
    }
  }, [month, year])

  useEffect(() => {
    loadBatches()
  }, [loadBatches])

  useEffect(() => {
    setSelectedBatch(undefined)
    setSelectedRowKeys([])
  }, [year, month])

  useEffect(() => {
    setSelectedRowKeys([])
  }, [selectedBatch])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res: any = await monthlyCapacityPlanApi.listMonthlyPlans({
        year,
        month,
        stage,
        keyword: keyword.trim() || undefined,
        batch_no: selectedBatch || undefined,
      })
      setRows(res.data || [])
      setDrafts({})
    } catch {
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [keyword, month, selectedBatch, stage, year])

  useEffect(() => {
    load()
  }, [load])

  const saveOne = async (row: PlanRow) => {
    const draft = drafts[row.id]
    if (!draft) return
    setSavingId(row.id)
    try {
      const res: any = await monthlyCapacityPlanApi.updateMonthlyPlan(row.id, {
        plan_date: draft.date ? draft.date.format('YYYY-MM-DD') : undefined,
        daily_work_hours: draft.hours,
        schedule_bucket: draft.stage,
      })
      const warning = res.data?.warning
      if (warning) message.warning(warning)
      else message.success('已保存')
      setDrafts((prev) => {
        const next = { ...prev }
        delete next[row.id]
        return next
      })
      await load()
    } catch {
      // 全局拦截器提示
    } finally {
      setSavingId(null)
    }
  }

  const saveBulk = async () => {
    if (!selectedRowKeys.length) {
      message.warning('请先选择计划')
      return
    }
    if (!bulkDate && !bulkHours && !bulkStage) {
      message.warning('请填写批量日期、批量工时或批量阶段')
      return
    }
    setSavingId(-1)
    try {
      for (const key of selectedRowKeys) {
        await monthlyCapacityPlanApi.updateMonthlyPlan(Number(key), {
          plan_date: bulkDate ? bulkDate.format('YYYY-MM-DD') : undefined,
          daily_work_hours: bulkHours ?? undefined,
          schedule_bucket: bulkStage ?? undefined,
        })
      }
      message.success(`已调整 ${selectedRowKeys.length} 条`)
      setBulkDate(null)
      setBulkHours(null)
      setBulkStage(null)
      setSelectedRowKeys([])
      await load()
    } catch {
      // 全局拦截器提示
    } finally {
      setSavingId(null)
    }
  }

  const restoreBatch = () => {
    if (!selectedBatch) return
    Modal.confirm({
      title: '恢复该批次为生效方案？',
      content: '当前生效批次会转为历史批次，本批次恢复为生效方案。历史数据不会被删除。',
      okText: '恢复',
      cancelText: '取消',
      onOk: async () => {
        setRestoring(true)
        try {
          await monthlyCapacityPlanApi.activateMonthlyPlanBatch(selectedBatch, { year, month })
          message.success('已恢复为生效方案')
          setSelectedBatch(undefined)
          await loadBatches()
        } catch {
          // 全局拦截器提示
        } finally {
          setRestoring(false)
        }
      },
    })
  }

  const pushNextWeekCapacity = () => {
    Modal.confirm({
      title: '推送下周产能计划？',
      content: '将生成下周产能的只读 H5 链接，并通过企业微信推送给陈巧霞（测试）。',
      okText: '推送',
      cancelText: '取消',
      onOk: async () => {
        setPushing(true)
        try {
          const res: any = await monthlyCapacityPlanApi.pushWeeklyCapacity()
          const data = res.data || {}
          const content = (
            <div style={{ lineHeight: 1.8 }}>
              <div>
                周期：{data.week_start} ~ {data.week_end}
              </div>
              <div>收件人：{(data.recipients || []).join('、') || '-'}</div>
              {data.error && <div style={{ color: '#cf1322' }}>{data.error}</div>}
              <div>
                链接：
                <a href={data.share_url} target="_blank" rel="noreferrer">
                  {data.share_url}
                </a>
              </div>
            </div>
          )
          if (data.success === false) {
            Modal.warning({
              title: '分享链接已生成，企业微信推送失败',
              content,
              width: 560,
            })
          } else {
            Modal.success({
              title: '推送成功',
              content,
              width: 560,
            })
          }
        } catch {
          // 全局拦截器提示
        } finally {
          setPushing(false)
        }
      },
    })
  }

  const columns: ColumnsType<PlanRow> = [
    {
      title: '计划日期',
      width: 160,
      sorter: (a, b) =>
        (a.plan_date || '').localeCompare(b.plan_date || '') || a.id - b.id,
      defaultSortOrder: 'ascend',
      render: (_, row) => {
        const value = drafts[row.id]?.date ?? (row.plan_date ? dayjs(row.plan_date) : null)
        return (
          <DatePicker
            value={value}
            format="YYYY-MM-DD"
            allowClear={false}
            disabled={readOnly}
            onChange={(date) =>
              setDrafts((prev) => ({ ...prev, [row.id]: { ...prev[row.id], date: date || undefined } }))
            }
          />
        )
      },
    },
    {
      title: '阶段',
      dataIndex: 'schedule_bucket',
      width: 110,
      filters: STAGE_OPTIONS.filter((option) => option.value !== 'all').map((option) => ({
        text: option.label,
        value: option.value,
      })),
      onFilter: (value, row) => row.schedule_bucket === value,
      sorter: (a, b) =>
        (STAGE_LABEL[a.schedule_bucket] || a.schedule_bucket).localeCompare(
          STAGE_LABEL[b.schedule_bucket] || b.schedule_bucket,
        ),
      render: (value: string, row) => (
        <Select
          size="small"
          value={drafts[row.id]?.stage ?? value}
          disabled={readOnly}
          style={{ width: 90 }}
          options={STAGE_OPTIONS.filter((option) => option.value !== 'all')}
          onChange={(stage) =>
            setDrafts((prev) => ({ ...prev, [row.id]: { ...prev[row.id], stage } }))
          }
        />
      ),
    },
    {
      title: '订单号',
      dataIndex: 'order_no',
      width: 180,
      sorter: (a, b) => (a.order_no || '').localeCompare(b.order_no || ''),
      ...textFilterProps('输入订单号'),
      onFilter: (value, row) => includesKeyword(row.order_no, value),
    },
    {
      title: '行号',
      dataIndex: 'line_no',
      width: 70,
      sorter: (a, b) => (a.line_no || '').localeCompare(b.line_no || ''),
      ...textFilterProps('输入行号'),
      onFilter: (value, row) => includesKeyword(row.line_no, value),
    },
    {
      title: '产品编码',
      dataIndex: 'product_code',
      width: 180,
      ellipsis: true,
      sorter: (a, b) => (a.product_code || '').localeCompare(b.product_code || ''),
      ...textFilterProps('输入产品编码'),
      onFilter: (value, row) => includesKeyword(row.product_code, value),
    },
    {
      title: 'BOM',
      dataIndex: 'bom_no',
      width: 200,
      ellipsis: true,
      sorter: (a, b) => (a.bom_no || '').localeCompare(b.bom_no || ''),
      ...textFilterProps('输入 BOM'),
      onFilter: (value, row) => includesKeyword(row.bom_no, value),
    },
    {
      title: '订单数量',
      dataIndex: 'source_order_qty',
      width: 100,
      align: 'right',
      sorter: (a, b) => (a.source_order_qty || 0) - (b.source_order_qty || 0),
      render: (value?: number) =>
        value === null || value === undefined ? '-' : Math.round(value),
    },
    {
      title: '当天数量',
      dataIndex: 'quantity',
      width: 100,
      align: 'right',
      sorter: (a, b) => (a.quantity || 0) - (b.quantity || 0),
      render: (value: number) => Math.round(value || 0),
    },
    {
      title: '日工时',
      width: 120,
      sorter: (a, b) => (a.daily_work_hours || 0) - (b.daily_work_hours || 0),
      render: (_, row) => {
        const value = drafts[row.id]?.hours ?? row.daily_work_hours
        return (
          <InputNumber
            min={1}
            max={24}
            step={0.5}
            value={value}
            disabled={readOnly}
            onChange={(hours) =>
              setDrafts((prev) => ({
                ...prev,
                [row.id]: { ...prev[row.id], hours: Number(hours || 0) },
              }))
            }
            style={{ width: 100 }}
          />
        )
      },
    },
    {
      title: '需要工时',
      dataIndex: 'required_hours',
      width: 100,
      align: 'right',
      sorter: (a, b) => (a.required_hours || 0) - (b.required_hours || 0),
      render: (value?: number) => (value === null || value === undefined ? '-' : value),
    },
    {
      title: '出货计划',
      dataIndex: 'source_promised_date',
      width: 110,
      sorter: (a, b) =>
        (a.source_promised_date || '').localeCompare(b.source_promised_date || ''),
    },
    {
      title: '状态',
      width: 100,
      filters: STATUS_FILTERS,
      onFilter: (value, row) => (value === 'warning' ? !!row.warning : !row.warning),
      sorter: (a, b) => Number(!!a.warning) - Number(!!b.warning),
      render: (_, row) =>
        row.warning ? <Tag color="red">超工时</Tag> : <Tag color="green">正常</Tag>,
    },
    {
      title: '操作',
      width: 90,
      fixed: 'right',
      render: (_, row) => (
          <Button
            type="link"
            size="small"
            disabled={!drafts[row.id] || readOnly}
            loading={savingId === row.id}
            onClick={() => saveOne(row)}
          >
          保存
        </Button>
      ),
    },
  ]

  return (
    <div style={{ padding: 16 }}>
      <Card
        title="新排产方案"
        extra={
          <Space>
            <Button type="primary" loading={pushing} onClick={pushNextWeekCapacity}>
              推送下周产能
            </Button>
            <Button onClick={() => navigate('/production/monthly-capacity-plan')}>
              返回产能规划
            </Button>
            <Button onClick={load} loading={loading}>
              刷新
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Space wrap>
            <Select
              style={{ width: 100 }}
              value={year}
              onChange={setYear}
              options={Array.from({ length: 5 }, (_, index) => ({
                value: now.year() - 1 + index,
                label: `${now.year() - 1 + index}年`,
              }))}
            />
            <Select
              style={{ width: 90 }}
              value={month}
              onChange={setMonth}
              options={Array.from({ length: 12 }, (_, index) => ({
                value: index + 1,
                label: `${index + 1}月`,
              }))}
            />
            <Select
              style={{ width: 130 }}
              value={stage}
              onChange={setStage}
              options={STAGE_OPTIONS}
            />
            <span>
              方案批次
              <Select
                style={{ width: 320, marginLeft: 8 }}
                placeholder="当前生效方案"
                loading={batchLoading}
                value={viewingBatchNo}
                onChange={setSelectedBatch}
                options={batches.map((batch) => ({
                  value: batch.batch_no,
                  label: `${batch.created_at ? dayjs(batch.created_at).format('MM-DD HH:mm') : batch.batch_no} · ${batch.row_count}条 · ${batch.is_active ? '生效中' : '历史'}`,
                }))}
              />
            </span>
            <Input.Search
              allowClear
              placeholder="订单号 / 产品 / BOM"
              style={{ width: 260 }}
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onSearch={load}
            />
            <DatePicker
              placeholder="批量日期"
              value={bulkDate}
              disabled={readOnly}
              onChange={(date) => setBulkDate(date)}
            />
            <InputNumber
              placeholder="批量工时"
              min={1}
              max={24}
              step={0.5}
              value={bulkHours}
              disabled={readOnly}
              onChange={(value) => setBulkHours(value ? Number(value) : null)}
              style={{ width: 120 }}
            />
            <Select
              allowClear
              placeholder="批量阶段"
              value={bulkStage ?? undefined}
              disabled={readOnly}
              onChange={(value) => setBulkStage(value ?? null)}
              style={{ width: 120 }}
              options={STAGE_OPTIONS.filter((option) => option.value !== 'all')}
            />
            <Button loading={savingId === -1} disabled={readOnly} onClick={saveBulk}>
              批量调整
            </Button>
          </Space>

          {!canAdjust && (
            <Alert
              type="info"
              showIcon
              message="当前账号只有查看权限"
              description="需要调整计划日期、日工时或阶段，请在「角色管理」中为该角色开通「月度产能规划」的管理权限。"
            />
          )}

          {isHistorical && (
            <Alert
              type="warning"
              showIcon
              message={`正在查看历史批次：${viewingBatch?.batch_no}`}
              description="历史批次只读，不会被修改；可恢复为生效方案。"
              action={
                <Button type="primary" size="small" loading={restoring} onClick={restoreBatch}>
                  恢复为生效方案
                </Button>
              }
            />
          )}

          <Table<PlanRow>
            rowKey="id"
            size="small"
            bordered
            loading={loading}
            columns={columns}
            dataSource={rows}
            scroll={{ x: 1500 }}
            rowSelection={readOnly ? undefined : {
              selectedRowKeys,
              onChange: (keys) => setSelectedRowKeys(keys),
            }}
            pagination={{ pageSize: 50, showSizeChanger: true, showTotal: (value) => `共 ${value} 条` }}
          />
        </Space>
      </Card>
    </div>
  )
}
