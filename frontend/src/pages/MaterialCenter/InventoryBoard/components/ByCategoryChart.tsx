import { Empty, Spin } from 'antd'
import { Pie } from '@ant-design/charts'

interface Row {
  category: string
  material_count: number
  total_qty: number
  total_value: number
}

interface Props {
  data: Row[]
  loading?: boolean
}

export default function ByCategoryChart({ data, loading }: Props) {
  const chartData = (data || []).slice(0, 10).map((d) => ({
    type: d.category,
    value: Number(d.total_value) || 0,
  }))
  return (
    <Spin spinning={!!loading}>
      <div className="card" style={{ padding: 16, height: '100%' }}>
        <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>按物料类别金额占比 Top 10</h3>
        {chartData.length > 0 ? (
          <Pie
            data={chartData}
            angleField="value"
            colorField="type"
            radius={0.85}
            innerRadius={0.55}
            legend={{ color: { position: 'bottom', layout: { justifyContent: 'center' } } }}
            label={{ text: (d: { type: string; value: number }) => `${d.type}`, style: { fontSize: 11 } }}
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