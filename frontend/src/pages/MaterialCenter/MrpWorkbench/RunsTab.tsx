import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Button, Descriptions, Form, Input, Modal, Radio, Select, Space, Spin, Table, Tag, Typography, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { PlayCircleOutlined, ReloadOutlined } from '@ant-design/icons'
import api from '@/services/api'
import { useAuthStore } from '@/store/auth'

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

interface ComparisonSummary {
  match?: number
  diff_qty?: number
  diff_date?: number
  spc_only?: number
  k3_only?: number
  match_rate?: number
  error?: string
}

interface RunStats {
  demand_lines?: number
  materials_processed?: number
  buckets?: number
  suggestions?: number
  duration_sec?: number
  data_issues?: Record<string, unknown> | null
  comparison?: ComparisonSummary | null
}

interface RunDetailState {
  loading: boolean
  loaded: boolean
  stats: RunStats | null
}

interface RunRow {
  id: number
  run_no: string
  run_type: string
  triggered_by: string | null
  status: string
  horizon_days: number
  stats: RunStats | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

type ScopeType = 'all' | 'sale_order_no' | 'material_codes'

interface TriggerFormValues {
  scope: ScopeType
  sale_order_no?: string
  material_codes?: string[]
}

const RUN_TYPE_MAP: Record<string, { label: string; color: string }> = {
  scheduled: { label: '定时', color: 'geekblue' },
  manual: { label: '手动', color: 'purple' },
}

const RUN_STATUS_MAP: Record<string, { label: string; color: string }> = {
  running: { label: '运算中', color: 'processing' },
  success: { label: '成功', color: 'success' },
  failed: { label: '失败', color: 'error' },
}

function fmtTime(v: string | null): string {
  return v ? new Date(v).toLocaleString('zh-CN') : '-'
}

function renderStats(stats: RunStats | null): string {
  if (!stats) return '-'
  const parts: string[] = []
  if (stats.suggestions != null) parts.push(`建议 ${stats.suggestions} 条`)
  if (stats.duration_sec != null) parts.push(`耗时 ${stats.duration_sec}s`)
  return parts.length ? parts.join(' · ') : '-'
}

const DATA_ISSUE_LABELS: Record<string, string> = {
  demand_without_bom: '需求行缺BOM',
  no_bom: '无有效BOM',
  material_property_missing: '物料属性缺失',
  bom_cycle: 'BOM环路',
  subcontract_date_approx: '委外日期近似',
  param_fallback: '参数回退统计',
}

function issueLabel(key: string): string {
  return DATA_ISSUE_LABELS[key] || key
}

function fmtIssueValue(value: unknown): string {
  if (value == null) return '-'
  if (typeof value === 'number') return String(value)
  if (Array.isArray(value)) return `${value.length} 项`
  if (typeof value === 'object') return `${Object.keys(value as Record<string, unknown>).length} 项`
  return String(value)
}

function fmtDataIssue(key: string, value: unknown): string {
  if (key === 'param_fallback' && value != null && typeof value === 'object' && !Array.isArray(value)) {
    const stat = value as Record<string, unknown>
    return `参数回退：共 ${stat.total ?? '-'} / 已配置 ${stat.configured ?? '-'} / 历史推导 ${stat.derived ?? '-'} / 默认 ${stat.default ?? '-'}`
  }
  return `${issueLabel(key)}：${fmtIssueValue(value)}`
}

export default function RunsTab({ onOpenRun }: { onOpenRun: (runId: number) => void }) {
  const hasPermission = useAuthStore((s) => s.hasPermission) as (resource: string, action: string) => boolean
  const canRun = hasPermission('materials.mrp', 'run')

  const [data, setData] = useState<RunRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [triggerOpen, setTriggerOpen] = useState(false)
  const [triggering, setTriggering] = useState(false)
  const [form] = Form.useForm<TriggerFormValues>()
  const scope = Form.useWatch('scope', form) as ScopeType | undefined

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    try {
      const res = (await api.get('/mrp/runs', { params: { page, page_size: pageSize } })) as unknown as ApiResponse<PageData<RunRow>>
      setData(res.data.items || [])
      setTotal(res.data.total || 0)
    } catch {
      // 全局拦截器已提示
    } finally {
      if (!silent) setLoading(false)
    }
  }, [page, pageSize])

  useEffect(() => { load() }, [load])

  const hasRunning = data.some((row) => row.status === 'running')
  useEffect(() => {
    if (!hasRunning) return
    const timer = setInterval(() => { load(true) }, 5000)
    return () => clearInterval(timer)
  }, [hasRunning, load])

  const [runDetails, setRunDetails] = useState<Record<number, RunDetailState>>({})
  const requestedRunIds = useRef<Set<number>>(new Set())

  const fetchRunDetail = useCallback(async (runId: number) => {
    if (requestedRunIds.current.has(runId)) return
    requestedRunIds.current.add(runId)
    setRunDetails((prev) => ({ ...prev, [runId]: { loading: true, loaded: false, stats: prev[runId]?.stats ?? null } }))
    try {
      const res = (await api.get(`/mrp/runs/${runId}`)) as unknown as ApiResponse<RunRow>
      setRunDetails((prev) => ({ ...prev, [runId]: { loading: false, loaded: true, stats: res.data.stats ?? null } }))
    } catch {
      requestedRunIds.current.delete(runId)
      setRunDetails((prev) => ({ ...prev, [runId]: { loading: false, loaded: false, stats: null } }))
    }
  }, [])

  const submitTrigger = async () => {
    const values = await form.validateFields()
    setTriggering(true)
    try {
      const payload: Record<string, unknown> = { scope: values.scope }
      if (values.scope === 'sale_order_no') payload.sale_order_no = (values.sale_order_no || '').trim()
      if (values.scope === 'material_codes') payload.material_codes = values.material_codes || []
      const res = (await api.post('/mrp/runs', payload)) as unknown as ApiResponse<{ run_id: number; run_no: string; status: string }>
      message.success(`已触发运算：${res.data.run_no}`)
      setTriggerOpen(false)
      await load()
    } catch (e) {
      const status = (e as { response?: { status?: number } })?.response?.status
      if (status === 409) message.error('MRP 正在运算中')
      // 其余错误由全局拦截器提示
    } finally {
      setTriggering(false)
    }
  }

  const renderExpandedRow = (row: RunRow) => {
    const detail = runDetails[row.id]
    const stats = detail?.loaded ? (detail.stats ?? row.stats) : null
    const issueEntries = stats?.data_issues ? Object.entries(stats.data_issues) : []
    const comparison = stats?.comparison ?? null

    return (
      <div>
        {row.error_message && (
          <Typography.Paragraph style={{ margin: '0 0 12px', whiteSpace: 'pre-wrap' }}>
            {row.error_message}
          </Typography.Paragraph>
        )}
        {detail?.loading && <Spin size="small" />}
        {!detail?.loading && !detail?.loaded && (
          <Space>
            <Typography.Text type="secondary">统计数据加载失败</Typography.Text>
            <Button type="link" size="small" onClick={() => { void fetchRunDetail(row.id) }}>重试</Button>
          </Space>
        )}
        {detail?.loaded && !stats && <Typography.Text type="secondary">暂无统计数据</Typography.Text>}
        {detail?.loaded && stats && (
          <>
            <Descriptions size="small" column={5} title="统计" style={{ marginBottom: 8 }}>
              <Descriptions.Item label="建议数">{stats.suggestions ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="桶数">{stats.buckets ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="需求行数">{stats.demand_lines ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="物料数">{stats.materials_processed ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="耗时">{stats.duration_sec != null ? `${stats.duration_sec}s` : '-'}</Descriptions.Item>
            </Descriptions>
            <div style={{ marginBottom: comparison ? 12 : 0 }}>
              <Typography.Text strong>数据体检</Typography.Text>
              <div style={{ marginTop: 6 }}>
                {issueEntries.length ? (
                  <Space size={[8, 8]} wrap>
                    {issueEntries.map(([key, value]) => (
                      <Tag key={key}>{fmtDataIssue(key, value)}</Tag>
                    ))}
                  </Space>
                ) : (
                  <Typography.Text type="secondary">无体检项</Typography.Text>
                )}
              </div>
            </div>
            {comparison && (
              comparison.error ? (
                <Typography.Text type="secondary">K3 对比失败：{comparison.error}</Typography.Text>
              ) : (
                <Descriptions size="small" column={6} title="K3 对比">
                  <Descriptions.Item label="匹配">{comparison.match ?? '-'}</Descriptions.Item>
                  <Descriptions.Item label="数量差异">{comparison.diff_qty ?? '-'}</Descriptions.Item>
                  <Descriptions.Item label="日期差异">{comparison.diff_date ?? '-'}</Descriptions.Item>
                  <Descriptions.Item label="仅 SPC">{comparison.spc_only ?? '-'}</Descriptions.Item>
                  <Descriptions.Item label="仅 K3">{comparison.k3_only ?? '-'}</Descriptions.Item>
                  <Descriptions.Item label="匹配率">
                    {comparison.match_rate != null ? `${comparison.match_rate}%` : '-'}
                  </Descriptions.Item>
                </Descriptions>
              )
            )}
          </>
        )}
      </div>
    )
  }

  const columns: ColumnsType<RunRow> = [
    {
      title: '批次号', dataIndex: 'run_no', width: 190,
      render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    {
      title: '类型', dataIndex: 'run_type', width: 80,
      render: (v: string) => {
        const m = RUN_TYPE_MAP[v] || { label: v, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '状态', dataIndex: 'status', width: 90,
      render: (v: string) => {
        const m = RUN_STATUS_MAP[v] || { label: v, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '触发人', dataIndex: 'triggered_by', width: 100,
      render: (v: string | null) => v || '-',
    },
    {
      title: '展望期', dataIndex: 'horizon_days', width: 90,
      render: (v: number) => `${v} 天`,
    },
    {
      title: '统计摘要', dataIndex: 'stats', width: 180,
      render: (v: RunStats | null) => renderStats(v),
    },
    {
      title: '开始时间', dataIndex: 'started_at', width: 170,
      render: (v: string | null) => fmtTime(v),
    },
    {
      title: '结束时间', dataIndex: 'finished_at', width: 170,
      render: (v: string | null) => fmtTime(v),
    },
    {
      title: '操作', width: 100, fixed: 'right',
      render: (_, row) => (
        <Button type="link" size="small" onClick={() => onOpenRun(row.id)}>查看平衡</Button>
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Space>
          {canRun && (
            <Button type="primary" icon={<PlayCircleOutlined />} onClick={() => setTriggerOpen(true)}>
              手动触发
            </Button>
          )}
          <Button icon={<ReloadOutlined />} onClick={() => load()} loading={loading}>刷新</Button>
          {hasRunning && <Typography.Text type="secondary">存在运算中的批次，每 5 秒自动刷新</Typography.Text>}
        </Space>
      </div>

      <div className="card-modern" style={{ padding: '0 0 4px' }}>
        <Table<RunRow>
          rowKey="id"
          dataSource={data}
          columns={columns}
          loading={loading}
          size="small"
          scroll={{ x: 1200 }}
          pagination={{
            total, current: page, pageSize,
            showSizeChanger: true, showTotal: (t) => `共 ${t} 条`,
          }}
          onChange={(pagination) => {
            setPage(pagination.current || 1)
            setPageSize(pagination.pageSize || 20)
          }}
          expandable={{
            onExpand: (expanded, row) => {
              if (expanded) void fetchRunDetail(row.id)
            },
            expandedRowRender: renderExpandedRow,
          }}
        />
      </div>

      <Modal
        title="手动触发 MRP 运算"
        open={triggerOpen}
        onCancel={() => setTriggerOpen(false)}
        onOk={submitTrigger}
        confirmLoading={triggering}
        okText="触发运算"
        cancelText="取消"
        afterClose={() => form.resetFields()}
      >
        <Form form={form} layout="vertical" initialValues={{ scope: 'all' }}>
          <Form.Item name="scope" label="运算范围">
            <Radio.Group>
              <Radio value="all">全部</Radio>
              <Radio value="sale_order_no">按销售订单号</Radio>
              <Radio value="material_codes">按物料编码</Radio>
            </Radio.Group>
          </Form.Item>
          {scope === 'sale_order_no' && (
            <Form.Item name="sale_order_no" label="销售订单号" rules={[{ required: true, message: '请输入销售订单号' }]}>
              <Input placeholder="请输入销售订单号" allowClear />
            </Form.Item>
          )}
          {scope === 'material_codes' && (
            <Form.Item name="material_codes" label="物料编码" rules={[{ required: true, message: '请输入至少一个物料编码' }]}>
              <Select
                mode="tags"
                placeholder="输入物料编码后回车，可输入多个"
                tokenSeparators={[',', ' ', '，']}
              />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  )
}
