import { useCallback, useEffect, useState } from 'react'
import { Alert, Card, Col, Row, Space, Table, Tag, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { ReactNode } from 'react'
import api from '@/services/api'

interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

interface ComparisonSummary {
  run_id: number
  total_suggestions: number
  match: number
  diff_qty: number
  diff_date: number
  spc_only: number
  k3_only: number
  match_rate: number
}

interface ComparisonItem {
  id: number
  material_id: number
  material_code: string
  material_name: string | null
  bill_type: number
  suggest_qty: number
  need_date: string | null
  compare_status: string | null
  k3_qty: number | null
  k3_need_date: string | null
}

interface K3OnlyItem {
  material_id: number
  need_date: string
  qty: number
}

interface ComparisonData {
  summary: ComparisonSummary
  k3_only: K3OnlyItem[]
  items: ComparisonItem[]
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

function StatCard({ title, value, color }: { title: string; value: ReactNode; color: string }) {
  return (
    <Card size="small" className="card-modern" style={{ padding: 0 }}>
      <div style={{ padding: '4px 4px 0' }}>
        <div style={{ fontSize: 'calc(1.375rem * var(--font-size-scale))', fontWeight: 700, color }}>
          {value}
        </div>
        <div style={{ fontSize: 'calc(0.75rem * var(--font-size-scale))', color: '#64748b' }}>{title}</div>
      </div>
    </Card>
  )
}

export default function ComparisonTab({ runId }: { runId: number | null }) {
  const [data, setData] = useState<ComparisonData | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(false)
    try {
      const res = (await api.get('/mrp/comparison', {
        params: runId != null ? { run_id: runId } : {},
        skipErrorToast: true,
      })) as unknown as ApiResponse<ComparisonData>
      setData(res.data)
    } catch {
      setData(null)
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => { load() }, [load])

  const itemColumns: ColumnsType<ComparisonItem> = [
    {
      title: '物料编码', dataIndex: 'material_code', width: 150, ellipsis: true,
      render: (v: string) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    { title: '物料名称', dataIndex: 'material_name', width: 200, ellipsis: true },
    {
      title: '建议量', dataIndex: 'suggest_qty', width: 110, align: 'right',
      render: (v: number) => fmtQty(v),
    },
    {
      title: '需求日', dataIndex: 'need_date', width: 110,
      render: (v: string | null) => v || '-',
    },
    {
      title: '对比状态', dataIndex: 'compare_status', width: 100,
      render: (v: string | null) => {
        if (!v) return '-'
        const m = COMPARE_MAP[v] || { label: v, color: 'default' }
        return <Tag color={m.color}>{m.label}</Tag>
      },
    },
    {
      title: 'K3 量', dataIndex: 'k3_qty', width: 110, align: 'right',
      render: (v: number | null) => fmtQty(v),
    },
    {
      title: 'K3 需求日', dataIndex: 'k3_need_date', width: 120,
      render: (v: string | null) => v || '-',
    },
  ]

  const k3OnlyColumns: ColumnsType<K3OnlyItem> = [
    {
      title: '物料 ID', dataIndex: 'material_id', width: 120,
      render: (v: number) => <span style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</span>,
    },
    { title: '需求日', dataIndex: 'need_date', width: 120 },
    {
      title: 'K3 量', dataIndex: 'qty', width: 120, align: 'right',
      render: (v: number) => fmtQty(v),
    },
  ]

  const summary = data?.summary

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={4}><StatCard title="匹配数" value={summary?.match ?? '-'} color="#16a34a" /></Col>
        <Col span={4}><StatCard title="匹配率" value={summary ? `${summary.match_rate}%` : '-'} color="#6366f1" /></Col>
        <Col span={4}><StatCard title="量差" value={summary?.diff_qty ?? '-'} color="#f59e0b" /></Col>
        <Col span={4}><StatCard title="日期差" value={summary?.diff_date ?? '-'} color="#f59e0b" /></Col>
        <Col span={4}><StatCard title="仅 SPC" value={summary?.spc_only ?? '-'} color="#e11d48" /></Col>
        <Col span={4}><StatCard title="仅 K3" value={summary?.k3_only ?? '-'} color="#0ea5e9" /></Col>
      </Row>

      {error ? (
        <Alert
          type="info"
          showIcon
          message="暂无 K3 对比数据"
          description="请先完成一次成功的运算批次，并确认 K3 计划数据（mrp_plan_order）已同步。"
        />
      ) : (
        <>
          <div className="card-modern" style={{ padding: '12px 16px 0', marginBottom: 16 }}>
            <Space style={{ marginBottom: 8 }}>
              <Typography.Text strong>差异清单（SPC 建议 vs K3）</Typography.Text>
              <Typography.Text type="secondary">共 {summary?.total_suggestions ?? 0} 条建议</Typography.Text>
            </Space>
            <Table<ComparisonItem>
              rowKey="id"
              dataSource={data?.items || []}
              columns={itemColumns}
              loading={loading}
              size="small"
              scroll={{ x: 1000 }}
              pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
            />
          </div>

          <div className="card-modern" style={{ padding: '12px 16px 0' }}>
            <Space style={{ marginBottom: 8 }}>
              <Typography.Text strong>仅 K3 存在的需求</Typography.Text>
              <Typography.Text type="secondary">SPC 未产生对应建议</Typography.Text>
            </Space>
            <Table<K3OnlyItem>
              rowKey={(row) => `${row.material_id}-${row.need_date}`}
              dataSource={data?.k3_only || []}
              columns={k3OnlyColumns}
              loading={loading}
              size="small"
              pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
            />
          </div>
        </>
      )}
    </div>
  )
}
