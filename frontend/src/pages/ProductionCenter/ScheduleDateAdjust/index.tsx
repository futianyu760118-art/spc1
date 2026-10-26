import { useCallback, useEffect, useMemo, useState } from 'react'
import type { Key } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert,
  Button,
  Checkbox,
  Col,
  Collapse,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Segmented,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, PlusOutlined, ReloadOutlined, SaveOutlined, UndoOutlined } from '@ant-design/icons'
import dayjs, { Dayjs } from 'dayjs'
import { productionApi } from '../../../services/api'
import { formatDate } from '../../../utils'

interface PlanRow {
  id: number
  order_no?: string
  line_no?: string
  product_code?: string
  model_code?: string
  quantity?: number
  upph?: number
  manpower?: number
  daily_work_hours?: number
  total_hours?: number
  owner?: string
  department?: string
  plan_date?: string
  start_date?: string
  end_date?: string
  status?: string
  schedule_bucket?: string
  schedule_bucket_label?: string
  delivery_status?: string
  delay_days?: number
}

interface CapacityConflict {
  date: string
  department: string
  schedule_bucket: string
  booked_hours: number
  limit_hours: number
  plan_ids: number[]
}

const BUCKET_TABS = [
  { key: 'lean', label: '精益' },
  { key: 'assembly', label: '装配-组装' },
  { key: 'packaging', label: '装配-包装' },
]

const STATUS_LABELS: Record<string, string> = {
  planned: '已排产',
  in_progress: '生产中',
  completed: '已完工',
  delayed: '延期',
  cancelled: '已取消',
}

function getRowDate(row: PlanRow): string | undefined {
  return row.start_date || row.plan_date
}

function getTotalHours(row: PlanRow): number | null {
  const quantity = Number(row.quantity || 0)
  const upph = Number(row.upph || 0)
  const manpower = Number(row.manpower || 10)
  if (quantity <= 0 || upph <= 0 || manpower <= 0) return null
  return Number((quantity / (upph * manpower)).toFixed(2))
}

