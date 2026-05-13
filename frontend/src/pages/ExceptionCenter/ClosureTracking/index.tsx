import { useEffect, useState } from 'react'
import { Table, Tag, Button, Space, message, Row, Col } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { exceptionApi } from '../../../services/api'

const STATUS_LABEL: Record<string, string> = {
  open: '待处理',
  in_progress: '处理中',
  closed: '已关闭',
}

const SOURCE_TYPE_LABEL: Record<string, string> = {
  risk_issue: '风险问题',
  quality_issue: '品质异常',
  process_exception: '工序异常',
}

export default function ClosureTracking() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const res: any = await exceptionApi.getClosureTracking()
      setData(res.data)
    } catch (e: any) {
      message.error(e.message || '获取闭环跟踪数据失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const statCards = data ? [
    { label: '待处理', value: data.total_open, color: '#e11d48' },
    { label: '处理中', value: data.total_in_progress, color: '#d97706' },
    { label: '已关闭', value: data.total_closed, color: '#10b981' },
    { label: '已超时', value: data.total_overdue, color: '#dc2626' },
  ] : []

  const typeColumns = [
    {
      title: '异常类型', dataIndex: 'source_type', width: 120,
      render: (v: string) => SOURCE_TYPE_LABEL[v] || v,
    },
    { title: '待处理', dataIndex: 'open_count', width: 80 },
    { title: '处理中', dataIndex: 'in_progress_count', width: 80 },
    { title: '已关闭', dataIndex: 'closed_count', width: 80 },
    {
      title: '已超时', dataIndex: 'overdue_count', width: 80,
      render: (v: number) => v > 0 ? <Tag color="red">{v}</Tag> : v,
    },
  ]

  const personColumns = [
    { title: '责任人', dataIndex: 'owner', width: 120 },
    { title: '待处理', dataIndex: 'open_count', width: 80 },
    { title: '处理中', dataIndex: 'in_progress_count', width: 80 },
    { title: '已关闭', dataIndex: 'closed_count', width: 80 },
    {
      title: '已超时', dataIndex: 'overdue_count', width: 80,
      render: (v: number) => v > 0 ? <Tag color="red">{v}</Tag> : v,
    },
  ]

  return (
    <div>
      <div className="filter-bar" style={{ marginBottom: 14 }}>
        <div className="filter-left" />
        <div className="filter-right">
          <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>刷新</Button>
        </div>
      </div>

      {/* 统计卡 */}
      {data && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
          {statCards.map(({ label, value, color }) => (
            <div key={label} className="card-modern" style={{ flex: 1, padding: '12px 20px' }}>
              <div style={{ color: '#94a3b8', fontSize: 12, marginBottom: 4 }}>{label}</div>
              <div style={{ fontSize: 24, fontWeight: 700, color }}>{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* 按类型分布 */}
      <div className="card-modern" style={{ padding: 16, marginBottom: 16 }}>
        <h3 style={{ marginBottom: 12, fontSize: 15 }}>按异常类型分布</h3>
        <Table
          rowKey="source_type"
          dataSource={data?.by_type || []}
          columns={typeColumns}
          loading={loading}
          size="small"
          pagination={false}
        />
      </div>

      {/* 按责任人分布 */}
      <div className="card-modern" style={{ padding: 16 }}>
        <h3 style={{ marginBottom: 12, fontSize: 15 }}>按责任人分布</h3>
        <Table
          rowKey="owner"
          dataSource={data?.by_person || []}
          columns={personColumns}
          loading={loading}
          size="small"
          pagination={false}
        />
      </div>
    </div>
  )
}
