import { Empty, Spin } from 'antd'
import { Bar } from '@ant-design/charts'

interface Row {
  warehouse_id: number
  warehouse_name: string
  material_count: number
  total_qty: number
  total_value: number
}

interface Props {
  data: Row[]
  loading?: boolean
}

export default function ByWarehouseChart({ data, loading }: Props) {
  const chartData = (data || []).slice(0, 15).map((d) => ({
    warehouse: d.warehouse_name,
    value: Number(d.total_value) || 0,
  }))
  return (
    <Spin spinning={!!loading}>
      <div className="card" style={{ padding: 16, height: '100%' }}>
        <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>按仓库库存金额 Top 15</h3>
        {chartData.length > 0 ? (
          <Bar
            data={chartData}
            xField="value"
            yField="warehouse"
            colorField="warehouse"
            legend={false}
            barStyle={{ radius: [0, 4, 4, 0] }}
            axis={{ x: { label: { style: { fontSize: 10 } } }, y: { label: { style: { fontSize: 10 }, autoEllipsis: true } } }}
            tooltip={{ items: [{ name: '金额', field: 'value' }] }}
            height={260}
          />
        ) : (
          <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Empty description={loading ? '加载中…' : '暂无数据'} />
          </div>
        )}
      </div>
    </Spin>
  )
}
