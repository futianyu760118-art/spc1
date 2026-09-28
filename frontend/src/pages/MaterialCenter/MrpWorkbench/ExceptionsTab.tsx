import { useCallback, useEffect, useState } from 'react'
import {
  Button, Col, Dropdown, Input, Modal, Popconfirm, Row, Select, Space, Table, Tag, Typography, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DownOutlined, DownloadOutlined, ReloadOutlined } from '@ant-design/icons'
import type { Key } from 'react'
import api from '@/services/api'
import { useAuthStore } from '@/store/auth'
import { useExport } from '@/hooks/useExport'

interface PageData<T> {
  total: number
  page: number
  page_size: number
  items: T[]
}

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

interface RunOption {
  id: number
  run_no: string
  status: string
}

interface ExceptionRow {
  id: number
  run_id: number
  material_code: string
  material_name: string | null
  exception_code: number
  exception_type: string
  source_type: string
  source_doc_no: string | null
  source_line_no: string | null
  need_date: string | null
  doc_date: string | null
  adjust_days: number | null
  suggest_date: string | null
  suggest_qty: number | null
  detail: string | null
  status: string
}

interface BatchResult {
  updated: number
  skipped: { id: number; reason: string }[]
}

type BatchAction = 'ignore' | 'reschedule' | 'cancel_reduce' | 'notify'

const EXCEPTION_TYPE_MAP: Record<string, { label: string; color: string }> = {
  past_due_demand: { label: '拖期需求', color: 'red' },
  past_due_supply: { label: '拖期供给', color: 'volcano' },
  supply_late: { label: '建议提前', color: 'orange' },
  supply_early: { label: '建议延后', color: 'blue' },
  supply_excess: { label: '取消或减量', color: 'gold' },
  below_safety_stock: { label: '低于安全库存', color: 'magenta' },
  no_bom: { label: '无有效BOM', color: 'default' },
}

const SOURCE_TYPE_MAP: Record<string, string> = {
  po: '采购订单',
  task: '生产任务',
  subcontract: '委外',
  transfer: '调拨',
  requisition: '采购申请',
  sale_order_line: '销售订单',
  mrp_material: '物料',
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  open: { label: '待处理', color: 'processing' },
  resolved: { label: '已处理', color: 'success' },
  ignored: { label: '已忽略', color: 'default' },
}

const BATCH_ACTIONS: { key: BatchAction; label: string }[] = [
  { key: 'ignore', label: '忽略' },
  { key: 'reschedule', label: '改期' },
  { key: 'cancel_reduce', label: '取消或减量' },
]

const URGABLE_TYPES = ['past_due_supply', 'supply_late']

