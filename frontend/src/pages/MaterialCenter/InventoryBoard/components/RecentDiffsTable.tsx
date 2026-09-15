import { Empty, Spin, Table, Tag } from 'antd'

interface Row {
  check_no: string
  check_date: string
  material_code?: string
  material_name?: string
  spec_model?: string
  unit?: string
  system_qty: number
  actual_qty?: number | null
  diff_qty?: number | null
}

interface Props {
  data: Row[]
  loading?: boolean
}

function fmt(n?: number | null): string {
  if (n == null) return '—'
  return Number(n).toLocaleString()
}

export default function RecentDiffsTable({ data, loading }: Props) {
  return (
    <Spin spinning={!!loading}>
      <div className="card" style={{ padding: 16 }}>
        <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>近期差异 Top 20</h3>
        <Table<Row>
          size="small"
          rowKey={(r, i) => `${r.check_no}-${r.material_code}-${i}`}
          dataSource={data || []}
          pagination={false}
          locale={{ emptyText: <Empty description={loading ? '加载中…' : '暂无差异'} /> }}
          scroll={{ x: 900 }}
          columns={[
            { title: '盘点单号', dataIndex: 'check_no', width: 160, ellipsis: true, fixed: 'left' },
            { title: '日期', dataIndex: 'check_date', width: 110 },
            { title: '物料编码', dataIndex: 'material_code', width: 120, ellipsis: true },
            { title: '物料名称', dataIndex: 'material_name', ellipsis: true },
            { title: '规格', dataIndex: 'spec_model', width: 140, ellipsis: true },
            { title: '系统', dataIndex: 'system_qty', width: 90, align: 'right', render: fmt },
            { title: '实盘', dataIndex: 'actual_qty', width: 90, align: 'right', render: fmt },
            {
              title: '差异',
              dataIndex: 'diff_qty',
              width: 110,
              align: 'right',
              render: (v: number | null | undefined, r) => {
                if (v == null) return '—'
                const positive = Number(v) >= 0
                return (
                  <Tag color={positive ? 'green' : 'red'}>
                    {positive ? '+' : ''}{fmt(v)}{r.unit ? ` ${r.unit}` : ''}
                  </Tag>
                )
              },
            },
          ]}
        />
      </div>
    </Spin>
  )
}
