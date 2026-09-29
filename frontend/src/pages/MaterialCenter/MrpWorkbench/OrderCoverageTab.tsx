import { useMemo, useState } from 'react'
import { Alert, Button, Col, Input, Row, Space, Spin, Table, Tag, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { SearchOutlined } from '@ant-design/icons'
import api from '@/services/api'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

interface SupplyItem {
  source_type: string
  doc_no: string
  line_no: string | null
  qty: number
  date: string | null
  used: number
}

interface CoverageLine {
  line_no: string
  product_code: string | null
  product_name: string | null
  material_id: number | null
  material_code: string | null
  qty: number
  need_date: string | null
  bom_id: string | null
  supplies: SupplyItem[]
  covered_qty: number
  shortage_qty: number
  status: string
}

interface CoverageOrder {
  order_no: string
  lines: number
  total_qty: number
  promised_date: string | null
  status: string
}

interface CoverageResult {
  order: CoverageOrder | null
  lines: CoverageLine[]
  note: string
}

type SegmentKey = 'inventory' | 'task' | 'po' | 'other' | 'gap'

interface CoverageSegments {
  inventory: number
  task: number
  po: number
  other: number
  gap: number
}

interface CoverageSummary {
  segments: CoverageSegments
  covered: number
  shortage: number
}

const CASE_ORDERS = ['HJ202609-0025-0215', 'HJ202609-0017-0207']

const DETAIL_PREVIEW = 10

const SUPPLY_SHORT_LABEL: Record<string, string> = {
  inventory: '库存',
  task: '任务',
  po: '采购',
  subcontract: '委外',
  transfer: '调拨',
  requisition: '申请',
}

const SUPPLY_TAG_MAP: Record<string, { label: string; color: string }> = {
  inventory: { label: '库存', color: 'success' },
  task: { label: '生产任务', color: 'processing' },
  po: { label: '采购订单', color: 'cyan' },
  subcontract: { label: '委外', color: 'purple' },
  transfer: { label: '调拨', color: 'gold' },
  requisition: { label: '申请单', color: 'default' },
}

const SEGMENT_DEFS: { key: SegmentKey; label: string; color: string }[] = [
  { key: 'inventory', label: '库存', color: '#16a34a' },
  { key: 'task', label: '任务', color: '#5b5bd6' },
  { key: 'po', label: '采购在途', color: '#0891b2' },
  { key: 'other', label: '其他', color: '#64748b' },
  { key: 'gap', label: '缺口', color: '#dc2626' },
]

const LINE_STATUS_MAP: Record<string, { label: string; color: string }> = {
  covered: { label: '已覆盖', color: 'success' },
  partial: { label: '部分覆盖', color: 'warning' },
  short: { label: '缺口', color: 'error' },
}

const ORDER_STATUS_MAP: Record<string, { label: string; color: string }> = {
  covered: { label: '已全部覆盖', color: 'success' },
  partial: { label: '部分覆盖', color: 'warning' },
  short: { label: '存在缺口', color: 'error' },
}

function fmtQty(v: number | null | undefined): string {
  if (v == null) return '—'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

function segmentKeyOf(sourceType: string): SegmentKey {
  if (sourceType === 'inventory') return 'inventory'
  if (sourceType === 'task') return 'task'
  if (sourceType === 'po') return 'po'
  return 'other'
}

function buildSummary(result: CoverageResult): CoverageSummary {
  const segments: CoverageSegments = { inventory: 0, task: 0, po: 0, other: 0, gap: 0 }
  let shortage = 0
  result.lines.forEach((line) => {
    const usedSupplies = (line.supplies || []).filter((s) => (Number(s.used) || 0) > 0)
    usedSupplies.forEach((s) => {
      segments[segmentKeyOf(s.source_type)] += Number(s.used) || 0
    })
    shortage += Number(line.shortage_qty) || 0
  })
  segments.gap = shortage
  return { segments, covered: (result.order?.total_qty || 0) - shortage, shortage }
}

function supplySummary(supplies: SupplyItem[]): string {
  const used = supplies.filter((s) => (Number(s.used) || 0) > 0)
  if (!used.length) return '—'
  const parts = used.slice(0, 2).map((s) =>
    s.source_type === 'inventory'
      ? `库存×${fmtQty(s.used)}`
      : `${SUPPLY_SHORT_LABEL[s.source_type] || s.source_type} ${s.doc_no || '—'}×${fmtQty(s.used)}`
  )
  return used.length > 2 ? `${parts.join('、')} 等 ${used.length} 条` : parts.join('、')
}

function coverConclusion(line: CoverageLine): string {
  const docCount = (line.supplies || []).filter((s) => (Number(s.used) || 0) > 0).length
  if (line.shortage_qty > 0 && line.covered_qty > 0) {
    return `本行已有 ${fmtQty(line.covered_qty)} 件被覆盖，仍缺 ${fmtQty(line.shortage_qty)} 件，请到「缺口与建议」查看补货建议`
  }
  if (line.shortage_qty > 0) {
    return `库存与在途均无 → 缺 ${fmtQty(line.shortage_qty)}，请到「缺口与建议」查看补货建议`
  }
  return `本行 ${fmtQty(line.qty)} 件已被 ${docCount} 张单据覆盖，无需新增计划`
}

const LINE_COLUMNS: ColumnsType<CoverageLine> = [
  {
    title: '序号', width: 48, align: 'right',
    render: (_: unknown, __: CoverageLine, index: number) => (
      <span className="sc-mono" style={{ color: '#94a3b8' }}>{index + 1}</span>
    ),
  },
  {
    title: '产品', dataIndex: 'product_code', width: 260,
    render: (_: string | null, row: CoverageLine) => (
      <div>
        <div className="sc-mono" style={{ fontSize: 12.5, fontWeight: 600 }}>{row.product_code || row.material_code || '—'}</div>
        <div className="sc-sub">{row.product_name || '—'}</div>
      </div>
    ),
  },
  {
    title: '需求', dataIndex: 'qty', width: 90, align: 'right',
    render: (v: number) => <b className="sc-mono">{fmtQty(v)}</b>,
  },
  {
    title: '交期', dataIndex: 'need_date', width: 110,
    render: (v: string | null) => (v ? <span className="sc-mono">{v}</span> : '—'),
  },
  {
    title: '覆盖状态', dataIndex: 'status', width: 100,
    render: (v: string) => {
      const m = LINE_STATUS_MAP[v] || { label: v, color: 'default' }
      return <Tag color={m.color}>{m.label}</Tag>
    },
  },
  {
    title: '覆盖来源', dataIndex: 'supplies', width: 380, ellipsis: true,
    render: (v: SupplyItem[]) => (
      <span style={{ color: '#475569', fontSize: 12.5 }}>{supplySummary(v || [])}</span>
    ),
  },
  {
    title: '缺口数量', dataIndex: 'shortage_qty', width: 100, align: 'right',
    render: (v: number) => (v > 0
      ? <b className="sc-mono" style={{ color: '#dc2626' }}>{fmtQty(v)}</b>
      : <span className="sc-sub">0</span>),
  },
]

const SUPPLY_DETAIL_COLUMNS: ColumnsType<SupplyItem> = [
  {
    title: '供给类型', dataIndex: 'source_type', width: 120,
    render: (v: string) => {
      const m = SUPPLY_TAG_MAP[v] || { label: v, color: 'default' }
      return <Tag color={m.color}>{m.label}</Tag>
    },
  },
  {
    title: '单号', dataIndex: 'doc_no', width: 240,
    render: (v: string, row: SupplyItem) => (
      <span className="sc-mono" style={{ fontSize: 12 }}>
        {v || '—'}{row.line_no ? ` · 行 ${row.line_no}` : ''}
      </span>
    ),
  },
  {
    title: '数量', dataIndex: 'qty', width: 120, align: 'right',
    render: (v: number) => <span className="sc-mono">{fmtQty(v)}</span>,
  },
  {
    title: '日期', dataIndex: 'date', width: 120,
    render: (v: string | null) => (v ? <span className="sc-mono" style={{ fontSize: 12 }}>{v}</span> : '—'),
  },
  {
    title: '本行占用', dataIndex: 'used', width: 120, align: 'right',
    render: (v: number) => (v > 0
      ? <b className="sc-mono">{fmtQty(v)}</b>
      : <span className="sc-sub">0</span>),
  },
]

function CoverageBar({ segments, total }: { segments: CoverageSegments; total: number }) {
  const base = total > 0 ? total : 1
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ display: 'flex', height: 10, borderRadius: 999, overflow: 'hidden', background: '#f1f5f9' }}>
        {SEGMENT_DEFS.map((def) => {
          const value = segments[def.key]
          if (value <= 0) return null
          return (
            <i
              key={def.key}
              title={`${def.label} ${fmtQty(value)}`}
              style={{ display: 'block', height: '100%', width: `${(value / base) * 100}%`, background: def.color }}
            />
          )
        })}
      </div>
      <div style={{
        display: 'flex', gap: 16, flexWrap: 'wrap', marginTop: 7,
        fontSize: 11.5, color: '#475569', fontVariantNumeric: 'tabular-nums',
      }}>
        {SEGMENT_DEFS.map((def) => (
          <span key={def.key} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
            <i style={{ display: 'inline-block', width: 8, height: 8, borderRadius: 2, background: def.color }} />
            {def.label}
            <b style={{ color: def.key === 'gap' && segments.gap > 0 ? '#dc2626' : '#0f172a' }}>
              {fmtQty(segments[def.key])}
            </b>
          </span>
        ))}
      </div>
    </div>
  )
}