function fmtQty(v: number | null | undefined): string {
  if (v == null) return '-'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

function describeResult(result: BatchResult): { text: string; hasSkipped: boolean } {
  if (!result.skipped || result.skipped.length === 0) {
    return { text: `已处理 ${result.updated} 条`, hasSkipped: false }
  }
  const reasons = Array.from(new Set(result.skipped.map((s) => s.reason)))
  return {
    text: `已处理 ${result.updated} 条，跳过 ${result.skipped.length} 条：${reasons.join('；')}`,
    hasSkipped: true,
  }
}

export default function ExceptionsTab({ runId }: { runId: number | null }) {
  const hasPermission = useAuthStore((s) => s.hasPermission) as (resource: string, action: string) => boolean
  const canReview = hasPermission('materials.mrp', 'review')
  const { exporting, exportData } = useExport()

  const [runOptions, setRunOptions] = useState<RunOption[]>([])
  const [selectedRunId, setSelectedRunId] = useState<number | null>(runId)
  const [exceptionType, setExceptionType] = useState('')
  const [status, setStatus] = useState('')
  const [sourceType, setSourceType] = useState('')
  const [keyword, setKeyword] = useState('')
  const [data, setData] = useState<ExceptionRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])
  const [handling, setHandling] = useState(false)
  const [notifyingId, setNotifyingId] = useState<number | null>(null)

  useEffect(() => {
    if (runId != null) setSelectedRunId(runId)
  }, [runId])

  useEffect(() => {
    const loadRuns = async () => {
      try {
        const res = (await api.get('/mrp/runs', { params: { page: 1, page_size: 100 } })) as unknown as ApiResponse<PageData<RunOption>>
        const items = res.data.items || []
        setRunOptions(items)
        const firstSuccess = items.find((r) => r.status === 'success')
        setSelectedRunId((prev) => prev ?? (firstSuccess ? firstSuccess.id : null))
      } catch {
        // 全局拦截器已提示
      }
    }
    loadRuns()
  }, [])

  const load = useCallback(async () => {
    if (selectedRunId == null) return
    setLoading(true)
    try {
      const res = (await api.get('/mrp/exceptions', {
        params: {
          run_id: selectedRunId,
          ...(exceptionType ? { exception_type: exceptionType } : {}),
          ...(status ? { status } : {}),
          ...(sourceType ? { source_type: sourceType } : {}),
          ...(keyword ? { keyword } : {}),
          page,
          page_size: pageSize,
        },
      })) as unknown as ApiResponse<PageData<ExceptionRow>>
      setData(res.data.items || [])
      setTotal(res.data.total || 0)
    } catch {
      // 全局拦截器已提示
    } finally {
      setLoading(false)
    }
  }, [selectedRunId, exceptionType, status, sourceType, keyword, page, pageSize])

  useEffect(() => { load() }, [load])

  const handleExport = () => {
    if (selectedRunId == null) return
    exportData('/api/v1/mrp/exceptions/export', {
      run_id: selectedRunId,
      ...(exceptionType ? { exception_type: exceptionType } : {}),
      ...(status ? { status } : {}),
      ...(sourceType ? { source_type: sourceType } : {}),
      ...(keyword ? { keyword } : {}),
    }, 'MRP例外清单.csv')
  }

  const callBatch = async (action: BatchAction, ids: number[]): Promise<BatchResult> => {
    const res = (await api.post('/mrp/exceptions/batch-handle', {
      exception_ids: ids,
      action,
    })) as unknown as ApiResponse<BatchResult>
    return res.data
  }

  const runBatch = async (action: BatchAction) => {
    setHandling(true)
    try {
      const result = await callBatch(action, selectedRowKeys.map(Number))
      const { text, hasSkipped } = describeResult(result)
      if (hasSkipped) message.warning(text)
      else message.success(text)
      setSelectedRowKeys([])
      await load()
    } catch {
      // 全局拦截器已提示
    } finally {
      setHandling(false)
    }
  }

  const confirmBatch = (action: BatchAction) => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先勾选例外')
      return
    }
    const label = BATCH_ACTIONS.find((a) => a.key === action)?.label || action
    Modal.confirm({
      title: `确认对已勾选的 ${selectedRowKeys.length} 条例外执行「${label}」？`,
      onOk: () => runBatch(action),
    })
  }

  const notify = async (row: ExceptionRow) => {
    setNotifyingId(row.id)
    try {
      const result = await callBatch('notify', [row.id])
      const { text, hasSkipped } = describeResult(result)
      if (hasSkipped) message.warning(text)
      else message.success('已标记催货')
      await load()
    } catch {
      // 全局拦截器已提示
    } finally {
      setNotifyingId(null)
    }
  }

  const columns: ColumnsType<ExceptionRow> = [
    {
      title: '物料编码', dataIndex: 'material_code', width: 140, ellipsis: true,
      render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    {
      title: '物料名称', dataIndex: 'material_name', width: 160, ellipsis: true,
      render: (v: string | null) => v || '-',
    },
    {
      title: '类型', dataIndex: 'exception_type', width: 140,
      render: (v: string, row) => {
        const m = EXCEPTION_TYPE_MAP[v] || { label: v, color: 'default' }
        return (
          <Space size={4}>
            <Tag color={m.color}>{m.label}</Tag>
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>{row.exception_code}</Typography.Text>
          </Space>
        )
      },
    },
    {
      title: '源单据', key: 'source', width: 190, ellipsis: true,
      render: (_, row) => {
        const label = SOURCE_TYPE_MAP[row.source_type] || row.source_type
        return row.source_doc_no ? `${label} · ${row.source_doc_no}` : label
      },
    },
    { title: '需求日', dataIndex: 'need_date', width: 105, render: (v: string | null) => v || '-' },
    { title: '单据日期', dataIndex: 'doc_date', width: 105, render: (v: string | null) => v || '-' },
    {
      title: '调整天数', dataIndex: 'adjust_days', width: 90, align: 'right',
      render: (v: number | null) => {
        if (v == null) return '-'
        if (v === 0) return '0'
        return <span style={{ color: v < 0 ? '#cf1322' : '#d46b08' }}>{v > 0 ? `+${v}` : v}</span>
      },
    },
    { title: '建议日期', dataIndex: 'suggest_date', width: 105, render: (v: string | null) => v || '-' },
    { title: '建议数量', dataIndex: 'suggest_qty', width: 100, align: 'right', render: (v: number | null) => fmtQty(v) },
    { title: '描述', dataIndex: 'detail', width: 260, ellipsis: true, render: (v: string | null) => v || '-' },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: string) => {
        const m = STATUS_MAP[v] || { label: v, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    ...(canReview ? [{
      title: '操作', key: 'action', width: 100, fixed: 'right' as const,
      render: (_: unknown, row: ExceptionRow) => {
        if (row.status !== 'open' || !URGABLE_TYPES.includes(row.exception_type)) return '-'
        return (
          <Popconfirm title="确认将该例外标记为已催货？" onConfirm={() => notify(row)}>
            <Button type="link" size="small" loading={notifyingId === row.id}>标记催货</Button>
          </Popconfirm>
        )
      },
    }] : []),
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Row gutter={12} align="middle">
          <Col>
            <Select
              placeholder="运算批次"
              value={selectedRunId ?? undefined}
              onChange={(v) => { setSelectedRunId(v ?? null); setPage(1) }}
              style={{ width: 260 }}
              options={runOptions.map((r) => ({
                value: r.id,
                label: `${r.run_no}${r.status === 'success' ? '' : `（${r.status}）`}`,
              }))}
            />
          </Col>
          <Col>
            <Select
              placeholder="例外类型"
              value={exceptionType || undefined}
              onChange={(v) => { setExceptionType(v || ''); setPage(1) }}
              style={{ width: 140 }}
              allowClear
            >
              {Object.entries(EXCEPTION_TYPE_MAP).map(([value, m]) => (
                <Select.Option key={value} value={value}>{m.label}</Select.Option>
              ))}
            </Select>
          </Col>
          <Col>
            <Select
              placeholder="状态"
              value={status || undefined}
              onChange={(v) => { setStatus(v || ''); setPage(1) }}
              style={{ width: 110 }}
              allowClear
            >
              <Select.Option value="open">待处理</Select.Option>
              <Select.Option value="resolved">已处理</Select.Option>
              <Select.Option value="ignored">已忽略</Select.Option>
            </Select>
          </Col>
          <Col>
            <Select
              placeholder="源单据类型"
              value={sourceType || undefined}
              onChange={(v) => { setSourceType(v || ''); setPage(1) }}
              style={{ width: 130 }}
              allowClear
            >
              {Object.entries(SOURCE_TYPE_MAP).map(([value, label]) => (
                <Select.Option key={value} value={value}>{label}</Select.Option>
              ))}
            </Select>
          </Col>
          <Col>
            <Input.Search
              placeholder="物料编码/名称"
              style={{ width: 200 }}
              allowClear
              onSearch={(v) => { setKeyword(v.trim()); setPage(1) }}
            />
          </Col>
          <Col flex="auto" />
          <Col>
            <Space>
              <Button icon={<DownloadOutlined />} onClick={handleExport} loading={exporting} disabled={selectedRunId == null}>导出</Button>
              <Button icon={<ReloadOutlined />} onClick={() => load()} loading={loading}>刷新</Button>
              {canReview && (
                <Dropdown
                  menu={{
                    items: BATCH_ACTIONS.map((a) => ({ key: a.key, label: a.label })),
                    onClick: ({ key }) => confirmBatch(key as BatchAction),
                  }}
                  disabled={selectedRowKeys.length === 0}
                >
                  <Button type="primary" disabled={selectedRowKeys.length === 0} loading={handling}>
                    批量处理 <DownOutlined />
                  </Button>
                </Dropdown>
              )}
            </Space>
          </Col>
        </Row>
      </div>

      {selectedRunId == null ? (
        <div className="card-modern" style={{ padding: 40, textAlign: 'center' }}>
          <Typography.Text type="secondary">暂无成功的运算批次，请先在「运算批次」触发一次运算</Typography.Text>
        </div>
      ) : (
        <div className="card-modern" style={{ padding: '0 0 4px' }}>
          <Table<ExceptionRow>
            rowKey="id"
            dataSource={data}
            columns={columns}
            loading={loading}
            size="small"
            scroll={{ x: 1580 }}
            rowSelection={canReview ? {
              selectedRowKeys,
              onChange: (keys) => setSelectedRowKeys(keys),
              getCheckboxProps: (row) => ({ disabled: row.status !== 'open' }),
            } : undefined}
            pagination={{
              total, current: page, pageSize,
              showSizeChanger: true, showTotal: (t) => `共 ${t} 条`,
            }}
            onChange={(pagination) => {
              setPage(pagination.current || 1)
              setPageSize(pagination.pageSize || 20)
            }}
          />
        </div>
      )}
    </div>
  )
}
