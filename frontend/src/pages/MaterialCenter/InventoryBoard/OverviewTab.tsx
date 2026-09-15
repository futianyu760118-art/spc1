import { useEffect, useState } from 'react'
import { Select } from 'antd'
import KpiStrip from './components/KpiStrip'
import ByWarehouseChart from './components/ByWarehouseChart'
import ByCategoryChart from './components/ByCategoryChart'
import AgingChart from './components/AgingChart'
import LowStockList from './components/LowStockList'
import { inventoryBoardApi } from '@/services/api'

interface OverviewData {
  kpi: {
    material_count: number
    total_qty: number
    total_value: number
    warehouse_count: number
  }
  by_warehouse: any[]
  by_category: any[]
  aging: any[]
  low_stock: any[]
  warehouses: { id: number; name: string }[]
  categories: string[]
}

interface Props {
  onLoadingChange?: (loading: boolean) => void
}

export default function OverviewTab({ onLoadingChange }: Props) {
  const [data, setData] = useState<OverviewData | null>(null)
  const [loading, setLoading] = useState(false)
  const [warehouseId, setWarehouseId] = useState<number | undefined>()
  const [category, setCategory] = useState<string | undefined>()

  const fetchData = async () => {
    setLoading(true)
    onLoadingChange?.(true)
    try {
      const res: any = await inventoryBoardApi.getOverview({
        warehouse_id: warehouseId,
        category,
      })
      setData(res.data)
    } catch {
      setData(null)
    } finally {
      setLoading(false)
      onLoadingChange?.(false)
    }
  }

  useEffect(() => {
    fetchData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [warehouseId, category])

  return (
    <div>
      {/* 筛选条 */}
      <div className="card mb12" style={{ padding: 12, display: 'flex', gap: 12, alignItems: 'center' }}>
        <span style={{ color: '#475569', fontSize: 13 }}>仓库:</span>
        <Select
          allowClear
          placeholder="全部仓库"
          style={{ width: 180 }}
          value={warehouseId}
          onChange={(v) => setWarehouseId(v)}
          options={(data?.warehouses || []).map((w) => ({ label: w.name, value: w.id }))}
        />
        <span style={{ color: '#475569', fontSize: 13 }}>物料类别:</span>
        <Select
          allowClear
          placeholder="全部类别"
          style={{ width: 180 }}
          value={category}
          onChange={(v) => setCategory(v)}
          options={(data?.categories || []).map((c) => ({ label: c, value: c }))}
        />
      </div>

      {/* KPI */}
      <KpiStrip
        loading={loading}
        items={[
          { label: '物料种类', value: data?.kpi.material_count ?? 0, unit: '种' },
          { label: '库存总量', value: data?.kpi.total_qty ?? 0, unit: '' },
          { label: '库存金额', value: data?.kpi.total_value ?? 0, unit: '¥' },
          { label: '覆盖仓库', value: data?.kpi.warehouse_count ?? 0, unit: '个' },
        ]}
      />

      {/* 图表区 */}
      <div className="grid g2 mt12">
        <ByWarehouseChart data={data?.by_warehouse || []} loading={loading} />
        <AgingChart data={data?.aging || []} loading={loading} />
      </div>
      <div className="grid g2 mt12">
        <ByCategoryChart data={data?.by_category || []} loading={loading} />
        <LowStockList data={data?.low_stock || []} loading={loading} />
      </div>
    </div>
  )
}
