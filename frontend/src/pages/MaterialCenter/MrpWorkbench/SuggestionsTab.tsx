import { useCallback, useEffect, useState } from 'react'
import {
  Button, Input, Popconfirm, Popover, Row, Col, Select, Space, Table, Tag, Tooltip, Typography, message,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { ReloadOutlined } from '@ant-design/icons'
import type { Key } from 'react'
import { Link } from 'react-router-dom'
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

interface PeggingItem {
  sale_order_no: string
  line_no: string
  qty: number
}

interface RunOption {
  id: number
  run_no: string
  status: string
}

interface SuggestionRow {
  id: number
  run_id: number
  material_id: number
  material_code: string
  material_name: string | null
  bill_type: number
  suggest_qty: number
  need_date: string
  action_date: string | null
  suggested_supplier_id: number | null
  source: string
  status: string
  reviewed_by: string | null
  reviewed_at: string | null
  converted_target_type?: string | null
  converted_target_id?: number | null
  pegging: PeggingItem[] | null
  compare_status: string | null
  k3_qty: number | null
  k3_need_date: string | null
}

const BILL_TYPE_MAP: Record<number, { label: string; color: string }> = {
  11010: { label: '外购', color: 'blue' },
  11011: { label: '自制', color: 'purple' },
  11012: { label: '委外', color: 'orange' },
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  pending: { label: '待审核', color: 'processing' },
  approved: { label: '已通过', color: 'success' },
  rejected: { label: '已驳回', color: 'error' },
  converted: { label: '已转化', color: 'default' },
}

const SOURCE_MAP: Record<string, { label: string; color: string }> = {
  demand: { label: '需求缺口', color: 'blue' },
  safety_stock: { label: '安全库存', color: 'gold' },
}

const COMPARE_MAP: Record<string, { label: string; color: string }> = {
  match: { label: '匹配', color: 'success' },
  diff_qty: { label: '量差', color: 'warning' },
  diff_date: { label: '日期差', color: 'warning' },
  spc_only: { label: '仅 SPC', color: 'default' },
}

function fmtQty(v: number | null | undefined): string {
  if (v == null) return '-'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

export default function SuggestionsTab({ runId }: { runId: number | null }) {
  const hasPermission = useAuthStore((s) => s.hasPermission) as (resource: string, action: string) => boolean
  const canReview = hasPermission('materials.mrp', 'review')
  const canConvert = hasPermission('materials.mrp', 'convert')

  const [runOptions, setRunOptions] = useState<RunOption[]>([])
  const [selectedRunId, setSelectedRunId] = useState<number | null>(runId)
  const [status, setStatus] = useState<string>('')
  const [billType, setBillType] = useState<number | undefined>(undefined)
  const [keyword, setKeyword] = useState('')
  const [data, setData] = useState<SuggestionRow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])
  const [selectedRows, setSelectedRows] = useState<SuggestionRow[]>([])
  const [reviewing, setReviewing] = useState(false)
  const [converting, setConverting] = useState(false)

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
      const res = (await api.get('/mrp/suggestions', {
        params: {
          run_id: selectedRunId,
          ...(status ? { status } : {}),
          ...(billType ? { bill_type: billType } : {}),
          ...(keyword ? { keyword } : {}),
          page,
          page_size: pageSize,
        },
      })) as unknown as ApiResponse<PageData<SuggestionRow>>
      setData(res.data.items || [])
      setTotal(res.data.total || 0)
    } catch {
      // 全局拦截器已提示
    } finally {
      setLoading(false)
    }
  }, [selectedRunId, status, billType, keyword, page, pageSize])

  useEffect(() => { load() }, [load])

  const review = async (action: 'approve' | 'reject') => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先勾选建议')
      return
    }
    setReviewing(true)
    try {
      const res = (await api.post('/mrp/suggestions/batch-review', {
        suggestion_ids: selectedRowKeys.map(Number),
        action,
      })) as unknown as ApiResponse<{ updated: number; status: string }>
      message.success(`已${action === 'approve' ? '通过' : '驳回'} ${res.data.updated} 条建议`)
      setSelectedRowKeys([])
      setSelectedRows([])
      await load()
    } catch {
      // 全局拦截器已提示
    } finally {
      setReviewing(false)
    }
  }

  const canSelectRow = (row: SuggestionRow) =>
    (canReview && row.status === 'pending') ||
    (canConvert && row.bill_type === 11010 && row.status === 'approved')

  const convertibleSelection =
    selectedRows.length > 0 && selectedRows.every((r) => r.bill_type === 11010 && r.status === 'approved')

  const convertHint = selectedRows.length === 0
    ? '请先勾选建议'
    : '仅「已通过」的「外购」建议可转为采购申请单'

  const convert = async () => {
    if (selectedRowKeys.length === 0) {
      message.warning('请先勾选建议')
      return
    }
    setConverting(true)
    try {
      const res = (await api.post(
        '/mrp/suggestions/convert',
        { suggestion_ids: selectedRowKeys.map(Number) },
        { skipErrorToast: true },
      )) as unknown as ApiResponse<{ requisition_id: number; req_no: string; line_count: number }>
      message.success(`已生成 ${res.data.req_no}`)
      setSelectedRowKeys([])
      setSelectedRows([])
      await load()
    } catch (err) {
      const response = (err as { response?: { status?: number; data?: { detail?: string } } })?.response
      if (response?.status === 409) {
        message.error('状态已变化，请刷新')
      } else {
        message.error(response?.data?.detail || (err as Error)?.message || '转换为采购申请单失败')
      }
    } finally {
      setConverting(false)
    }
  }

  const columns: ColumnsType<SuggestionRow> = [
    {
      title: '物料编码', dataIndex: 'material_code', width: 150, ellipsis: true,
      render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    { title: '物料名称', dataIndex: 'material_name', width: 180, ellipsis: true },
    {
      title: '类型', dataIndex: 'bill_type', width: 80,
      render: (v: number) => {
        const m = BILL_TYPE_MAP[v] || { label: String(v), color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '建议量', dataIndex: 'suggest_qty', width: 100, align: 'right',
      render: (v: number) => fmtQty(v),
    },
    { title: '需求日', dataIndex: 'need_date', width: 110 },
    {
      title: '下单日', dataIndex: 'action_date', width: 110,
      render: (v: string | null) => v || '-',
    },
    {
      title: '来源', dataIndex: 'source', width: 100,
      render: (v: string) => {
        const m = SOURCE_MAP[v] || { label: v, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '状态', dataIndex: 'status', width: 150,
      render: (v: string, row: SuggestionRow) => {
        const m = STATUS_MAP[v] || { label: v, color: 'default' }
        if (v === 'converted' && row.converted_target_id != null) {
          return (
            <Space size={4}>
              <Tag color={m.color}>{m.label}</Tag>
              <Link to={`/purchase-requisitions/${row.converted_target_id}`}>查看申请单</Link>
            </Space>
          )
        }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: 'K3 对比', dataIndex: 'compare_status', width: 100,
      render: (v: string | null) => {
        if (!v) return '-'
        const m = COMPARE_MAP[v] || { label: v, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: '需求来源', dataIndex: 'pegging', width: 100,
      render: (v: PeggingItem[] | null) => {
        if (!v || v.length === 0) return '-'
        const content = (
          <div style={{ maxHeight: 240, overflowY: 'auto' }}>
            {v.map((p, i) => (
              <div key={i} style={{ fontSize: 12 }}>
                {p.sale_order_no}{p.line_no ? ` / ${p.line_no}` : ''} · {fmtQty(p.qty)}
              </div>
            ))}
          </div>
        )
        return <Popover content={content} title="来源订单" trigger="hover">{v.length} 条</Popover>
      },
    },
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
              placeholder="状态"
              value={status || undefined}
              onChange={(v) => { setStatus(v || ''); setPage(1) }}
              style={{ width: 110 }}
              allowClear
            >
              <Select.Option value="pending">待审核</Select.Option>
              <Select.Option value="approved">已通过</Select.Option>
              <Select.Option value="rejected">已驳回</Select.Option>
              <Select.Option value="converted">已转化</Select.Option>
            </Select>
          </Col>
          <Col>
            <Select
              placeholder="建议类型"
              value={billType}
              onChange={(v) => { setBillType(v); setPage(1) }}
              style={{ width: 110 }}
              allowClear
            >
              <Select.Option value={11010}>外购</Select.Option>
              <Select.Option value={11011}>自制</Select.Option>
              <Select.Option value={11012}>委外</Select.Option>
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
              <Button icon={<ReloadOutlined />} onClick={() => load()} loading={loading}>刷新</Button>
              {canReview && (
                <>
                  <Popconfirm
                    title={`确认批量通过已勾选的 ${selectedRowKeys.length} 条建议？`}
                    onConfirm={() => review('approve')}
                    disabled={selectedRowKeys.length === 0}
                  >
                    <Button type="primary" disabled={selectedRowKeys.length === 0} loading={reviewing}>批量通过</Button>
                  </Popconfirm>
                  <Popconfirm
                    title={`确认批量驳回已勾选的 ${selectedRowKeys.length} 条建议？`}
                    onConfirm={() => review('reject')}
                    disabled={selectedRowKeys.length === 0}
                  >
                    <Button danger disabled={selectedRowKeys.length === 0} loading={reviewing}>批量驳回</Button>
                  </Popconfirm>
                </>
              )}
              {canConvert && (
                <Tooltip title={convertibleSelection ? undefined : convertHint}>
                  <span style={{ display: 'inline-block' }}>
                    <Button
                      type="primary"
                      disabled={!convertibleSelection}
                      loading={converting}
                      onClick={convert}
                    >
                      转为采购申请单
                    </Button>
                  </span>
                </Tooltip>
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
          <Table<SuggestionRow>
            rowKey="id"
            dataSource={data}
            columns={columns}
            loading={loading}
            size="small"
            scroll={{ x: 1400 }}
            rowSelection={(canReview || canConvert) ? {
              selectedRowKeys,
              onChange: (keys, rows) => { setSelectedRowKeys(keys); setSelectedRows(rows) },
              getCheckboxProps: (row) => ({ disabled: !canSelectRow(row) }),
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
