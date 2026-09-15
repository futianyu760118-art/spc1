import { useNavigate } from 'react-router-dom'
import { Empty, Progress, Spin, Table, Tag, Tooltip } from 'antd'

interface Row {
  check_id: number
  check_no: string
  status: string
  total_materials: number
  checked_materials: number
  completion_rate: number
  check_date: string
  age_days: number
  created_by?: string
  order_no?: string
}

interface Props {
  data: Row[]
  loading?: boolean
}

const STATUS_TAG: Record<string, { color: string; text: string }> = {
  open: { color: 'blue', text: '待开始' },
  in_progress: { color: 'gold', text: '进行中' },
}

export default function ActiveChecksTable({ data, loading }: Props) {
  const navigate = useNavigate()
  return (
    <Spin spinning={!!loading}>
      <div className="card" style={{ padding: 16 }}>
        <h3 className="text-sm font-semibold m-0 mb-3" style={{ color: '#475569' }}>进行中盘点单</h3>
        <Table<Row>
          size="small"
          rowKey="check_id"
          dataSource={data || []}
          pagination={{ pageSize: 10, showSizeChanger: false }}
          locale={{ emptyText: <Empty description={loading ? '加载中…' : '暂无进行中盘点单'} /> }}
          onRow={(r) => ({ onClick: () => navigate(`/stock-check/${r.check_id}`), style: { cursor: 'pointer' } })}
          columns={[
            { title: '盘点单号', dataIndex: 'check_no', width: 160, ellipsis: true },
            {
              title: '状态',
              dataIndex: 'status',
              width: 90,
              render: (s: string) => <Tag color={STATUS_TAG[s]?.color}>{STATUS_TAG[s]?.text || s}</Tag>,
            },
            { title: '关联订单', dataIndex: 'order_no', width: 130, ellipsis: true },
            {
              title: '进度',
              width: 200,
              render: (_, r) => (
                <Tooltip title={`${r.checked_materials}/${r.total_materials}`}>
                  <Progress percent={Math.round((r.completion_rate || 0) * 100)} size="small" status="active" />
                </Tooltip>
              ),
            },
            {
              title: '已盘/应盘',
              width: 110,
              align: 'right',
              render: (_, r) => `${r.checked_materials}/${r.total_materials}`,
            },
            { title: '盘点日期', dataIndex: 'check_date', width: 110 },
            { title: '创建人', dataIndex: 'created_by', width: 100, ellipsis: true },
            {
              title: '已存续',
              dataIndex: 'age_days',
              width: 80,
              align: 'right',
              render: (n: number) => <span style={{ color: n > 7 ? '#f59e0b' : '#64748b' }}>{n} 天</span>,
            },
          ]}
        />
      </div>
    </Spin>
  )
}
