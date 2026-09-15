import { Empty, Spin } from 'antd'
import { Column } from '@ant-design/charts'

interface Bucket {
  bucket: string
  material_count: number
  total_qty: number
  total_value: number
}

interface Props {
  data: Bucket[]
  loading?: boolean
}

export default function AgingChart({ data, loading }: Props) {
  const chartData = (data || []).map((d) => ({
    bucket: d.bucket,
    value: Number(d.total_value) || 0,
  }))
  return (
    <Spin spinning={!!loading}>
      <div className="card" style={{ padding: 16, height: '100%' }}>
        <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>库龄分布（按库存金额）</h3>
        {chartData.length > 0 ? (
          <Column
            data={chartData}
            xField="bucket"
            yField="value"
            colorField="bucket"
            legend={false}
            columnStyle={{ radius: [4, 4, 0, 0] }}
            axis={{ x: { label: { style: { fontSize: 11 } } }, y: { label: { style: { fontSize: 10 } } } }}
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
