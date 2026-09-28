import { useCallback, useEffect, useState } from 'react'
import { Alert, Empty, Input, Space, Table, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import api from '@/services/api'

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

interface BucketRow {
  bucket_date: string
  opening_qty: number
  gross_demand_qty: number
  supply_po_qty: number
  supply_task_qty: number
  supply_subcontract_qty: number
  supply_transfer_qty: number
  safety_stock_qty: number
  closing_qty: number
  net_demand_qty: number
}

function fmtQty(v: number | null | undefined): string {
  if (v == null) return '-'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

export default function MaterialBalanceTab({ runId }: { runId: number | null }) {
  const [latestSuccess, setLatestSuccess] = useState<RunOption | null>(null)
  const [runsLoaded, setRunsLoaded] = useState(false)
  const [data, setData] = useState<BucketRow[]>([])
  const [searchedCode, setSearchedCode] = useState('')
  const [loading, setLoading] = useState(false)

  const effectiveRunId = runId ?? latestSuccess?.id ?? null

  useEffect(() => {
    const loadRuns = async () => {
      try {
        const res = (await api.get('/mrp/runs', { params: { page: 1, page_size: 100 } })) as unknown as ApiResponse<PageData<RunOption>>
        const firstSuccess = (res.data.items || []).find((r) => r.status === 'success')
        setLatestSuccess(firstSuccess || null)
      } catch {
        // 全局拦截器已提示
      } finally {
        setRunsLoaded(true)
      }
    }
    loadRuns()
  }, [])

  useEffect(() => {
    setData([])
    setSearchedCode('')
  }, [effectiveRunId])

  const search = useCallback(async (value: string) => {
    const code = value.trim()
    if (!code) return
    if (effectiveRunId == null) return
    setLoading(true)
    try {
      const res = (await api.get(`/mrp/runs/${effectiveRunId}/buckets`, {
        params: { material_code: code },
      })) as unknown as ApiResponse<BucketRow[]>
      setData(res.data || [])
      setSearchedCode(code)
    } catch {
      // 全局拦截器已提示（含物料不存在）
    } finally {
      setLoading(false)
    }
  }, [effectiveRunId])

  const columns: ColumnsType<BucketRow> = [
    { title: '日期', dataIndex: 'bucket_date', width: 110, fixed: 'left' },
    { title: '期初', dataIndex: 'opening_qty', width: 100, align: 'right', render: fmtQty },
    { title: '毛需求', dataIndex: 'gross_demand_qty', width: 100, align: 'right', render: fmtQty },
    { title: 'PO 在途', dataIndex: 'supply_po_qty', width: 100, align: 'right', render: fmtQty },
    { title: '任务在制', dataIndex: 'supply_task_qty', width: 100, align: 'right', render: fmtQty },
    { title: '委外在途', dataIndex: 'supply_subcontract_qty', width: 100, align: 'right', render: fmtQty },
    { title: '调拨在途', dataIndex: 'supply_transfer_qty', width: 100, align: 'right', render: fmtQty },
    { title: '安全库存', dataIndex: 'safety_stock_qty', width: 100, align: 'right', render: fmtQty },
    { title: '期末', dataIndex: 'closing_qty', width: 100, align: 'right', render: fmtQty },
    {
      title: '缺口', dataIndex: 'net_demand_qty', width: 100, align: 'right', fixed: 'right',
      render: (v: number) => (
        <span style={{ color: v > 0 ? '#e11d48' : undefined, fontWeight: v > 0 ? 600 : undefined }}>{fmtQty(v)}</span>
      ),
    },
  ]

  return (
    <div>
      <div className="card-modern" style={{ padding: '16px 20px', marginBottom: 16 }}>
        <Space wrap>
          <Input.Search
            placeholder="输入物料编码"
            style={{ width: 260 }}
            allowClear
            enterButton="查询"
            onSearch={search}
            disabled={effectiveRunId == null}
          />
          {effectiveRunId != null && (
            <Typography.Text type="secondary">
              当前批次：{runId != null ? `#${runId}` : (latestSuccess?.run_no || `#${effectiveRunId}`)}
            </Typography.Text>
          )}
        </Space>
      </div>

      {runsLoaded && effectiveRunId == null ? (
        <Alert
          type="info"
          showIcon
          message="暂无成功的运算批次"
          description="请先在「运算批次」触发一次运算，成功后再查询物料日桶平衡。"
        />
      ) : (
        <div className="card-modern" style={{ padding: '0 0 4px' }}>
          <Table<BucketRow>
            rowKey="bucket_date"
            dataSource={data}
            columns={columns}
            loading={loading}
            size="small"
            scroll={{ x: 1100 }}
            rowClassName={(row) => (row.net_demand_qty > 0 ? 'ant-table-row-danger' : '')}
            pagination={false}
            locale={{
              emptyText: (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description={searchedCode ? '该物料本批次无供需活动' : '输入物料编码后查询'}
                />
              ),
            }}
          />
        </div>
      )}
    </div>
  )
}
