import { useEffect, useState } from 'react'
import { Empty, Spin, Table, Tag } from 'antd'
import KpiStrip from './components/KpiStrip'
import ActiveChecksTable from './components/ActiveChecksTable'
import StockCheckTrend from './components/StockCheckTrend'
import RecentDiffsTable from './components/RecentDiffsTable'
import { inventoryBoardApi, materialApi } from '@/services/api'

interface OverviewData {
  kpi: {
    active_checks: number
    month_completion_rate: number
    month_profit_qty: number
    month_loss_qty: number
  }
  active_checks: any[]
  trend: any[]
  recent_diffs: any[]
}

interface Props {
  onLoadingChange?: (loading: boolean) => void
}

export default function StockCheckTab({ onLoadingChange }: Props) {
  const [data, setData] = useState<OverviewData | null>(null)
  const [loading, setLoading] = useState(false)
  const [myTasks, setMyTasks] = useState<any[]>([])
  const [myLoading, setMyLoading] = useState(false)

  const fetchOverview = async () => {
    setLoading(true)
    onLoadingChange?.(true)
    try {
      const res: any = await inventoryBoardApi.getStockCheck()
      setData(res.data)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
      onLoadingChange?.(false)
    }
  }

  const fetchMyTasks = async () => {
    setMyLoading(true)
    try {
      const res: any = await materialApi.getMyStockCheckItems({ page: 1, page_size: 20 })
      setMyTasks(res.data?.items || [])
    } catch {
      setMyTasks([])
    } finally {
      setMyLoading(false)
    }
  }

  useEffect(() => {
    fetchOverview()
    fetchMyTasks()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div>
      {/* KPI */}
      <KpiStrip
        loading={loading}
        items={[
          { label: '进行中盘点单', value: data?.kpi.active_checks ?? 0, unit: '单' },
          {
            label: '本月完成率',
            value: data ? `${Math.round((data.kpi.month_completion_rate || 0) * 100)}%` : '—',
            tone: (data?.kpi.month_completion_rate ?? 0) >= 0.8 ? 'good' : (data?.kpi.month_completion_rate ?? 0) >= 0.5 ? 'warn' : 'bad',
          },
          { label: '本月盘盈', value: data?.kpi.month_profit_qty ?? 0, tone: 'good' },
          { label: '本月盘亏', value: data?.kpi.month_loss_qty ?? 0, tone: 'bad' },
        ]}
      />

      <div className="grid g2-1 mt12">
        {/* 我的盘点任务 */}
        <div className="card" style={{ padding: 16 }}>
          <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>我的盘点任务</h3>
          <Spin spinning={myLoading}>
            <Table
              size="small"
              rowKey="id"
              dataSource={myTasks}
              pagination={false}
              locale={{ emptyText: <Empty description={myLoading ? '加载中…' : '暂无待盘点任务'} /> }}
              columns={[
                { title: '盘点单号', dataIndex: 'check_no', width: 140, ellipsis: true },
                { title: '物料', dataIndex: 'material_name', ellipsis: true },
                {
                  title: '状态',
                  dataIndex: 'status',
                  width: 90,
                  render: (s: string) => <Tag color={s === 'counted' ? 'green' : 'blue'}>{s === 'counted' ? '已盘' : '待盘'}</Tag>,
                },
                { title: '应盘', dataIndex: 'req_qty', width: 80, align: 'right' },
                { title: '实盘', dataIndex: 'actual_qty', width: 80, align: 'right', render: (v: any) => v ?? '—' },
              ]}
            />
          </Spin>
        </div>
        <ActiveChecksTable data={data?.active_checks || []} loading={loading} />
      </div>

      <div className="mt12">
        <StockCheckTrend data={data?.trend || []} loading={loading} />
      </div>

      <div className="mt12">
        <RecentDiffsTable data={data?.recent_diffs || []} loading={loading} />
      </div>
    </div>
  )
}