export default function ScheduleDateAdjust() {
  const navigate = useNavigate()
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>([
    dayjs().startOf('month'),
    dayjs().endOf('month'),
  ])
  const [keyword, setKeyword] = useState('')
  const [activeBucket, setActiveBucket] = useState('lean')
  const [plans, setPlans] = useState<PlanRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(50)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [drafts, setDrafts] = useState<Record<number, Dayjs>>({})
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])
  const [bulkDate, setBulkDate] = useState<Dayjs | null>(null)
  const [conflicts, setConflicts] = useState<CapacityConflict[]>([])
  const [insertOpen, setInsertOpen] = useState(false)
  const [insertMode, setInsertMode] = useState<'order' | 'manual' | 'rework'>('order')
  const [insertForm] = Form.useForm()
  const [inserting, setInserting] = useState(false)
  const [orderOptions, setOrderOptions] = useState<any[]>([])
  const [orderLoading, setOrderLoading] = useState(false)
  const [selectedOrder, setSelectedOrder] = useState<any>(null)
  const [reworkOptions, setReworkOptions] = useState<any[]>([])
  const [reworkLoading, setReworkLoading] = useState(false)
  const [reworkKeyword, setReworkKeyword] = useState('')
  const [selectedRework, setSelectedRework] = useState<any>(null)
  const [syncingRework, setSyncingRework] = useState(false)
  const [splitOpen, setSplitOpen] = useState(false)
  const [splitPlan, setSplitPlan] = useState<PlanRow | null>(null)
  const [splitForm] = Form.useForm()
  const [splitting, setSplitting] = useState(false)
  const [splitCount, setSplitCount] = useState(2)
  const [remainders, setRemainders] = useState<any[]>([])
  const [remainderSourceQty, setRemainderSourceQty] = useState<number | null>(null)

  const loadPlans = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, any> = {
        page,
        page_size: pageSize,
        is_active: true,
        date_start: dateRange[0].format('YYYY-MM-DD'),
        date_end: dateRange[1].format('YYYY-MM-DD'),
      }
      if (keyword.trim()) params.keyword = keyword.trim()
      params.schedule_bucket = activeBucket
      const res: any = await productionApi.listSchedulePlans(params)
      setPlans(res.data?.items || [])
      setTotal(res.data?.total || 0)
    } catch {
      // 错误已由全局拦截器提示
    } finally {
      setLoading(false)
    }
  }, [activeBucket, dateRange, keyword, page, pageSize])

  useEffect(() => {
    loadPlans()
  }, [loadPlans])

  const loadRemainders = useCallback(async () => {
    try {
      const res: any = await productionApi.listScheduleRemainders({
        schedule_bucket: activeBucket,
      })
      setRemainders(res.data || [])
    } catch {
      // 错误已由全局拦截器提示
      setRemainders([])
    }
  }, [activeBucket])

  useEffect(() => {
    loadRemainders()
  }, [loadRemainders])

  const conflictPlanIds = useMemo(
    () => new Set(conflicts.flatMap((item) => item.plan_ids)),
    [conflicts],
  )

  const watchedBatches = Form.useWatch('batches', splitForm) as any[] | undefined
  const splitTotalQty = (watchedBatches || []).reduce(
    (sum, item) => sum + Number(item?.quantity || 0),
    0,
  )
  const splitDatedQty = (watchedBatches || [])
    .filter((item) => item?.target_date)
    .reduce((sum, item) => sum + Number(item?.quantity || 0), 0)
  const splitUndatedQty = Number((splitTotalQty - splitDatedQty).toFixed(2))
  const splitRemainingQty = Number((Number(splitPlan?.quantity || 0) - splitTotalQty).toFixed(2))

  const draftItems = useMemo(
    () =>
      Object.entries(drafts)
        .filter(([, value]) => Boolean(value))
        .map(([planId, value]) => ({
          plan_id: Number(planId),
          target_date: value.format('YYYY-MM-DD'),
        })),
    [drafts],
  )

  const handleDateChange = (row: PlanRow, value: Dayjs | null) => {
    setDrafts((prev) => {
      const next = { ...prev }
      const original = getRowDate(row)
      if (!value || (original && value.format('YYYY-MM-DD') === original)) {
        delete next[row.id]
      } else {
        next[row.id] = value
      }
      return next
    })
  }

  const handleBulkApply = () => {
    if (!bulkDate) {
      message.info('请先选择目标日期')
      return
    }
    if (!selectedRowKeys.length) {
      message.info('请先勾选需要调整的计划')
      return
    }
    setDrafts((prev) => {
      const next = { ...prev }
      selectedRowKeys.forEach((key) => {
        next[Number(key)] = bulkDate
      })
      return next
    })
  }

  const handleReset = () => {
    setDrafts({})
    setSelectedRowKeys([])
    setConflicts([])
  }

  const handleDeletePlans = (ids: number[]) => {
    if (!ids.length) return
    Modal.confirm({
      title: `确认删除 ${ids.length} 条排产计划？`,
      content: '删除后会释放产能，订单回到待排；排产看板和生产驾驶舱会同步更新。',
      okText: '删除',
      okButtonProps: { danger: true },
      onOk: async () => {
        await productionApi.batchDeletePlans(ids)
        message.success(`已删除 ${ids.length} 条计划`)
        setSelectedRowKeys([])
        setDrafts((prev) => {
          const next = { ...prev }
          ids.forEach((id) => {
            delete next[id]
          })
          return next
        })
        await loadPlans()
        await loadRemainders()
      },
    })
  }

  const handleSave = async () => {
    if (!draftItems.length) {
      message.info('没有需要保存的修改')
      return
    }
    setSaving(true)
    try {
      const res: any = await productionApi.adjustScheduleDates({ items: draftItems })
      const payload = res.data || {}
      setConflicts(payload.conflicts || [])
      if (payload.failed_count) {
        const failed = (payload.items || []).filter((item: any) => !item.success)
        message.warning(
          `${payload.success_count || 0} 条已保存，${payload.failed_count} 条失败：${failed
            .map((item: any) => item.message)
            .join('；')}`,
        )
      } else {
        message.success(`已保存 ${payload.success_count || draftItems.length} 条日期调整`)
      }
      setDrafts({})
      setSelectedRowKeys([])
      setBulkDate(null)
      await loadPlans()
    } catch {
      // 错误已由全局拦截器提示
    } finally {
      setSaving(false)
    }
  }

  const loadOrderOptions = async () => {
    setOrderLoading(true)
    try {
      const res: any = await productionApi.getOrdersForScheduling({
        page: 1,
        page_size: 50,
      })
      setOrderOptions(res.data?.items || [])
    } catch {
      // 错误已由全局拦截器提示
      setOrderOptions([])
    } finally {
      setOrderLoading(false)
    }
  }

  const openInsert = () => {
    setInsertMode('order')
    setSelectedOrder(null)
    setSelectedRework(null)
    setRemainderSourceQty(null)
    insertForm.resetFields()
    insertForm.setFieldsValue({
      department: '生产',
      schedule_bucket: activeBucket,
      manpower: 10,
      allow_duplicate: false,
      line_no: '1',
      target_date: dayjs().add(1, 'day'),
    })
    setInsertOpen(true)
    loadOrderOptions()
  }

  const openInsertWithPlan = (row: PlanRow) => {
    setInsertMode('manual')
    setSelectedOrder(null)
    setSelectedRework(null)
    setRemainderSourceQty(null)
    insertForm.resetFields()
    insertForm.setFieldsValue({
      order_no: row.order_no,
      line_no: row.line_no || '1',
      product_code: row.product_code,
      model_code: row.model_code,
      quantity: row.quantity,
      upph: row.upph,
      manpower: row.manpower || 10,
      daily_work_hours: row.daily_work_hours,
      owner: row.owner,
      department: row.department || '生产',
      schedule_bucket: row.schedule_bucket || activeBucket,
      target_date: getRowDate(row) ? dayjs(getRowDate(row)) : dayjs().add(1, 'day'),
      allow_duplicate: true,
      remark: `返单自 ${row.order_no || ''}/${row.line_no || ''}`,
    })
    setInsertOpen(true)
  }

  const loadReworkOptions = async (keyword?: string) => {
    setReworkLoading(true)
    try {
      const res: any = await productionApi.listReworkOrders({
        page: 1,
        page_size: 50,
        keyword: keyword?.trim() || undefined,
      })
      setReworkOptions(res.data?.items || [])
    } catch {
      // 错误已由全局拦截器提示
      setReworkOptions([])
    } finally {
      setReworkLoading(false)
    }
  }

  const handleInsertModeChange = (mode: 'order' | 'manual' | 'rework') => {
    setInsertMode(mode)
    setSelectedOrder(null)
    setSelectedRework(null)
    setRemainderSourceQty(null)
    insertForm.resetFields()
    insertForm.setFieldsValue({
      department: '生产',
      schedule_bucket: activeBucket,
      manpower: 10,
      allow_duplicate: false,
      line_no: '1',
      target_date: dayjs().add(1, 'day'),
    })
    if (mode === 'rework') {
      loadReworkOptions()
    }
  }

  const handleOrderSelect = (value: string) => {
    const order = orderOptions.find(
      (item) => `${item.order_no}::${item.line_no}` === value,
    )
    setSelectedOrder(order || null)
    if (!order) return
    const bucket = ['lean', 'assembly', 'packaging'].includes(order.schedule_bucket)
      ? order.schedule_bucket
      : undefined
    insertForm.setFieldsValue({
      line_no: order.line_no,
      product_code: order.product_code,
      model_code: order.product_model,
      quantity: order.order_qty,
      upph: order.upph,
      schedule_bucket: bucket,
      allow_duplicate: !!order.has_schedule,
    })
    if (!bucket) {
      message.warning('该订单是组装+包装，请分别插入组装段和包装段')
    }
  }

  const handleReworkSelect = (value: string) => {
    const rework = reworkOptions.find(
      (item) => String(item.request_id) === String(value),
    )
    setSelectedRework(rework || null)
    if (!rework) return
    insertForm.setFieldsValue({
      order_no: rework.order_no,
      line_no: rework.line_no || '1',
      product_code: rework.product_code,
      quantity: rework.defect_qty,
      allow_duplicate: true,
      remark: `OA返工单 ${rework.flow_no || rework.request_id}`,
    })
    if (Number(rework.rework_hours || 0) <= 0) {
      message.warning('该返工单返工工时为 0，无法排产')
    }
  }

  const openRemainderSchedule = (rem: any) => {
    setInsertMode('manual')
    setSelectedOrder(null)
    setSelectedRework(null)
    setRemainderSourceQty(Number(rem.source_order_qty) || null)
    insertForm.resetFields()
    insertForm.setFieldsValue({
      order_no: rem.order_no,
      line_no: rem.line_no || '1',
      product_code: rem.product_code,
      model_code: rem.model_code,
      quantity: rem.remaining_qty,
      upph: rem.upph,
      manpower: rem.manpower || 10,
      daily_work_hours: rem.daily_work_hours,
      department: rem.department || '生产',
      schedule_bucket: rem.schedule_bucket || activeBucket,
      target_date: dayjs().add(1, 'day'),
      allow_duplicate: true,
      remark: `补排剩余 ${rem.remaining_qty}/${rem.source_order_qty}`,
    })
    setInsertOpen(true)
  }

  const handleSyncRework = async () => {
    setSyncingRework(true)
    try {
      const res: any = await productionApi.syncReworkOrders()
      const stats = res.data || {}
      message.success(
        `同步完成：拉取 ${stats.fetched || 0}，新增 ${stats.created || 0}，更新 ${stats.updated || 0}`,
      )
      await loadReworkOptions(reworkKeyword)
    } finally {
      setSyncingRework(false)
    }
  }

  const handleInsert = async () => {
    let values: any
    try {
      values = await insertForm.validateFields()
    } catch {
      return
    }
    setInserting(true)
    try {
      const rework = insertMode === 'rework' ? selectedRework : null
      const orderNo =
        insertMode === 'order'
          ? selectedOrder?.order_no
          : insertMode === 'rework'
            ? rework?.order_no
            : values.order_no
      const payload: Record<string, any> = {
        order_no: orderNo,
        line_no:
          insertMode === 'order'
            ? selectedOrder?.line_no || '1'
            : values.line_no || '1',
        department: values.department || '生产',
        schedule_bucket: values.schedule_bucket,
        target_date: values.target_date.format('YYYY-MM-DD'),
        quantity: values.quantity,
        upph: insertMode === 'rework' ? undefined : values.upph,
        manpower: values.manpower,
        daily_work_hours: values.daily_work_hours,
        product_code: values.product_code,
        model_code: values.model_code,
        owner: values.owner,
        remark: values.remark,
        allow_duplicate: !!values.allow_duplicate,
        break_frozen_reason: values.break_frozen_reason,
        source_promised_date: selectedOrder?.promised_date || undefined,
        rework_hours: rework ? Number(rework.rework_hours) : undefined,
        rework_request_id: rework ? String(rework.request_id) : undefined,
        source_order_qty: remainderSourceQty ?? undefined,
      }
      const res: any = await productionApi.insertSchedulePlan(payload)
      const data = res.data || {}
      const pushed: any[] = data.pushed || []
      setConflicts(data.conflicts || [])
      setInsertOpen(false)
      setActiveBucket(values.schedule_bucket)
      setPage(1)
      setRemainderSourceQty(null)
      await loadPlans()
      await loadRemainders()
      Modal.success({
        title: '插入成功',
        content: (
          <div>
            <div style={{ marginBottom: 8 }}>
              计划 {data.plan?.order_no} / {data.plan?.line_no}：
              {formatDate(data.plan?.start_date)} ~ {formatDate(data.plan?.end_date)}
            </div>
            <div>顺延 {pushed.length} 条计划</div>
            {pushed.slice(0, 8).map((item) => (
              <div key={item.plan_id} style={{ color: '#64748b', fontSize: 12, marginTop: 4 }}>
                {item.order_no} / {item.line_no}：{formatDate(item.old_start)} →{' '}
                {formatDate(item.new_start)}
              </div>
            ))}
          </div>
        ),
      })
    } catch {
      // 错误已由全局拦截器提示
    } finally {
      setInserting(false)
    }
  }

  const buildEvenBatches = (row: PlanRow, requestedCount: number) => {
    const totalQty = Number(row.quantity || 0)
    const maxCount = Math.max(1, Math.floor(totalQty))
    const count = Math.max(1, Math.min(Math.floor(requestedCount || 2), maxCount))
    const base = Math.floor((totalQty / count) * 100) / 100
    const quantities = Array.from({ length: count }, () => base)
    quantities[count - 1] = Number((totalQty - base * (count - 1)).toFixed(2))

    const totalHours = Number(row.total_hours || 0)
    const dailyHours = Number(row.daily_work_hours || 8.5) || 8.5
    let cursor = getRowDate(row) ? dayjs(getRowDate(row)) : dayjs().add(1, 'day')
    return quantities.map((quantity) => {
      const days = totalQty > 0 && totalHours > 0
        ? Math.max(1, Math.ceil((quantity / totalQty) * totalHours / dailyHours))
        : 1
      const target = cursor
      cursor = cursor.add(days, 'day')
      return { quantity, target_date: target }
    })
  }

  const openSplit = (row: PlanRow) => {
    setSplitPlan(row)
    setSplitCount(2)
    splitForm.resetFields()
    splitForm.setFieldsValue({
      batches: buildEvenBatches(row, 2),
      push_conflicts: true,
    })
    setSplitOpen(true)
  }

  const handleEvenSplit = () => {
    if (!splitPlan) return
    const batches = buildEvenBatches(splitPlan, splitCount)
    splitForm.setFieldsValue({ batches })
  }

  const handleSplit = async () => {
    if (!splitPlan) return
    let values: any
    try {
      values = await splitForm.validateFields()
    } catch {
      return
    }
    const batches = (values.batches || [])
      .filter((item: any) => item && item.quantity > 0 && item.target_date)
      .map((item: any) => ({
        quantity: Number(item.quantity),
        target_date: item.target_date.format('YYYY-MM-DD'),
      }))
    if (!batches.length) {
      message.info('请至少填写一个带开始日期的批次；无日期的批次会作为待定余量')
      return
    }
    setSplitting(true)
    try {
      const res: any = await productionApi.splitSchedulePlan({
        plan_id: splitPlan.id,
        batches,
        push_conflicts: !!values.push_conflicts,
        break_frozen_reason: values.break_frozen_reason,
      })
      const data = res.data || {}
      setConflicts(data.conflicts || [])
      setSplitOpen(false)
      await loadPlans()
      await loadRemainders()
      Modal.success({
        title: '拆单完成',
        content: (
          <div>
            <div>已拆为 {data.plans?.length || batches.length} 批</div>
            <div>顺延 {data.pushed?.length || 0} 条后续计划</div>
            {Number(data.unplanned_qty || 0) > 0 && (
              <div style={{ color: '#fa8c16' }}>
                未排数量 {data.unplanned_qty}（已进入待排余量，可稍后补排）
              </div>
            )}
          </div>
        ),
      })
    } catch {
      // 错误已由全局拦截器提示
    } finally {
      setSplitting(false)
    }
  }

  const columns: ColumnsType<PlanRow> = [
    {
      title: '订单号',
      dataIndex: 'order_no',
      width: 150,
      fixed: 'left',
      render: (value?: string) => value || '-',
    },
    { title: '行号', dataIndex: 'line_no', width: 80, render: (value?: string) => value || '-' },
    {
      title: '产品编码',
      dataIndex: 'product_code',
      width: 180,
      ellipsis: true,
      render: (value?: string, row?: PlanRow) => (
        <Tooltip title={row?.model_code || value}>
          <span>{value || row?.model_code || '-'}</span>
        </Tooltip>
      ),
    },
    {
      title: '排产段',
      dataIndex: 'schedule_bucket_label',
      width: 110,
      render: (value: string | undefined, row: PlanRow) => (
        <Tag>{value || row.schedule_bucket || '-'}</Tag>
      ),
    },
    { title: '数量', dataIndex: 'quantity', width: 90, render: (value?: number) => value ?? '-' },
    {
      title: '总工时',
      width: 90,
      render: (_: unknown, row: PlanRow) => {
        const hours = getTotalHours(row)
        return hours === null ? '-' : `${hours}h`
      },
    },
    {
      title: '当前开始',
      width: 110,
      render: (_: unknown, row: PlanRow) => formatDate(getRowDate(row)),
    },
    {
      title: '当前完成',
      width: 110,
      render: (_: unknown, row: PlanRow) => (
        <Tag color={row.delivery_status === 'delayed' ? 'red' : 'green'}>
          {formatDate(row.end_date)}
        </Tag>
      ),
    },
    {
      title: '新开始日期',
      width: 170,
      align: 'center',
      render: (_: unknown, row: PlanRow) => {
        const value = drafts[row.id] ?? (getRowDate(row) ? dayjs(getRowDate(row)) : null)
        const isConflict = conflictPlanIds.has(row.id)
        return (
          <DatePicker
            allowClear={false}
            value={value}
            format="YYYY-MM-DD"
            status={isConflict ? 'error' : undefined}
            onChange={(next) => handleDateChange(row, next)}
            style={{ width: 140 }}
          />
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 90,
      render: (value?: string) => STATUS_LABELS[value || ''] || value || '-',
    },
    {
      title: '延期',
      width: 80,
      render: (_: unknown, row: PlanRow) =>
        row.delay_days ? <Tag color="red">延期 {row.delay_days} 天</Tag> : <Tag color="green">正常</Tag>,
    },
    {
      title: '操作',
      width: 180,
      fixed: 'right',
      render: (_: unknown, row: PlanRow) => (
        <Space size={0}>
          <Button type="link" size="small" onClick={() => openInsertWithPlan(row)}>
            返单
          </Button>
          <Button type="link" size="small" onClick={() => openSplit(row)}>
            拆单
          </Button>
          <Button type="link" size="small" danger onClick={() => handleDeletePlans([row.id])}>
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: 16, marginBottom: 16 }}>
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="直接改日期，以你填的日期为准"
            description="保存后立即重算产能槽，排产看板按新日期展示；不会自动挪动其它计划。当天产能超限会标红提示，但不阻止保存。周日会自动顺延到下一个生产日。"
          />
          <Space wrap size={12} style={{ width: '100%', justifyContent: 'space-between' }}>
            <Space wrap size={12}>
              <DatePicker.RangePicker
                allowClear={false}
                value={dateRange}
                onChange={(value) => {
                  if (value && value[0] && value[1]) {
                    setDateRange([value[0], value[1]])
                    setPage(1)
                  }
                }}
              />
              <Input
                allowClear
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                onPressEnter={() => {
                  setPage(1)
                  loadPlans()
                }}
                placeholder="搜索订单 / 产品 / BOM"
                style={{ width: 220 }}
              />
              <Button icon={<ReloadOutlined />} onClick={loadPlans}>
                刷新
              </Button>
            </Space>
            <Space wrap size={12}>
              <Button type="primary" ghost icon={<PlusOutlined />} onClick={openInsert}>
                插入计划
              </Button>
              <DatePicker
                value={bulkDate}
                onChange={(value) => setBulkDate(value)}
                placeholder="批量改到"
              />
              <Button onClick={handleBulkApply} disabled={!selectedRowKeys.length}>
                应用到选中 {selectedRowKeys.length ? `(${selectedRowKeys.length})` : ''}
              </Button>
              <Button
                danger
                icon={<DeleteOutlined />}
                disabled={!selectedRowKeys.length}
                onClick={() => handleDeletePlans(selectedRowKeys.map(Number))}
              >
                删除选中 {selectedRowKeys.length ? `(${selectedRowKeys.length})` : ''}
              </Button>
              <Button icon={<UndoOutlined />} onClick={handleReset} disabled={!draftItems.length}>
                还原
              </Button>
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={saving}
                disabled={!draftItems.length}
                onClick={handleSave}
              >
                保存修改 {draftItems.length ? `(${draftItems.length})` : ''}
              </Button>
            </Space>
          </Space>
          <Space wrap size={12}>
            <Button onClick={() => navigate('/schedule-plans')}>去排产台账</Button>
            <Button onClick={() => navigate('/schedule-board')}>去看板</Button>
          </Space>
        </Space>
      </div>

      {remainders.length > 0 && (
        <div className="card-modern" style={{ padding: 16, marginBottom: 16 }}>
          <div style={{ fontWeight: 600, marginBottom: 10 }}>
            待排余量（{remainders.length}）
            <span style={{ marginLeft: 8, color: '#94a3b8', fontSize: 12, fontWeight: 400 }}>
              拆单少排 / 只生产一部分，剩余量可随时补排
            </span>
          </div>
          <Space direction="vertical" size={6} style={{ width: '100%' }}>
            {remainders.slice(0, 20).map((rem: any) => (
              <div
                key={`${rem.order_no}-${rem.line_no}-${rem.schedule_bucket}-${rem.source_order_qty}`}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 12,
                }}
              >
                <span style={{ fontSize: 13 }}>
                  {rem.order_no} / {rem.line_no} · {rem.product_code || '-'} · 剩余{' '}
                  <b>{rem.remaining_qty}</b> / {rem.source_order_qty}
                </span>
                <Button size="small" type="primary" ghost onClick={() => openRemainderSchedule(rem)}>
                  补排
                </Button>
              </div>
            ))}
            {remainders.length > 20 && (
              <span style={{ color: '#94a3b8', fontSize: 12 }}>
                还有 {remainders.length - 20} 条，请缩小范围查看
              </span>
            )}
          </Space>
        </div>
      )}

      {conflicts.length ? (
        <div className="card-modern" style={{ padding: 16, marginBottom: 16 }}>
          <Alert
            type="warning"
            showIcon
            message={`保存成功，但有 ${conflicts.length} 个「日期 + 排产段」超出日产能`}
            description={
              <Space direction="vertical" size={4} style={{ marginTop: 8 }}>
                {conflicts.map((item) => (
                  <span key={`${item.date}-${item.department}-${item.schedule_bucket}`}>
                    {item.date} · {item.schedule_bucket} · 已占 {item.booked_hours}h / 上限{' '}
                    {item.limit_hours}h（涉及计划 {item.plan_ids.join(', ')}）
                  </span>
                ))}
              </Space>
            }
          />
        </div>
      ) : null}

      <div className="card-modern" style={{ padding: 16 }}>
        <Tabs
          activeKey={activeBucket}
          onChange={(key) => {
            setActiveBucket(key)
            setPage(1)
            setSelectedRowKeys([])
          }}
          items={BUCKET_TABS.map((item) => ({
            key: item.key,
            label: item.label,
            children: (
              <Table<PlanRow>
                rowKey="id"
                size="small"
                bordered
                loading={loading}
                columns={columns}
                dataSource={plans}
                scroll={{ x: 1280 }}
                locale={{ emptyText: <Empty description={`当前区间没有${item.label}计划`} /> }}
                rowSelection={{
                  selectedRowKeys,
                  onChange: (keys) => setSelectedRowKeys(keys),
                }}
                pagination={{
                  current: page,
                  pageSize,
                  total,
                  showSizeChanger: true,
                  pageSizeOptions: [20, 50, 100, 200],
                  showTotal: (value) => `共 ${value} 条`,
                  onChange: (nextPage, nextPageSize) => {
                    setPage(nextPageSize !== pageSize ? 1 : nextPage)
                    setPageSize(nextPageSize)
                    setSelectedRowKeys([])
                  },
                }}
              />
            ),
          }))}
        />
      </div>

      <Modal
        title="插入计划"
        open={insertOpen}
        destroyOnHidden
        width={760}
        okText="插入并顺延"
        confirmLoading={inserting}
        onOk={handleInsert}
        onCancel={() => setInsertOpen(false)}
      >
        <Alert
          type="info"
          showIcon
          message="插入日期优先，同部门同排产段的后续计划整体顺延"
          description="新订单选订单池；返单点行上「返单」自动带入原单；有 OA 返工单可直接选「OA返工单」，按返工工时占产能。"
          style={{ marginBottom: 16 }}
        />
        <Segmented
          value={insertMode}
          onChange={(value) => handleInsertModeChange(value as 'order' | 'manual')}
          options={[
            { value: 'order', label: '订单池插入' },
            { value: 'manual', label: '手工返单' },
            { value: 'rework', label: 'OA返工单' },
          ]}
          style={{ marginBottom: 16 }}
        />
        <Form form={insertForm} layout="vertical">
          <Row gutter={16}>
            {insertMode === 'order' ? (
              <Col span={24}>
                <Form.Item name="order_key" label="订单" rules={[{ required: true }]}>
                  <Select
                    showSearch
                    optionFilterProp="label"
                    loading={orderLoading}
                    placeholder="搜索订单号 / 产品编码"
                    onChange={handleOrderSelect}
                    options={orderOptions.map((order) => ({
                      value: `${order.order_no}::${order.line_no}`,
                      label: `${order.order_no} / ${order.line_no} · ${order.product_code || '-'} · ${
                        order.schedule_bucket_label || '未分类'
                      } · 数 ${order.order_qty ?? '-'}`,
                    }))}
                  />
                </Form.Item>
              </Col>
            ) : insertMode === 'rework' ? (
              <>
                <Col span={24}>
                  <Space.Compact style={{ width: '100%', marginBottom: 16 }}>
                    <Input
                      allowClear
                      value={reworkKeyword}
                      onChange={(event) => setReworkKeyword(event.target.value)}
                      onPressEnter={() => loadReworkOptions(reworkKeyword)}
                      placeholder="搜索订单号 / 产品编码 / 流程号"
                    />
                    <Button onClick={() => loadReworkOptions(reworkKeyword)}>查询</Button>
                    <Button loading={syncingRework} onClick={handleSyncRework}>
                      同步OA
                    </Button>
                  </Space.Compact>
                </Col>
                <Col span={24}>
                  <Form.Item
                    name="rework_key"
                    label="OA返工单"
                    rules={[{ required: true, message: '请选择返工单' }]}
                  >
                    <Select
                      showSearch
                      optionFilterProp="label"
                      loading={reworkLoading}
                      placeholder="选择已审批归档的返工单"
                      onChange={handleReworkSelect}
                      options={reworkOptions.map((item) => ({
                        value: String(item.request_id),
                        label: `${item.order_no || '-'} · ${item.product_code || '-'} · 行 ${
                          item.line_no || '1'
                        } · 不良 ${item.defect_qty ?? '-'} · 返工 ${item.rework_hours ?? 0}h · ${
                          item.apply_date || ''
                        }`,
                      }))}
                    />
                  </Form.Item>
                </Col>
                {selectedRework && (
                  <Col span={24}>
                    <Alert
                      type="info"
                      showIcon
                      message={`返工工时 ${selectedRework.rework_hours ?? 0} h · 不良数 ${
                        selectedRework.defect_qty ?? '-'
                      } · 行号 ${selectedRework.line_no || '1'} · ${
                        selectedRework.product_name || ''
                      }`}
                      style={{ marginBottom: 16 }}
                    />
                  </Col>
                )}
                <Col span={12}>
                  <Form.Item
                    name="order_no"
                    label="订单号"
                    rules={[{ required: true, message: '请输入订单号' }]}
                  >
                    <Input placeholder="OA 单缺少订单号时手工补" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="line_no"
                    label="行号"
                    rules={[{ required: true, message: '请输入行号' }]}
                  >
                    <Input placeholder="默认 1" />
                  </Form.Item>
                </Col>
              </>
            ) : (
              <>
                <Col span={12}>
                  <Form.Item name="order_no" label="订单号" rules={[{ required: true }]}>
                    <Input placeholder="返单可沿用原订单号" />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item
                    name="line_no"
                    label="行号"
                    rules={[{ required: true, message: '请输入行号' }]}
                  >
                    <Input placeholder="默认 1" />
                  </Form.Item>
                </Col>
              </>
            )}
            <Col span={8}>
              <Form.Item name="schedule_bucket" label="排产段" rules={[{ required: true }]}>
                <Select
                  options={[
                    { value: 'lean', label: '精益' },
                    { value: 'assembly', label: '装配-组装' },
                    { value: 'packaging', label: '装配-包装' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="target_date" label="开始日期" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="quantity" label="数量" rules={[{ required: true }]}>
                <InputNumber min={0} style={{ width: '100%' }} disabled={insertMode === 'order'} />
              </Form.Item>
            </Col>
            {insertMode !== 'rework' && (
              <Col span={8}>
                <Form.Item name="upph" label="UPPH" rules={[{ required: true }]}>
                  <InputNumber min={0} style={{ width: '100%' }} disabled={insertMode === 'order'} />
                </Form.Item>
              </Col>
            )}
            <Col span={8}>
              <Form.Item name="manpower" label="人数">
                <InputNumber min={1} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item
                name="product_code"
                label="产品编码"
                rules={
                  insertMode === 'manual' || insertMode === 'rework'
                    ? [{ required: true, message: '请输入产品编码' }]
                    : []
                }
              >
                <Input disabled={insertMode === 'order'} />
              </Form.Item>
            </Col>
            <Col span={16}>
              <Form.Item name="remark" label="备注">
                <Input placeholder="如：返单 / 返工批次" />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="allow_duplicate" valuePropName="checked">
                <Checkbox>允许同订单重复（返单/返工，不覆盖原计划）</Checkbox>
              </Form.Item>
            </Col>
          </Row>
          <Collapse
            ghost
            items={[
              {
                key: 'advanced',
                label: '更多设置（部门 / 工时 / 型号 / 负责人 / 破冻理由）',
                children: (
                  <Row gutter={16}>
                    <Col span={8}>
                      <Form.Item name="department" label="部门">
                        <Input />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="daily_work_hours" label="每日工时">
                        <InputNumber
                          min={1}
                          max={12}
                          style={{ width: '100%' }}
                          placeholder="默认基础条件"
                        />
                      </Form.Item>
                    </Col>
                    <Col span={8}>
                      <Form.Item name="model_code" label="型号">
                        <Input disabled={insertMode === 'order'} />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item name="owner" label="负责人">
                        <Input />
                      </Form.Item>
                    </Col>
                    <Col span={12}>
                      <Form.Item
                        name="break_frozen_reason"
                        label="破冻理由（插入或顺延进入 1-3 天冷冻区时必填）"
                      >
                        <Input />
                      </Form.Item>
                    </Col>
                  </Row>
                ),
              },
            ]}
          />
        </Form>
      </Modal>

      <Modal
        title={`拆单 · ${splitPlan?.order_no || ''} / ${splitPlan?.line_no || ''}`}
        open={splitOpen}
        destroyOnHidden
        width={720}
        okText="确认拆单"
        confirmLoading={splitting}
        onOk={handleSplit}
        onCancel={() => setSplitOpen(false)}
      >
        <Alert
          type="info"
          showIcon
          message="按数量拆成多批，每批可单独设置开始日期"
          description="批次数量合计不能超过当前计划数量；开始日期留空的批次视为「待定」，不会立即排产，保存后进入页面顶部的「待排余量」，确定日期后再补排。"
          style={{ marginBottom: 16 }}
        />
        <div style={{ marginBottom: 12, color: '#475569' }}>
          当前计划数量：{splitPlan?.quantity ?? '-'}，已拆：{splitTotalQty}
          <span style={{ marginLeft: 8, color: '#64748b' }}>
            （有日期 {splitDatedQty} / 待定 {splitUndatedQty}）
          </span>
          <span style={{ marginLeft: 8, color: splitRemainingQty < 0 ? '#ff4d4f' : '#64748b' }}>
            未分配：{splitRemainingQty}
          </span>
        </div>
        <Space wrap style={{ marginBottom: 12 }}>
          <span style={{ color: '#64748b' }}>均分为</span>
          <InputNumber
            min={2}
            max={Math.max(2, Math.floor(Number(splitPlan?.quantity || 2)))}
            value={splitCount}
            onChange={(value) => setSplitCount(Number(value) || 2)}
            style={{ width: 80 }}
          />
          <span style={{ color: '#64748b' }}>批</span>
          <Button onClick={handleEvenSplit}>重新均分</Button>
        </Space>
        <Form form={splitForm} layout="vertical">
          <Form.List name="batches">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field, index) => (
                  <Row gutter={12} key={field.key} align="middle">
                    <Col span={7}>
                      <Form.Item
                        name={[field.name, 'quantity']}
                        label={index === 0 ? '批次数量' : undefined}
                        rules={[{ required: true, message: '请输入数量' }]}
                      >
                        <InputNumber min={0} style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col span={10}>
                      <Form.Item
                        name={[field.name, 'target_date']}
                        label={index === 0 ? '开始日期' : undefined}
                      >
                        <DatePicker style={{ width: '100%' }} placeholder="留空 = 待定" />
                      </Form.Item>
                    </Col>
                    <Col span={4}>
                      <Button
                        danger
                        type="link"
                        icon={<DeleteOutlined />}
                        disabled={fields.length <= 1}
                        onClick={() => remove(field.name)}
                      />
                    </Col>
                  </Row>
                ))}
                <Button
                  type="dashed"
                  block
                  icon={<PlusOutlined />}
                  onClick={() => add({ quantity: 0, target_date: null })}
                  style={{ marginBottom: 16 }}
                >
                  添加批次
                </Button>
              </>
            )}
          </Form.List>
          <Form.Item name="push_conflicts" valuePropName="checked">
            <Checkbox>顺延同段后续计划</Checkbox>
          </Form.Item>
          <Form.Item
            name="break_frozen_reason"
            label="破冻理由（顺延进入 1-3 天冷冻区时必填）"
          >
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
