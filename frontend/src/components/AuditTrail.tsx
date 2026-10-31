import { Table } from 'antd'

interface AuditRecord {
  id: number
  table_name: string
  record_id: string
  field: string
  old_value: string
  new_value: string
  operator: string
  created_at: string
}

interface AuditTrailProps {
  records: AuditRecord[]
  loading?: boolean
}

export default function AuditTrail({ records, loading = false }: AuditTrailProps) {
  const columns = [
    { title: '时间', dataIndex: 'created_at', key: 'created_at', width: 170 },
    { title: '操作人', dataIndex: 'operator', key: 'operator', width: 100 },
    { title: '表', dataIndex: 'table_name', key: 'table_name', width: 130 },
    { title: '字段', dataIndex: 'field', key: 'field', width: 110 },
    { title: '旧值', dataIndex: 'old_value', key: 'old_value', ellipsis: true },
    { title: '新值', dataIndex: 'new_value', key: 'new_value', ellipsis: true },
  ]

  return (
    <div className="card-modern" style={{ overflow: 'hidden' }}>
      <div style={{ padding: '16px 20px 0' }}>
        <h3 className="text-sm font-semibold m-0" style={{ color: '#475569' }}>审计轨迹</h3>
      </div>
      <div className="table-modern" style={{ marginTop: 12 }}>
        <Table
          columns={columns}
          dataSource={records}
          rowKey="id"
          loading={loading}
          size="small"
          pagination={{ pageSize: 10, showSizeChanger: false, style: { padding: '0 16px' } }}
        />
      </div>
    </div>
  )
}
