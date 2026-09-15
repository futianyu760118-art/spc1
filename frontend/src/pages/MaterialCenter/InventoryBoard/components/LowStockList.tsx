import { Empty, Spin, Table } from 'antd'

interface Row {
  material_code?: string
  material_name?: string
  warehouse_name?: string
  qty_on_hand: number
  unit?: string
}

interface Props {
  data: Row[]
  loading?: boolean
}

export default function LowStockList({ data, loading }: Props) {
  return (
    <Spin spinning={!!loading}>
      <div className="card" style={{ padding: 16, height: '100%' }}>
        <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>低库存 Top 10</h3>
        <Table<Row>
          size="small"
          rowKey={(r, i) => `${r.material_code}-${r.warehouse_name}-${i}`}
          dataSource={data || []}
          pagination={false}
          locale={{ emptyText: <Empty description={loading ? '加载中…' : '暂无数据'} /> }}
          columns={[
            { title: '物料编码', dataIndex: 'material_code', width: 120, ellipsis: true },
            { title: '物料名称', dataIndex: 'material_name', ellipsis: true },
            { title: '仓库', dataIndex: 'warehouse_name', width: 100, ellipsis: true },
            {
              title: '在库量',
              dataIndex: 'qty_on_hand',
              width: 100,
              align: 'right',
              render: (v: number, r) => <span style={{ color: '#ef4444', fontWeight: 600 }}>{(Number(v) || 0).toLocaleString()}{r.unit ? ` ${r.unit}` : ''}</span>,
            },
          ]}
        />
      </div>
    </Spin>
  )
}
