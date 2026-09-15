import { Empty, Spin } from 'antd'
import { Line } from '@ant-design/charts'

interface Point {
  date: string
  checks_completed: number
  diff_items_count: number
  total_diff_qty: number
}

interface Props {
  data: Point[]
  loading?: boolean
}

export default function StockCheckTrend({ data, loading }: Props) {
  const chartData = (data || []).flatMap((d) => [
    { date: d.date, type: '完成盘点单', value: d.checks_completed },
    { date: d.date, type: '差异行数', value: d.diff_items_count },
  ])
  return (
    <Spin spinning={!!loading}>
      <div className="card" style={{ padding: 16 }}>
        <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>盘点趋势（最近 30 天）</h3>
        {chartData.length > 0 ? (
          <Line
            data={chartData}
            xField="date"
            yField="value"
            colorField="type"
            shapeField="smooth"
            point={{ shapeField: 'circle', sizeField: 3 }}
            axis={{ x: { label: { style: { fontSize: 10 } } }, y: { label: { style: { fontSize: 10 } } } }}
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