function SupplyDetailTable({ supplies }: { supplies: SupplyItem[] }) {
  const [showAll, setShowAll] = useState(false)
  const sorted = useMemo(
    () => [...supplies].sort((a, b) => (Number(b.used) || 0) - (Number(a.used) || 0)),
    [supplies]
  )
  const rows = showAll ? sorted : sorted.slice(0, DETAIL_PREVIEW)
  return (
    <>
      <div style={{ border: '1px solid #e2e8f0', borderRadius: 8, overflow: 'hidden', background: '#fff', maxWidth: 880 }}>
        <Table<SupplyItem>
          rowKey={(r) => `${r.source_type}-${r.doc_no}-${r.line_no ?? ''}`}
          dataSource={rows}
          columns={SUPPLY_DETAIL_COLUMNS}
          size="small"
          pagination={false}
          locale={{ emptyText: '无任何在途 / 库存供给' }}
        />
      </div>
      {sorted.length > DETAIL_PREVIEW && (
        <Button
          type="link"
          size="small"
          style={{ paddingLeft: 0 }}
          onClick={() => setShowAll((v) => !v)}
        >
          {showAll ? '收起' : `展开全部（共 ${sorted.length} 条）`}
        </Button>
      )}
    </>
  )
}

function LineDetail({ line, note }: { line: CoverageLine; note: string }) {
  return (
    <div style={{ padding: '2px 0' }}>
      <SupplyDetailTable supplies={line.supplies || []} />
      <div style={{ fontSize: 12, color: '#475569', lineHeight: 1.7, margin: '10px 0 6px', maxWidth: 880 }}>
        <b style={{ color: '#0f172a', marginRight: 6 }}>结论</b>{coverConclusion(line)}
      </div>
      <div className="sc-sub" style={{ fontSize: 11, lineHeight: 1.7 }}>口径：{note}</div>
    </div>
  )
}

