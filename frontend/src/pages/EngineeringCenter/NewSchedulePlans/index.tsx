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
}

const STAGE_OPTIONS = [
  { value: 'all', label: '全部阶段' },
  { value: 'assembly', label: '组装' },
  { value: 'packaging', label: '包装' },
  { value: 'lean', label: '精益' },
]

const STAGE_LABEL: Record<string, string> = {
  assembly: '组装',
  packaging: '包装',
  lean: '精益',
}

export default function NewSchedulePlans() {
  const navigate = useNavigate()
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
  const [savingId, setSavingId] = useState<number | null>(null)

  const activeBatchNo = batches.find((batch) => batch.is_active)?.batch_no
  const viewingBatchNo = selectedBatch ?? activeBatchNo
  const viewingBatch = batches.find((batch) => batch.batch_no === viewingBatchNo)
  const isHistorical = !!viewingBatch && !viewingBatch.is_active

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
    if (!bulkDate && !bulkHours) {
      message.warning('请填写批量日期或批量工时')
      return
    }
    setSavingId(-1)
    try {
      for (const key of selectedRowKeys) {
        await monthlyCapacityPlanApi.updateMonthlyPlan(Number(key), {
          plan_date: bulkDate ? bulkDate.format('YYYY-MM-DD') : undefined,
          daily_work_hours: bulkHours ?? undefined,
        })
      }
      message.success(`已调整 ${selectedRowKeys.length} 条`)
      setBulkDate(null)
      setBulkHours(null)
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

  const columns: ColumnsType<PlanRow> = [
    {
      title: '计划日期',
      width: 160,
      render: (_, row) => {
        const value = drafts[row.id]?.date ?? (row.plan_date ? dayjs(row.plan_date) : null)
        return (
          <DatePicker
            value={value}
            format="YYYY-MM-DD"
            allowClear={false}
            disabled={isHistorical}
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
      width: 80,
      render: (value: string) => <Tag>{STAGE_LABEL[value] || value}</Tag>,
    },
    { title: '订单号', dataIndex: 'order_no', width: 180 },
    { title: '行号', dataIndex: 'line_no', width: 70 },
    { title: '产品编码', dataIndex: 'product_code', width: 180, ellipsis: true },
    { title: 'BOM', dataIndex: 'bom_no', width: 200, ellipsis: true },
    {
      title: '数量',
      dataIndex: 'quantity',
      width: 90,
      align: 'right',
      render: (value: number) => value?.toFixed(2),
    },
    {
      title: '日工时',
      width: 120,
      render: (_, row) => {
        const value = drafts[row.id]?.hours ?? row.daily_work_hours
        return (
          <InputNumber
            min={1}
            max={24}
            step={0.5}
            value={value}
            disabled={isHistorical}
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
      render: (value?: number) => (value === null || value === undefined ? '-' : value),
    },
    {
      title: '出货计划',
      dataIndex: 'source_promised_date',
      width: 110,
    },
    {
      title: '状态',
      width: 100,
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
            disabled={!drafts[row.id] || isHistorical}
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
              disabled={isHistorical}
              onChange={(date) => setBulkDate(date)}
            />
            <InputNumber
              placeholder="批量工时"
              min={1}
              max={24}
              step={0.5}
              value={bulkHours}
              disabled={isHistorical}
              onChange={(value) => setBulkHours(value ? Number(value) : null)}
              style={{ width: 120 }}
            />
            <Button loading={savingId === -1} disabled={isHistorical} onClick={saveBulk}>
              批量调整
            </Button>
          </Space>

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
            rowSelection={isHistorical ? undefined : {
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