export default function OrderCoverageTab() {
  const [orderNo, setOrderNo] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<CoverageResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const order = result?.order ?? null
  const lines = result?.lines ?? []
  const note = result?.note ?? ''
  const summary = useMemo(() => (result ? buildSummary(result) : null), [result])

  const search = async (no?: string) => {
    const target = (no ?? orderNo).trim()
    if (!target) {
      message.warning('请输入销售订单号')
      return
    }
    setOrderNo(target)
    setLoading(true)
    setError(null)
    try {
      const res = (await api.get('/mrp/order-coverage', {
        params: { order_no: target },
        skipErrorToast: true,
      })) as unknown as ApiResponse<CoverageResult>
      setResult(res.data)
    } catch (e) {
      const response = (e as { response?: { status?: number } })?.response
      const msg = response?.status === 404
        ? '订单不存在或无未结行'
        : ((e as Error)?.message || '查询订单覆盖失败')
      if (response?.status === 404) {
        message.warning(msg)
      } else {
        message.error(msg)
      }
      setResult(null)
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  const orderStatus = order
    ? (ORDER_STATUS_MAP[order.status] || { label: order.status, color: 'default' })
    : null

  return (
    <div>
      <Alert
        type="info"
        showIcon
        message={<><b>怎么看：</b>输入销售订单号，逐个物料看：需求被哪些已有单据（库存 / 采购在途 / 生产任务）覆盖、还缺多少。0 条建议＝每行都被覆盖。</>}
        style={{ marginBottom: 12 }}
      />

      <div className="sc-card" style={{ padding: '14px 16px', marginBottom: 14 }}>
        <Space wrap>
          <Input
            placeholder="输入订单号，如 HJ202609-0025-0215"
            style={{ width: 360 }}
            value={orderNo}
            allowClear
            onChange={(e) => setOrderNo(e.target.value)}
            onPressEnter={() => search()}
          />
          <Button type="primary" icon={<SearchOutlined />} loading={loading} onClick={() => search()}>查询</Button>
          <span className="sc-sub">覆盖来源：即时库存 / 未结采购 / 未结生产任务；缺口行为红色</span>
        </Space>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 12 }}>
          {CASE_ORDERS.map((no) => (
            <span
              key={no}
              className={`sc-chip${orderNo === no ? ' on' : ''}`}
              onClick={() => search(no)}
            >
              {no}
            </span>
          ))}
        </div>
      </div>

      {loading && !order && (
        <div className="sc-card" style={{ padding: 48, textAlign: 'center' }}>
          <Spin />
        </div>
      )}

      {!loading && !order && error && (
        <div className="sc-card" style={{ padding: 40, textAlign: 'center' }}>
          <div className="sc-sub" style={{ marginBottom: 12 }}>{error}</div>
          <Button onClick={() => search()}>重新查询</Button>
        </div>
      )}

      {order && summary && (
        <>
          <div className="sc-card" style={{ padding: '14px 16px', marginBottom: 14 }}>
            <Row gutter={[24, 8]} align="middle">
              <Col>
                <div className="sc-meta-k">订单号</div>
                <div className="sc-mono" style={{ fontWeight: 600 }}>{order.order_no}</div>
              </Col>
              <Col><div className="sc-meta-k">订单行数</div><div className="sc-mono">{order.lines} 行</div></Col>
              <Col><div className="sc-meta-k">需求总量</div><div className="sc-mono">{fmtQty(order.total_qty)} 件</div></Col>
              <Col><div className="sc-meta-k">交期</div><div className="sc-mono">{order.promised_date || '—'}</div></Col>
              <Col flex="auto" />
              <Col>{orderStatus && <Tag color={orderStatus.color}>{orderStatus.label}</Tag>}</Col>
            </Row>
            <CoverageBar segments={summary.segments} total={order.total_qty} />
          </div>

          <div className="sc-card" style={{ padding: '0 0 4px' }}>
            <div className="sc-card-head">
              <h3>订单行 × 覆盖明细</h3>
              <span className="sc-hint">
                共 {order.lines} 行{summary.shortage > 0 ? ` · 缺口 ${fmtQty(summary.shortage)} 件` : ' · 全部已覆盖'}
              </span>
              <span style={{ marginLeft: 'auto', fontSize: 12, color: '#475569' }}>
                覆盖 <b style={{ color: '#16a34a' }}>{fmtQty(summary.covered)}</b> 件
                {summary.shortage > 0 && <> · 缺口 <b style={{ color: '#dc2626' }}>{fmtQty(summary.shortage)}</b> 件</>}
              </span>
            </div>
            <Table<CoverageLine>
              rowKey={(r) => String(r.line_no)}
              dataSource={lines}
              columns={LINE_COLUMNS}
              loading={loading}
              size="small"
              pagination={false}
              scroll={{ x: 1140 }}
              locale={{ emptyText: '该订单没有未结需求行' }}
              expandable={{ expandedRowRender: (row) => <LineDetail line={row} note={note} /> }}
            />
          </div>
        </>
      )}
    </div>
  )
}
